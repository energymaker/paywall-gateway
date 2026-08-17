"""
Paywall-as-a-service gateway — MVP.

Flow:
  1. Provider registers, adds a paywalled endpoint with a price.
  2. Agent calls GET /pay/{provider_slug}/{endpoint_path}
     - No payment proof header -> HTTP 402 with price + challenge_id (like x402)
     - Valid payment proof header -> transaction logged as paid, request
       forwarded to the provider's real upstream URL, data returned.
  3. Every call (challenged, paid, or blocked) is logged to the transactions
     table. A simple velocity check logs a reputation event if an agent's
     call rate spikes, so the future trust/reputation layer has real history
     to build on from day one.

NOTE ON PAYMENT VERIFICATION: this MVP stubs out real signature verification
against a settlement facilitator (e.g. Coinbase's CDP for x402) — that's a
Day 3-4 integration once the plumbing here is proven. For now, any proof
string that isn't empty is treated as valid, so the full request/response
loop, pricing, and logging can be tested end-to-end immediately.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import Base, engine, get_db
from app import models
from app import x402_integration

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Financial Data Paywall Gateway (MVP)")

# --- simple in-memory velocity tracker (per agent_key) for anomaly logging ---
CALL_TIMESTAMPS = defaultdict(list)
VELOCITY_WINDOW_SECONDS = 30
VELOCITY_THRESHOLD = 10  # more than this many calls in the window -> flag


def check_velocity(db: Session, agent: models.Agent):
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=VELOCITY_WINDOW_SECONDS)
    timestamps = CALL_TIMESTAMPS[agent.agent_key]
    timestamps = [t for t in timestamps if t > window_start]
    timestamps.append(now)
    CALL_TIMESTAMPS[agent.agent_key] = timestamps

    if len(timestamps) > VELOCITY_THRESHOLD:
        event = models.ReputationEvent(
            agent_id=agent.id,
            event_type="velocity_spike",
            detail=f"{len(timestamps)} calls in {VELOCITY_WINDOW_SECONDS}s window",
        )
        db.add(event)
        db.commit()
        return True
    return False


# ---------------------------- provider config ----------------------------

class ProviderCreate(BaseModel):
    slug: str
    name: str
    contact_email: Optional[str] = None
    payout_wallet: Optional[str] = None


class EndpointCreate(BaseModel):
    path: str
    description: Optional[str] = None
    price_usd: float
    upstream_url: str


@app.post("/providers")
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Provider).filter_by(slug=payload.slug).first()
    if existing:
        raise HTTPException(400, "Provider slug already exists")
    provider = models.Provider(**payload.dict())
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


@app.post("/providers/{provider_slug}/endpoints")
def create_endpoint(provider_slug: str, payload: EndpointCreate, db: Session = Depends(get_db)):
    provider = db.query(models.Provider).filter_by(slug=provider_slug).first()
    if not provider:
        raise HTTPException(404, "Provider not found")
    endpoint = models.Endpoint(provider_id=provider.id, **payload.dict())
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    return endpoint


# ------------------------------ discovery ---------------------------------

@app.get("/directory")
def directory(db: Session = Depends(get_db)):
    """Public-facing listing of paywalled endpoints — the seed of the future
    discovery layer agents browse to find data worth paying for."""
    endpoints = db.query(models.Endpoint).filter_by(active=True).all()
    return [
        {
            "provider": e.provider.name,
            "endpoint": e.full_path,
            "price_usd": e.price_usd,
            "description": e.description,
        }
        for e in endpoints
    ]


# -------------------------- the paid proxy itself --------------------------

def get_or_create_agent(db: Session, agent_key: str) -> models.Agent:
    agent = db.query(models.Agent).filter_by(agent_key=agent_key).first()
    if not agent:
        agent = models.Agent(agent_key=agent_key)
        db.add(agent)
        db.commit()
        db.refresh(agent)
    return agent


@app.get("/pay/{provider_slug}/{endpoint_path}")
async def paid_proxy(
    provider_slug: str,
    endpoint_path: str,
    request: Request,
    db: Session = Depends(get_db),
    x_agent_key: Optional[str] = Header(None),
    x_payment_proof: Optional[str] = Header(None),
):
    provider = db.query(models.Provider).filter_by(slug=provider_slug).first()
    if not provider:
        raise HTTPException(404, "Unknown provider")

    endpoint = (
        db.query(models.Endpoint)
        .filter_by(provider_id=provider.id, path=endpoint_path, active=True)
        .first()
    )
    if not endpoint:
        raise HTTPException(404, "Unknown or inactive endpoint")

    agent_key = x_agent_key or "anonymous"
    agent = get_or_create_agent(db, agent_key)

    pay_to_wallet = provider.payout_wallet or "0x0000000000000000000000000000000000dEaD"
    requirements = await x402_integration.build_requirements(pay_to_wallet, endpoint.price_usd)

    # --- No payment proof: issue the 402 challenge, real x402-style ---
    if not x_payment_proof:
        db.add(models.Transaction(
            agent_id=agent.id, endpoint_id=endpoint.id,
            amount_usd=endpoint.price_usd, status="challenged",
        ))
        db.commit()

        if requirements is not None:
            # Real, spec-compliant x402 challenge: encode via the SDK's own
            # PaymentRequired response + header, so a real x402 client (like
            # the one we're about to build) can parse it correctly.
            server = await x402_integration.get_x402_server()
            payment_required = await server.create_payment_required_response(requirements)
            header_value = x402_integration.encode_payment_required_header(payment_required)
            return JSONResponse(
                status_code=402,
                headers={"PAYMENT-REQUIRED": header_value},
                content={"status": 402, "message": "Payment Required", "x402Version": 2},
            )
        else:
            # Facilitator unreachable (e.g. sandbox network restrictions) --
            # fall back to the simple Day 1-2 challenge shape so the flow
            # still works end-to-end during local development.
            challenge_body = {
                "status": 402,
                "message": "Payment Required",
                "price_usd": endpoint.price_usd,
                "endpoint": endpoint.full_path,
                "instructions": "Retry with X-Payment-Proof header set to a valid payment signature.",
                "note": "facilitator unreachable in this environment; using fallback challenge shape",
            }
            return JSONResponse(status_code=402, content=challenge_body)

    # --- Payment proof present: verify against the real x402 facilitator ---
    if requirements is not None:
        payment_valid, reason = await x402_integration.verify_payment_header(
            x_payment_proof, requirements[0]
        )
    else:
        payment_valid, reason = bool(x_payment_proof.strip()), "stub-mode fallback"

    if not payment_valid:
        db.add(models.Transaction(
            agent_id=agent.id, endpoint_id=endpoint.id,
            amount_usd=endpoint.price_usd, status="blocked",
            payment_proof=x_payment_proof,
        ))
        db.commit()
        raise HTTPException(403, f"Invalid payment proof: {reason}")

    flagged = check_velocity(db, agent)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream_resp = await client.get(endpoint.upstream_url)
        data = upstream_resp.json() if upstream_resp.headers.get(
            "content-type", ""
        ).startswith("application/json") else upstream_resp.text

        # Only count this as a successful, billable "paid" call if the
        # upstream actually returned success -- a network-blocked or error
        # response should never be logged as a paid, revenue-generating call.
        status = "paid" if upstream_resp.status_code < 400 else "failed"
    except Exception as e:
        data = {"error": f"upstream call failed: {e}"}
        status = "failed"

    db.add(models.Transaction(
        agent_id=agent.id, endpoint_id=endpoint.id,
        amount_usd=endpoint.price_usd if status == "paid" else 0.0,
        status=status,
        payment_proof=x_payment_proof,
    ))
    db.commit()

    return {
        "data": data,
        "billed_usd": endpoint.price_usd if status == "paid" else 0.0,
        "status": status,
        "velocity_flagged": flagged,
    }


# ------------------------------- dashboard ----------------------------------

@app.get("/providers/{provider_slug}/dashboard")
def provider_dashboard(provider_slug: str, db: Session = Depends(get_db)):
    provider = db.query(models.Provider).filter_by(slug=provider_slug).first()
    if not provider:
        raise HTTPException(404, "Provider not found")

    endpoint_ids = [e.id for e in provider.endpoints]
    txs = db.query(models.Transaction).filter(
        models.Transaction.endpoint_id.in_(endpoint_ids)
    ).all()

    paid = [t for t in txs if t.status == "paid"]
    revenue = sum(t.amount_usd for t in paid)
    unique_agents = len({t.agent_id for t in paid})

    return {
        "provider": provider.name,
        "total_calls": len(txs),
        "paid_calls": len(paid),
        "revenue_usd": round(revenue, 6),
        "unique_paying_agents": unique_agents,
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "financial-data-paywall-gateway"}
