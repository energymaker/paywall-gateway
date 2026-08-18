"""
Data models for the cross-rail agent spending policy engine.

Design principles (borrowed deliberately from how mature spend-control
products like AgentWallet structure this, and validated against how
Stripe Issuing / Coinbase Agentic Wallets think about limits):

1. Policies are SCOPED and HIERARCHICAL: account -> team -> agent.
   A child scope can only narrow what its parent allows, never widen it.
   This is what makes the system safe to delegate: handing an agent to
   a new team can never silently grant it more spending power.

2. Policies are RAIL-AGNOSTIC. A single policy (e.g. "this agent may
   spend $50/day on market-data category") is defined once and enforced
   identically whether the actual payment executes over x402, Stripe
   Issuing, or any other rail. The rail is just metadata on the
   transaction attempt, not something the policy schema needs to know
   about in advance. This is the actual product wedge: rail providers
   only enforce policy on their own rail.

3. Every check -- allowed, blocked, or escalated -- is logged. The log
   is the audit trail a compliance buyer needs, and (later) the raw
   material for a benchmark/report artifact, the same way Mercor's
   transaction/eval history became the raw material for APEX.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Policy(Base):
    """A spending policy attached to a scope in the account/team/agent
    hierarchy. Any field left null means "not constrained at this level" --
    the effective limit for an agent is the tightest non-null value found
    walking up its scope chain.
    """
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True)

    scope_type = Column(String, nullable=False)  # "account" | "team" | "agent"
    scope_id = Column(String, nullable=False, index=True)  # e.g. an agent_key or team name
    parent_policy_id = Column(Integer, ForeignKey("policies.id"), nullable=True)

    max_per_transaction_usd = Column(Float, nullable=True)
    max_daily_usd = Column(Float, nullable=True)
    max_velocity_calls_per_min = Column(Integer, nullable=True)

    allowed_categories = Column(Text, nullable=True)  # comma-separated, null = all allowed
    allowed_rails = Column(Text, nullable=True)  # comma-separated, null = all allowed

    active = Column(String, default="true")  # "true" | "false" -- soft disable without delete
    created_at = Column(DateTime, default=utcnow)

    parent = relationship("Policy", remote_side=[id])


class PolicyCheckLog(Base):
    """Append-only record of every spend attempt evaluated against policy,
    across every rail. This is the unified cross-rail audit log -- the
    single artifact no individual rail provider can produce on their own,
    because each of them only sees their own transactions.
    """
    __tablename__ = "policy_check_log"

    id = Column(Integer, primary_key=True)

    agent_key = Column(String, nullable=False, index=True)
    rail = Column(String, nullable=False)  # e.g. "x402", "stripe_issuing"
    amount_usd = Column(Float, nullable=False)
    category = Column(String, nullable=True)

    decision = Column(String, nullable=False)  # "allowed" | "blocked" | "escalated"
    reason = Column(String, nullable=True)  # which rule triggered, if blocked/escalated

    timestamp = Column(DateTime, default=utcnow)
