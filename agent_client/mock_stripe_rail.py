"""
A deliberately minimal mock of a second payment rail, styled after Stripe
Issuing's card-level spend model (single call = one authorization).

This is NOT a real Stripe integration -- it exists only to prove the
policy engine's central claim: the SAME policy, checked by the SAME
PolicyGuard, governs spend across genuinely different rails. Swapping
this mock for a real `stripe.issuing.Authorization` call later doesn't
change anything about the policy engine itself -- that's the point.
"""
import random


def execute_mock_stripe_payment(amount_usd: float, merchant: str) -> dict:
    """Pretends to authorize a card payment. Always "succeeds" -- this mock
    only needs to exist so PolicyGuard has something real to call.
    """
    return {
        "rail": "stripe_issuing",
        "authorization_id": f"auth_mock_{random.randint(100000, 999999)}",
        "amount_usd": amount_usd,
        "merchant": merchant,
        "status": "authorized",
    }
