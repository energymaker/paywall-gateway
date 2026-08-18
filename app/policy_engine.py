"""
Core policy evaluation logic. Rail-agnostic on purpose: callers pass in
which rail the attempt is on purely as metadata for logging, never as
something the policy schema branches on.

Usage from a rail adapter (e.g. the x402 flow):

    from app.policy_engine import evaluate

    decision = evaluate(
        db, agent_key="agent_123", rail="x402",
        amount_usd=0.02, category="market-data",
    )
    if decision.allowed:
        # proceed to sign/execute payment on that rail
        ...
    else:
        # block, return decision.reason to the agent
        ...
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.policy_models import Policy, PolicyCheckLog, utcnow


@dataclass
class Decision:
    allowed: bool
    reason: Optional[str] = None
    escalate: bool = False


def _effective_limit(values):
    """The tightest (lowest) non-null limit wins -- this is what makes the
    hierarchy narrowing-only. A None at every level means unconstrained.
    """
    present = [v for v in values if v is not None]
    return min(present) if present else None


def _scope_chain(db: Session, agent_key: str, team: Optional[str]):
    """Walk agent -> team -> account, returning whichever Policy rows exist
    at each level. Missing levels are simply skipped (not an error) --
    a deployment doesn't have to define a team policy to have an agent
    policy, for example.
    """
    scopes = [("agent", agent_key)]
    if team:
        scopes.append(("team", team))
    scopes.append(("account", "default"))

    policies = []
    for scope_type, scope_id in scopes:
        row = (
            db.query(Policy)
            .filter(
                Policy.scope_type == scope_type,
                Policy.scope_id == scope_id,
                Policy.active == "true",
            )
            .first()
        )
        if row:
            policies.append(row)
    return policies


def evaluate(
    db: Session,
    agent_key: str,
    rail: str,
    amount_usd: float,
    category: Optional[str] = None,
    team: Optional[str] = None,
) -> Decision:
    """Evaluate a proposed spend against the full narrowing-only policy
    chain for this agent, across whichever rail it's attempted on.
    Logs the decision either way -- this function is the single choke
    point every rail adapter must call before executing a payment.
    """
    policies = _scope_chain(db, agent_key, team)

    if not policies:
        # No policy configured anywhere in the chain: default-deny.
        # An enterprise compliance product should never fail open.
        decision = Decision(allowed=False, reason="no_policy_configured")
        _log(db, agent_key, rail, amount_usd, category, decision)
        return decision

    # Per-transaction cap: tightest non-null value across the chain
    per_tx_cap = _effective_limit([p.max_per_transaction_usd for p in policies])
    if per_tx_cap is not None and amount_usd > per_tx_cap:
        decision = Decision(
            allowed=False,
            reason=f"exceeds_per_transaction_cap:{per_tx_cap}",
        )
        _log(db, agent_key, rail, amount_usd, category, decision)
        return decision

    # Category allowlist: every level that specifies a list must include it
    if category:
        for p in policies:
            if p.allowed_categories:
                allowed = {c.strip() for c in p.allowed_categories.split(",")}
                if category not in allowed:
                    decision = Decision(
                        allowed=False,
                        reason=f"category_not_allowed:{category}",
                    )
                    _log(db, agent_key, rail, amount_usd, category, decision)
                    return decision

    # Rail allowlist: same pattern as category
    for p in policies:
        if p.allowed_rails:
            allowed = {r.strip() for r in p.allowed_rails.split(",")}
            if rail not in allowed:
                decision = Decision(allowed=False, reason=f"rail_not_allowed:{rail}")
                _log(db, agent_key, rail, amount_usd, category, decision)
                return decision

    # Daily cumulative cap: tightest non-null value across the chain
    daily_cap = _effective_limit([p.max_daily_usd for p in policies])
    if daily_cap is not None:
        since = utcnow() - timedelta(days=1)
        spent_today = (
            db.query(PolicyCheckLog)
            .filter(
                PolicyCheckLog.agent_key == agent_key,
                PolicyCheckLog.decision == "allowed",
                PolicyCheckLog.timestamp >= since,
            )
            .with_entities(PolicyCheckLog.amount_usd)
            .all()
        )
        total = sum(a for (a,) in spent_today) + amount_usd
        if total > daily_cap:
            decision = Decision(allowed=False, reason=f"exceeds_daily_cap:{daily_cap}")
            _log(db, agent_key, rail, amount_usd, category, decision)
            return decision

    # Velocity cap: tightest non-null value across the chain
    velocity_cap = _effective_limit([p.max_velocity_calls_per_min for p in policies])
    if velocity_cap is not None:
        since = utcnow() - timedelta(minutes=1)
        recent_calls = (
            db.query(PolicyCheckLog)
            .filter(
                PolicyCheckLog.agent_key == agent_key,
                PolicyCheckLog.decision == "allowed",
                PolicyCheckLog.timestamp >= since,
            )
            .count()
        )
        if recent_calls + 1 > velocity_cap:
            decision = Decision(allowed=False, reason=f"exceeds_velocity_cap:{velocity_cap}")
            _log(db, agent_key, rail, amount_usd, category, decision)
            return decision

    decision = Decision(allowed=True)
    _log(db, agent_key, rail, amount_usd, category, decision)
    return decision


def _log(db: Session, agent_key, rail, amount_usd, category, decision: Decision):
    entry = PolicyCheckLog(
        agent_key=agent_key,
        rail=rail,
        amount_usd=amount_usd,
        category=category,
        decision="allowed" if decision.allowed else ("escalated" if decision.escalate else "blocked"),
        reason=decision.reason,
    )
    db.add(entry)
    db.commit()
