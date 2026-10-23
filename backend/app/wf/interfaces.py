"""Plug-in contracts for the walk-forward harness (hub D22).

Three kinds of component plug into the same point-in-time data layer and the same engine:

    Decider          research + strategy: what to hold (target weights, optional stop/target)
    ExecutionPolicy  how to get there: weights + current holdings -> orders
    Evaluator        frozen weights + dates -> metrics (mirrors the blind backtester's input)

The harness runs a decision date in two phases so cost, caching and leakage control stay simple:

    phase 1  Decider.decide(ctx)        ctx.portfolio is NOT used by stateless deciders, so every date
                                        can run in parallel and replies are cached on disk
    phase 2  ExecutionPolicy.plan(...)  runs INSIDE the simulation loop, because order planners need
                                        the current holdings (ctx.portfolio) at the decision close

Leakage rules every component must obey (enforced by `conformance.py`):
    * read data only through ``ctx.pit`` (already bound to ``ctx.as_of``); never import
      ``backend.app.wf.market``, ``data.prices_full`` or ``data.last_close``;
    * output is a pure function of (ctx, cached replies): poisoning every data row after
      ``as_of`` must not change it;
    * tickers outside ``ctx.universe`` and negative weights are invalid.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schema import Metrics, Source
from backend.app.wf.config import WfConfig
from backend.app.wf.schemas import DecisionOrders


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Account state at the decision close, in the shape order planners expect.

    ``positions`` and ``shares`` hold only held names. ``open_orders`` is always empty in a
    replay: day orders lapse and protective orders are modelled inside the engine.
    """

    as_of: str
    equity: float
    cash: float
    positions: Mapping[str, float] = field(default_factory=dict)  # ticker -> market value ($)
    shares: Mapping[str, float] = field(default_factory=dict)
    open_orders: tuple = ()

    def weight(self, ticker: str) -> float:
        return self.positions.get(ticker, 0.0) / self.equity if self.equity > 0 else 0.0

    def as_broker_snapshot(self) -> dict:
        """The dict shape `backend.app.synthesis.orders.plan_orders` reads (Alpaca-like)."""
        return {
            "account": {
                "equity": self.equity,
                "cash": self.cash,
                "status": "ACTIVE",
                "trading_blocked": False,
                "account_blocked": False,
            },
            "positions": [
                {"symbol": t, "market_value": v, "qty": self.shares.get(t, 0.0)}
                for t, v in sorted(self.positions.items())
            ],
            "open_orders": list(self.open_orders),
        }


class PitView(Protocol):
    """`PitData` bound to one decision date: methods take no date, so none can be asked for."""

    as_of: str

    def evidence(self, analyst: str, universe: Sequence[str]) -> tuple[str, list[Source]]: ...

    def execution_context(self, tickers: Sequence[str]) -> dict[str, dict]: ...

    def last_close(self, ticker: str) -> float: ...


@dataclass(frozen=True)
class DecisionContext:
    as_of: str
    universe: tuple[str, ...]
    pit: PitView
    portfolio: PortfolioSnapshot
    cfg: WfConfig
    contaminated: bool = False
    masker: Any = None


class TargetBook(BaseModel):
    """Decider output. Weights are fractions of equity, long-only, sum <= 1 (rest is cash)."""

    model_config = ConfigDict(extra="forbid")

    decision_date: str
    weights: dict[str, float]
    stop_pct: dict[str, float] = Field(default_factory=dict)
    target_pct: dict[str, float] = Field(default_factory=dict)
    rationale: str = ""
    notes: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict, description="JSON-safe: memos, sources, plan")


class EvalResult(BaseModel):
    """Evaluator output, the shape of the blind backtester's result plus the assumptions."""

    model_config = ConfigDict(extra="forbid")

    cutoff: str
    end: str
    portfolio: Metrics
    benchmark: Metrics  # SPY buy-and-hold
    equal_weight: Metrics | None = None
    assumptions: list[str] = Field(default_factory=list)
    equity: dict[str, list] | None = None  # {"dates": [...], "portfolio": [...], ...} when available


@runtime_checkable
class Decider(Protocol):
    name: str
    version: str
    stateless: ClassVar[bool]  # True: output depends only on ctx.as_of/pit, safe to parallelise and cache

    def decide(self, ctx: DecisionContext) -> TargetBook: ...


@runtime_checkable
class ExecutionPolicy(Protocol):
    name: str
    version: str

    def plan(self, ctx: DecisionContext, book: TargetBook) -> DecisionOrders:
        """Orders for the next session. May read ``ctx.portfolio``. Tickers not mentioned keep
        their position. Must not look at anything but ctx and book."""
        ...


@runtime_checkable
class Evaluator(Protocol):
    name: str
    version: str

    def evaluate(self, weights: Mapping[str, float], cutoff: str, end: str) -> EvalResult: ...


class ComponentSpec(BaseModel):
    """How a run names a component: a registered name or ``module:Class``, plus parameters."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    params: dict[str, Any] = Field(default_factory=dict)
