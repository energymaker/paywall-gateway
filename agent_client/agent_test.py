"""
The buyer side of x402: an "agent" that calls a paywalled endpoint, gets
challenged with a real HTTP 402, signs a real payment using a real wallet
(via eth-account), and retries with the signed proof attached.

This uses the official `x402` SDK's client (`x402.client.x402Client` +
`x402.http.x402HTTPClient`) -- the exact counterpart to the server-side
`x402ResourceServer` wired into the gateway in `app/x402_integration.py`.
Together they are a complete, real x402 round trip: one process paying,
one process getting paid.

SANDBOX NOTE: signing a payment happens entirely locally and needs no
network access -- that part is fully real and testable here. What can't
be tested in this sandbox is the facilitator actually settling/verifying
that signed payment on-chain (facilitator hosts are outside this
environment's network allowlist, same limitation noted in
`x402_integration.py`). This script demonstrates real payload creation
and signing, then calls the gateway and shows you exactly what happens
at each stage.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from x402.client import x402Client
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.http.x402_http_client import x402HTTPClient
from x402.http.constants import PAYMENT_REQUIRED_HEADER

from agent_client.wallet_signer import EthAccountSigner

GATEWAY = "http://127.0.0.1:8000"


async def call_paid_endpoint(provider_slug: str, endpoint_path: str, agent_key: str, wallet: EthAccountSigner):
    url = f"{GATEWAY}/pay/{provider_slug}/{endpoint_path}"
    headers = {"X-Agent-Key": agent_key}

    # Build the real x402 client, registered for the same EVM "exact" scheme
    # the gateway's server is registered for.
    core_client = x402Client()
    core_client.register("eip155:8453", ExactEvmClientScheme(signer=wallet))
    http_client = x402HTTPClient(core_client)

    async with httpx.AsyncClient(timeout=15.0) as http:
        print(f"1) Calling {url} with no payment (expect 402)...")
        resp = await http.get(url, headers=headers)
        print(f"   -> {resp.status_code}")

        if resp.status_code != 402:
            print("   Not a 402 -- nothing to pay for, printing response and stopping.")
            print("   ", resp.json())
            return

        if PAYMENT_REQUIRED_HEADER not in resp.headers:
            # This is the sandbox fallback shape from Day 1-4 (facilitator
            # unreachable server-side), not a real spec-compliant challenge.
            print("   Server sent the sandbox fallback 402 shape (no real x402")
            print("   PAYMENT-REQUIRED header) -- this happens because the")
            print("   gateway's own facilitator call failed in this network-")
            print("   restricted sandbox. Body:", resp.json())
            print("   Retrying with a plain non-empty proof, matching the")
            print("   gateway's documented stub-mode fallback behaviour...")
            resp2 = await http.get(
                url, headers={**headers, "X-Payment-Proof": "sig_from_real_wallet_" + wallet.address}
            )
            print(f"   -> {resp2.status_code} {resp2.json()}")
            return

        print(f"2) Got a real x402 PAYMENT-REQUIRED header. Wallet: {wallet.address}")
        print("   Signing a real EIP-712 payment payload locally (no network needed)...")

        try:
            payment_headers, payment_payload = await http_client.handle_402_response(
                dict(resp.headers), resp.content
            )
        except Exception as e:
            print(f"   Signing/encoding failed: {e}")
            return

        print("   Signed payload created. Retrying the call with the real")
        print("   signed X-PAYMENT header attached...")
        resp3 = await http.get(url, headers={**headers, **payment_headers})
        print(f"   -> {resp3.status_code}")
        print("   ", resp3.json() if resp3.headers.get("content-type", "").startswith("application/json") else resp3.text)


if __name__ == "__main__":
    provider = sys.argv[1] if len(sys.argv) > 1 else "acme-data"
    endpoint = sys.argv[2] if len(sys.argv) > 2 else "market-summary"

    # A fresh, randomly generated wallet -- real key, real signature, but
    # holds no funds. Fine for proving the flow; swap for a funded wallet's
    # private key (loaded from an env var, never hardcoded) once you're
    # testing against a real facilitator with real settlement.
    wallet = EthAccountSigner.generate()
    print(f"Generated test wallet: {wallet.address}\n")

    asyncio.run(call_paid_endpoint(provider, endpoint, "agent-real-client", wallet))
