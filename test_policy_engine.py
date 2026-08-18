"""
Tests for the cross-rail policy engine core.

Run with: python test_policy_engine.py
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.policy_models import Policy
from app.policy_engine import evaluate


def fresh_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_default_deny_with_no_policy():
    db = fresh_db()
    d = evaluate(db, agent_key="agent_a", rail="x402", amount_usd=1.0)
    assert d.allowed is False
    assert d.reason == "no_policy_configured"
    print("PASS: default-deny with no policy configured")


def test_account_level_cap_applies_to_unconfigured_agent():
    db = fresh_db()
    db.add(Policy(scope_type="account", scope_id="default", max_per_transaction_usd=10.0))
    db.commit()

    d = evaluate(db, agent_key="agent_a", rail="x402", amount_usd=5.0)
    assert d.allowed is True

    d2 = evaluate(db, agent_key="agent_a", rail="x402", amount_usd=50.0)
    assert d2.allowed is False
    assert "exceeds_per_transaction_cap" in d2.reason
    print("PASS: account-level policy applies to an agent with no agent-level policy")


def test_narrowing_only_child_cannot_widen_parent():
    db = fresh_db()
    # Account allows up to $100/tx, but this specific agent is capped tighter at $5.
    db.add(Policy(scope_type="account", scope_id="default", max_per_transaction_usd=100.0))
    db.add(Policy(scope_type="agent", scope_id="agent_b", max_per_transaction_usd=5.0))
    db.commit()

    d = evaluate(db, agent_key="agent_b", rail="x402", amount_usd=8.0)
    assert d.allowed is False
    assert "exceeds_per_transaction_cap:5.0" in d.reason
    print("PASS: tightest limit in the chain wins (child cannot widen what parent allows)")


def test_cross_rail_daily_cap_is_shared():
    """The whole point of the product: spend on rail A counts against the
    same daily cap as spend on rail B, because it's the same agent."""
    db = fresh_db()
    db.add(Policy(scope_type="account", scope_id="default", max_daily_usd=10.0))
    db.commit()

    d1 = evaluate(db, agent_key="agent_c", rail="x402", amount_usd=6.0)
    assert d1.allowed is True

    # Different rail, same agent, same day -- should still count against the cap.
    d2 = evaluate(db, agent_key="agent_c", rail="stripe_issuing", amount_usd=6.0)
    assert d2.allowed is False
    assert "exceeds_daily_cap" in d2.reason
    print("PASS: daily cap is enforced cumulatively across different rails")


def test_category_allowlist():
    db = fresh_db()
    db.add(Policy(scope_type="account", scope_id="default", allowed_categories="market-data,news"))
    db.commit()

    ok = evaluate(db, agent_key="agent_d", rail="x402", amount_usd=1.0, category="market-data")
    assert ok.allowed is True

    blocked = evaluate(db, agent_key="agent_d", rail="x402", amount_usd=1.0, category="compute")
    assert blocked.allowed is False
    assert "category_not_allowed" in blocked.reason
    print("PASS: category allowlist enforced")


def test_velocity_cap():
    db = fresh_db()
    db.add(Policy(scope_type="account", scope_id="default", max_velocity_calls_per_min=2))
    db.commit()

    r1 = evaluate(db, agent_key="agent_e", rail="x402", amount_usd=0.01)
    r2 = evaluate(db, agent_key="agent_e", rail="x402", amount_usd=0.01)
    r3 = evaluate(db, agent_key="agent_e", rail="x402", amount_usd=0.01)

    assert r1.allowed and r2.allowed
    assert r3.allowed is False
    assert "exceeds_velocity_cap" in r3.reason
    print("PASS: velocity cap enforced within a rolling 1-minute window")


if __name__ == "__main__":
    test_default_deny_with_no_policy()
    test_account_level_cap_applies_to_unconfigured_agent()
    test_narrowing_only_child_cannot_widen_parent()
    test_cross_rail_daily_cap_is_shared()
    test_category_allowlist()
    test_velocity_cap()
    print("\nAll policy engine tests passed.")
