"""Watchdog-local shapes.

PRD-level Order, Fill, Mandate and ModeratorEvent contracts are not in `schema.py` yet.
These stay here until the agent-loop lane adopts shared ones (proposed in D19). All
fractions are 0..1, money is dollars, times are ISO 8601 UTC strings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

RiskBand = Literal["conservative", "balanced", "aggressive"]
Side = Literal["buy", "sell"]
Decision = Literal["approve", "block"]
RuleSeverity = Literal["pass", "near_miss", "block", "info"]
EventSeverity = Literal["info", "warn", "critical"]


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class WatchOrder(BaseModel):
    symbol: str
    side: Side
    notional: float
    qty: float | None = None
    price: float | None = Field(
        default=None, description="Limit or expected fill price. None for market notional orders."
    )
    client_order_id: str = ""
    strategy_id: str | None = None
    agent_id: str | None = None
    time: str = Field(default_factory=utcnow)


class WatchMandate(BaseModel):
    client: str = "default board"
    risk: RiskBand = "balanced"
    trading_allowed: bool = False
    universe: list[str]
    capital: float | None = None
    max_position: float = Field(description="Largest single position, fraction of capital")
    max_drawdown: float = Field(description="Largest tolerated drawdown from peak equity")
    max_order_notional: float | None = None
    max_daily_orders: int | None = None
    # None means the risk band's watchdog guardrail applies (see rules.GUARDRAILS).
    max_concentration: float | None = None
    max_daily_turnover: float | None = None
    max_order_fraction: float | None = None
    price_band: float | None = None


class PastOrder(BaseModel):
    time: str
    symbol: str
    side: Side
    notional: float
    client_order_id: str = ""
    status: str = "submitted"


class LiveMarket(BaseModel):
    """Venue data fetched right before the review. `error` set means the gate fell back."""

    source: str
    error: str | None = None
    tradable: dict[str, bool] = Field(default_factory=dict)
    last_trade: dict[str, float] = Field(default_factory=dict)
    prev_close: dict[str, float] = Field(default_factory=dict)
    market_open: bool | None = None
    equity_peak: float | None = None


class WatchPortfolio(BaseModel):
    equity: float
    cash: float
    positions: dict[str, float] = Field(default_factory=dict, description="symbol -> market value")
    own_positions: dict[str, float] | None = Field(
        default=None, description="symbol -> market value this fund itself filled; caps its sells"
    )
    peak_equity: float | None = None
    last_close: dict[str, float] = Field(default_factory=dict)
    recent_orders: list[PastOrder] = Field(default_factory=list)
    backtest_verdict: str | None = None
    backtest_max_drawdown: float | None = None
    live: LiveMarket | None = None


class RuleResult(BaseModel):
    rule: str
    severity: RuleSeverity
    message: str
    value: float | None = None
    limit: float | None = None


class Verdict(BaseModel):
    decision: Decision
    reason: str
    blocked_by: list[str]
    near_misses: list[str]
    rules: list[RuleResult]
    order: WatchOrder
    client: str
    risk: RiskBand
    reviewed_at: str = Field(default_factory=utcnow)


class ModeratorEvent(BaseModel):
    time: str = Field(default_factory=utcnow)
    kind: str = Field(
        description="order_blocked, near_miss, runaway, retry_loop, claim, position, uncertain_order, halt, outcome"
    )
    severity: EventSeverity
    subject: str = Field(description="Agent id, strategy id, order id or symbol the event is about")
    message: str
    details: dict = Field(default_factory=dict)
