Financial Data Paywall Gateway + Cross-Rail Policy Engine

A paywall-as-a-service layer for financial and alt-data providers, plus a spending policy engine that governs what an AI agent can spend across different payment rails.

Two things live in this repo:

Paywall gateway (Day 1-4): lets a data provider wrap any API endpoint, set a price, and get paid per call by AI agents using an x402-style HTTP 402 flow.
Policy engine (Day 5): lets an enterprise set one spending policy for an agent, enforced the same way no matter which payment rail that agent uses.
Part 1: Paywall gateway
What's built and tested
402 challenge/response flow. An agent hits a paid endpoint with no payment proof and gets a 402 back with the price. It retries with proof and gets the real data.
Provider and endpoint config. Set up pricing with two POST calls, no code required.
Transaction ledger. Every call gets logged: challenged, paid, blocked, or failed. This is the audit trail.
Velocity-based reputation logging. If an agent calls too fast in a rolling window, it gets flagged. This is the seed of a future trust layer.
Public directory. A live list of paywalled endpoints, the start of a discovery layer agents could browse.
Provider dashboard. Revenue, call volume, unique paying agents.

All of this runs end to end in test_flow.py against a mock financial data provider.

Running it yourself
bash
python -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate
pip install -r requirements.txt

# Terminal 1: mock upstream financial data provider
uvicorn mock_provider:app --port 8001

# Terminal 2: the gateway itself
uvicorn app.main:app --port 8000

# Terminal 3: run the full simulated flow
python test_flow.py

Then open http://127.0.0.1:8000/directory to see the public listing, or http://127.0.0.1:8000/docs for interactive API docs (FastAPI generates these automatically).

Real x402 verification

app/x402_integration.py uses the official x402 PyPI SDK, the same one referenced in Coinbase's docs. It's not a stub. It registers a real EVM "exact" scheme for USDC on Base, builds real x402 payment requirements for the 402 response, and verifies real payment headers against the public facilitator at https://x402.org/facilitator.

In this build environment specifically, network access is restricted to a fixed allow-list that doesn't include x402.org. So the facilitator call fails fast (a 4-second timeout by design) and the gateway falls back to the simpler stub behavior so the rest of the system keeps working end to end. You'll see this in the server log:

Could not reach x402 facilitator (https://x402.org/facilitator) within 4.0s.
Falling back to stub verification for this run.
Error: Facilitator get_supported failed (403): Host not in allowlist: x402.org.

That's a limitation of this build environment, not a bug in the integration. Deploy this anywhere with normal outbound network access (your own machine, a VPS, a cloud function) and it talks to the real facilitator with no code changes.

What's still stubbed here (honest list)
Wallet signing isn't wired into the agent side of this repo. This repo is the server (resource/paywall) side of x402. An agent that actually pays needs its own wallet plus the x402 client SDK (x402.client) to sign and attach a real payment header. That's the piece to build or wire into a test agent once you have real network access to verify against. (The policy engine's agent_client/ folder does include a real wallet signer, see Part 2 below.)
Real financial data provider: no new code needed. upstream_url on an Endpoint is just a config field. Point it at a real API, like Alpha Vantage's demo endpoint or Polygon.io with a free-tier key, instead of the mock provider when you register the endpoint.
Velocity threshold is a placeholder (more than 10 calls in 30 seconds). Tune this once you have real usage data. Call patterns vary a lot by use case.
No auth or API keys yet on the provider config endpoints. Fine for local testing, not for a public deployment.
Part 2: Cross-rail spending policy engine

The gateway above is the supply side: it helps providers charge agents. This is the demand side: an enterprise-facing policy layer that governs what an agent can spend, enforced the same way no matter which payment rail it uses.

app/policy_models.py and app/policy_engine.py implement a scoped, narrowing-only policy hierarchy: account, then team, then agent. There are five enforcement checks: per-transaction cap, daily cumulative cap, velocity (calls per minute), category allowlist, and rail allowlist. A child scope can only tighten what its parent allows, never widen it. So handing an agent to a new team can never quietly give it more spending power.

agent_client/policy_client.py is the actual product: a PolicyGuard that wraps any rail's payment call with a check before spend happens. Policy is enforced before a payment attempt reaches the rail, not audited after the fact.

The core claim, proven in demo_cross_rail.py

One agent has a $10/day cap. It spends $7 through x402. It then tries to spend $5 through a second, unrelated rail (a Stripe Issuing-style mock in agent_client/mock_stripe_rail.py). The second attempt gets blocked. Not because that rail has its own $10 cap (it has no idea what the agent spent on x402), but because the shared PolicyGuard already knows $7 was spent today, on any rail.

Neither Coinbase's agent wallet limits nor Stripe Issuing's own card limits can do this on their own, since each only sees its own rail.

Run it:

python demo_cross_rail.py

Unit tests covering all five checks plus the hierarchy:

python test_policy_engine.py

There's also a combined demo (record_demo.py) that generates a real Ethereum wallet, signs a real message with it, runs the full test suite, and runs the cross-rail proof, all in one script, useful for recording or screen-sharing.

What's still stubbed here (honest list)
The second rail is a mock, not a real Stripe Issuing integration. The policy logic tested against it is real. The rail call itself is not, yet.
The policy engine runs in-process against the same SQLite database as the demo and tests. A real deployment would run this as its own service that an enterprise's agent infrastructure calls over the network, with the x402 flow in agent_client/agent_test.py wired to check policy before it signs, not just alongside it.
No dashboard yet for configuring policies or browsing the audit log. PolicyCheckLog rows exist and are queryable, but there's no UI on top of them.
Suggested next steps
Replace the mock Stripe rail with a real Stripe Issuing test-mode integration.
Wire PolicyGuard.attempt() directly into agent_test.py's real x402 signing flow, so the cross-rail demo runs on live signing instead of a stand-in.
Add a minimal read-only endpoint exposing PolicyCheckLog so the audit trail is visible over HTTP, not just queryable in-process.
Deploy the gateway somewhere with open outbound network access and confirm a real facilitator round-trip.
Point one real endpoint at a real financial or alt-data API.
Add basic auth to the provider config endpoints before onboarding a real outside provider.
