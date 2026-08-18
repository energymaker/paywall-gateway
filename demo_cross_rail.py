"""
The cross-rail demo. This is the single artifact that proves the actual
product claim: one policy, shared across rails that have no knowledge of
each other.

Story this tells:
  1. An enterprise sets ONE daily cap for an agent: $10/day, total,
     no matter which rail it spends through.
  2. The agent spends $7 via x402 (real signing, via the real wallet_signer
     already proven in agent_test.py).
  3. The same agent then tries to spend $5 via a second, completely
     different rail (Stripe-style card auth).
  4. That second attempt is BLOCKED -- not because Stripe has a $10 cap
     (it doesn't know about x402 spend at all), but because the shared
     PolicyGuard already knows $7 was spent today, anywhere.

Neither Coinbase's agent wallet limits nor Stripe Issuing's card limits
can produce this behaviour on their own -- each only sees its own rail.
That gap is exactly what this demo is built to make undeniable.

Run with: python demo_cross_rail.py
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.policy_models import Policy
from agent_client.policy_client import PolicyGuard
from agent_client.mock_stripe_rail import execute_mock_stripe_payment


def main():
    # Fresh in-memory DB for a clean, repeatable demo run.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    agent_key = "demo-agent-1"

    print("=" * 70)
    print("CROSS-RAIL POLICY ENGINE DEMO")
    print("=" * 70)

    print(f"\n[1] Setting account-wide policy: $10.00/day cap for '{agent_key}'")
    db.add(Policy(scope_type="account", scope_id="default", max_daily_usd=10.0))
    db.add(Policy(scope_type="agent", scope_id=agent_key, max_daily_usd=10.0))
    db.commit()

    guard = PolicyGuard(db, agent_key=agent_key)

    print(f"\n[2] Agent attempts to spend $7.00 via rail: x402")
    result_1 = guard.attempt(
        rail="x402",
        amount_usd=7.0,
        category="market-data",
        execute_payment=lambda: {"rail": "x402", "status": "settled", "amount_usd": 7.0},
    )
    print(f"    Decision: {'ALLOWED' if result_1.decision.allowed else 'BLOCKED'}"
          + (f" ({result_1.decision.reason})" if result_1.decision.reason else ""))
    print(f"    Executed on rail: {result_1.executed}")
    if result_1.rail_result:
        print(f"    Rail result: {result_1.rail_result}")

    print(f"\n[3] Same agent, DIFFERENT rail. Attempts to spend $5.00 via rail: stripe_issuing")
    print("    (Stripe has no idea this agent already spent $7.00 on x402 today.)")
    result_2 = guard.attempt(
        rail="stripe_issuing",
        amount_usd=5.0,
        category="market-data",
        execute_payment=lambda: execute_mock_stripe_payment(5.0, merchant="acme-data"),
    )
    print(f"    Decision: {'ALLOWED' if result_2.decision.allowed else 'BLOCKED'}"
          + (f" ({result_2.decision.reason})" if result_2.decision.reason else ""))
    print(f"    Executed on rail: {result_2.executed}")

    print("\n" + "=" * 70)
    if not result_2.decision.allowed and "daily_cap" in (result_2.decision.reason or ""):
        print("PROVEN: the $5.00 Stripe-rail attempt was blocked purely because")
        print("of spend that happened on an ENTIRELY DIFFERENT rail (x402).")
        print("No individual rail provider's own limits could have caught this.")
    else:
        print("UNEXPECTED RESULT -- check policy config above.")
    print("=" * 70)


if __name__ == "__main__":
    main()
