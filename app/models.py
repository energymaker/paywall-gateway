"""
Database models for the paywall-as-a-service gateway.

Design note: reputation/discovery tables are included from day one, not
bolted on later, so every transaction from the first day of usage feeds
the data that will eventually power agent trust scores and the public
discovery directory.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
)
from sqlalchemy.orm import relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Agent(Base):
    """An AI agent (or the developer/company behind it) that pays for data."""
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)
    agent_key = Column(String, unique=True, index=True, nullable=False)  # public identifier
    name = Column(String, nullable=True)
    wallet_address = Column(String, nullable=True)  # stablecoin wallet, if known
    created_at = Column(DateTime, default=utcnow)

    transactions = relationship("Transaction", back_populates="agent")
    reputation_events = relationship("ReputationEvent", back_populates="agent")


class Provider(Base):
    """A financial/alt-data provider selling access to agents."""
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, index=True, nullable=False)  # used in URL path
    name = Column(String, nullable=False)
    contact_email = Column(String, nullable=True)
    payout_wallet = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    endpoints = relationship("Endpoint", back_populates="provider")


class Endpoint(Base):
    """A single paywalled data endpoint a provider exposes, with its price."""
    __tablename__ = "endpoints"

    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    path = Column(String, nullable=False)  # e.g. "market-summary"
    description = Column(String, nullable=True)
    price_usd = Column(Float, nullable=False)  # price per call, e.g. 0.002
    upstream_url = Column(String, nullable=False)  # where the real data lives
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    provider = relationship("Provider", back_populates="endpoints")
    transactions = relationship("Transaction", back_populates="endpoint")

    @property
    def full_path(self):
        return f"{self.provider.slug}/{self.path}"


class Transaction(Base):
    """Every call attempt through the gateway — paid or not, success or blocked.

    This is the core ledger AND the raw material for the future reputation
    layer: which agents pay reliably, which providers get repeat traffic.
    """
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)  # null if unpaid/unknown agent
    endpoint_id = Column(Integer, ForeignKey("endpoints.id"), nullable=False)
    amount_usd = Column(Float, nullable=False)
    status = Column(String, nullable=False)  # "challenged" | "paid" | "blocked" | "failed"
    payment_proof = Column(String, nullable=True)  # signature/token presented
    timestamp = Column(DateTime, default=utcnow)

    agent = relationship("Agent", back_populates="transactions")
    endpoint = relationship("Endpoint", back_populates="transactions")


class ReputationEvent(Base):
    """Anomaly / trust-relevant events, logged from day one even before any
    scoring model exists. This is what makes the reputation layer buildable
    later without re-collecting history.
    """
    __tablename__ = "reputation_events"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    event_type = Column(String, nullable=False)  # e.g. "velocity_spike", "repeat_identical_query"
    detail = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utcnow)

    agent = relationship("Agent", back_populates="reputation_events")
