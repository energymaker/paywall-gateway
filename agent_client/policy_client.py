"""
The policy-enforced agent client: the actual product surface for the
cross-rail spending policy engine.

In a real deployment this wrapper would run as a small local proxy or SDK
inside the enterprise's own agent infrastructure, calling out to a hosted
policy service. For this MVP it imports the engine directly (same process,
same DB) -- the logic being proven is identical either way; only the
transport changes later.

The key idea: whatever rail-specific client you already have (the real
x402 client, a Stripe Issuing client, anything), you wrap its "attempt to
pay" call with `guard.check(...)` first. If blocked, you never even reach
the rail's own signing/execution step -- policy is enforced BEFORE spend,
not audited after the fact.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.policy_engine import evaluate, Decision


@dataclass
class SpendAttemptResult:
    decision: Decision
    executed: bool
    rail_result: Optional[dict] = None


class PolicyGuard:
    """One guard per agent (or per enterprise deployment), reused across
    however many different rails that agent pays through.
    """

    def __init__(self, db: Session, agent_key: str, team: Optional[str] = None):
        self.db = db
        self.agent_key = agent_key
        self.team = team

    def attempt(
        self,
        rail: str,
        amount_usd: float,
        execute_payment: Callable[[], dict],
        category: Optional[str] = None,
    ) -> SpendAttemptResult:
        """Check policy first; only call `execute_payment()` -- the actual
        rail-specific signing/settlement call -- if allowed. This ordering
        is the whole point: policy is a pre-spend gate, not a post-hoc log.
        """
        decision = evaluate(
            self.db,
            agent_key=self.agent_key,
            rail=rail,
            amount_usd=amount_usd,
            category=category,
            team=self.team,
        )

        if not decision.allowed:
            return SpendAttemptResult(decision=decision, executed=False)

        result = execute_payment()
        return SpendAttemptResult(decision=decision, executed=True, rail_result=result)
