"""
Simulates the full flow end-to-end against the running gateway (port 8000)
and mock provider (port 8001):
  1. Register a provider ("acme-data") and a paywalled endpoint.
  2. Agent calls it without payment -> expects HTTP 402.
  3. Agent retries with a payment proof -> expects real data back.
  4. Fire a burst of calls to trigger the velocity flag.
  5. Print the provider's dashboard and the public directory.

Run:
  terminal 1: uvicorn mock_provider:app --port 8001
  terminal 2: uvicorn app.main:app --port 8000
  terminal 3: python test_flow.py
"""
import httpx

GATEWAY = "http://127.0.0.1:8000"

client = httpx.Client(timeout=10.0)

print("1) Registering provider...")
r = client.post(f"{GATEWAY}/providers", json={
    "slug": "acme-data",
    "name": "Acme Financial Data",
    "contact_email": "hello@acmedata.example",
})
print(r.status_code, r.json())

print("\n2) Adding a paywalled endpoint...")
r = client.post(f"{GATEWAY}/providers/acme-data/endpoints", json={
    "path": "market-summary",
    "description": "Real-time single-ticker price summary",
    "price_usd": 0.002,
    "upstream_url": "http://127.0.0.1:8001/market-summary",
})
print(r.status_code, r.json())

print("\n3) Agent calls without payment -> expect 402...")
r = client.get(
    f"{GATEWAY}/pay/acme-data/market-summary",
    headers={"X-Agent-Key": "agent-alpha"},
)
print(r.status_code, r.json())

print("\n4) Agent retries with payment proof -> expect data back...")
r = client.get(
    f"{GATEWAY}/pay/acme-data/market-summary",
    headers={"X-Agent-Key": "agent-alpha", "X-Payment-Proof": "sig_test_123"},
)
print(r.status_code, r.json())

print("\n5) Firing a burst of 12 calls to trigger the velocity flag...")
for i in range(12):
    r = client.get(
        f"{GATEWAY}/pay/acme-data/market-summary",
        headers={"X-Agent-Key": "agent-alpha", "X-Payment-Proof": "sig_test_123"},
    )
last = r.json()
print("last call velocity_flagged:", last.get("velocity_flagged"))

print("\n6) Provider dashboard:")
r = client.get(f"{GATEWAY}/providers/acme-data/dashboard")
print(r.status_code, r.json())

print("\n7) Public directory:")
r = client.get(f"{GATEWAY}/directory")
print(r.status_code, r.json())
