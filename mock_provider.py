"""
A tiny mock financial-data provider, standing in for a real upstream like
Polygon.io or Alpha Vantage during MVP testing. Run on port 8001.
"""
from fastapi import FastAPI
import random

app = FastAPI(title="Mock Financial Data Provider")


@app.get("/market-summary")
def market_summary():
    return {
        "ticker": "AAPL",
        "price": round(200 + random.uniform(-5, 5), 2),
        "as_of": "mock-realtime",
    }
