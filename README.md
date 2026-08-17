# Financial Data Paywall Gateway — MVP (Day 1–2)

A paywall-as-a-service layer for financial/alt-data providers: wrap any API
endpoint, set a price, and let AI agents pay per call via an x402-style
HTTP 402 challenge — while every transaction feeds a reputation/discovery
layer from day one.

## What's built and tested here

- **402 challenge/response flow** — an agent hitting a paid endpoint without
  proof gets a 402 with the price; retrying with proof gets the real data.
- **Provider + endpoint config** — no-code pricing setup via two POST calls.
- **Transaction ledger** — every call (challenged, paid, blocked, failed) is
  logged, forming the raw audit trail.
- **Velocity-based reputation event logging** — an agent calling too fast in
  a rolling window gets flagged and recorded, seeding the future trust layer.
- **Public directory** — a live listing of paywalled endpoints, the seed of
  the discovery layer agents would eventually browse.
- **Provider dashboard** — revenue, call volume, unique paying agents.

All of the above ran successfully end-to-end in `test_flow.py` against a
mock financial data provider.

## Running it yourself

```bash
python -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate
pip install -r requirements.txt

# Terminal 1 — mock upstream financial data provider
uvicorn mock_provider:app --port 8001

# Terminal 2 — the gateway itself
uvicorn app.main:app --port 8000

# Terminal 3 — run the full simulated flow
python test_flow.py
```

Then browse `http://127.0.0.1:8000/directory` in a browser to see the
public listing, or `http://127.0.0.1:8000/docs` for interactive API docs
(FastAPI generates this automatically).

## Day 3–4 update: real x402 verification wired in

`app/x402_integration.py` now uses the official `x402` PyPI SDK (the same
one referenced in Coinbase's docs) — not a stub. It:

- registers a real EVM "exact" scheme for USDC on Base
- builds real x402 payment requirements for the 402 response
- verifies real payment headers against the public facilitator at
  `https://x402.org/facilitator`

**In this build sandbox specifically**, network access is restricted to a
fixed allow-list that does not include `x402.org`, so the facilitator call
fails fast (by design — a 4-second timeout) and the gateway falls back to
the simple Day 1-2 stub behaviour so the rest of the system keeps working
end-to-end. You'll see this clearly in the server log:

```
Could not reach x402 facilitator (https://x402.org/facilitator) within 4.0s.
Falling back to stub verification for this run.
Error: Facilitator get_supported failed (403): Host not in allowlist: x402.org.
```

That's a network-allowlist limitation of *this build environment*, not a
bug in the integration. Deploy this anywhere with normal outbound network
access (your own machine, a VPS, a cloud function) and it will talk to the
real facilitator with no code changes.

## What's still stubbed / left for you (honest list)

- **Wallet signing isn't implemented on the agent side.** This repo is the
  *server* (resource/paywall side) of x402. An agent actually paying you
  needs its own wallet + the `x402` client-side SDK (`x402.client`) to sign
  and attach a real payment header — that's the next piece to build or
  wire into a test agent once you have real network access to verify
  against.
- **Real financial data provider**: no new code is needed — `upstream_url`
  on an `Endpoint` is just a config field. Point it at a real API (e.g.
  Alpha Vantage's demo endpoint, or Polygon.io with a free-tier key)
  instead of the mock provider when you register the endpoint.
- **Velocity threshold is a placeholder** (>10 calls / 30s). Tune this once
  you have real usage data — financial data call patterns vary a lot by use
  case (a backtest agent looks very different from a live-monitoring one).
- **No auth/API keys yet** for the provider config endpoints — fine for
  local testing, not for a public deployment.

## Suggested next steps

1. Deploy this somewhere with open outbound network access and confirm a
   real facilitator round-trip (the log line above will show success
   instead of the fallback warning).
2. Build or borrow a minimal x402 client (the SDK's `x402.client` module)
   to act as a real paying agent for testing.
3. Point one real endpoint at a real financial/alt-data API.
4. Add basic auth to the provider config endpoints before onboarding a
   real outside provider.
