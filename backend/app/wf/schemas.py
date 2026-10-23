"""Contracts between the three parts of the walk-forward harness.

    pit.py      (data)    -> evidence + execution context, strictly point-in-time
    engine.py   (engine)  -> deterministic daily-bar simulator, no LLM
    stages.py   (agents)  -> research -> strategy -> execution, one decision date at a time

All agents are STATELESS: a stage output is a function of the decision date only (plus
the cached LLM replies). Portfolio continuity (current holdings, no-trade band) is the
engine's job, which is what lets every decision date run in parallel and lets ablations
re-run only the engine on cached stage outputs.

Decision timing: a decision dated ``date`` is made after that day's close using data
available at that moment. Orders become live on the NEXT trading day's open.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.app.schema import Memo, Source

EntryKind = Literal["market_open", "limit", "skip"]


# --------------------------------------------------------------------------- engine input


class OrderIntent(BaseModel):
    """What the engine is asked to do for one ticker. Long-only.

    target_weight: desired fraction of total equity (marked at the decision date's close).
    entry:
      market_open  trade to the target at the next open (plus slippage against us).
      limit        buy only if the next session trades at or through limit_price; fill at
                   min(open, limit). Sells use the mirror rule (max(open, limit)).
      skip         do not trade this ticker this week (keep any position and its stops).
    skip_if_gap_pct: cancel an entry/add if the next open is more than this fraction
                   ABOVE the decision close (buys) or BELOW it (sells), e.g. 0.03.
    stop_price / target_price: absolute prices for protective orders on the resulting
                   position, live until the next decision. Stop fills at min(open, stop)
                   if it gaps through, target at max(open, target); if both trigger in
                   one bar the stop wins.
    """

    ticker: str
    target_weight: float = Field(ge=0.0, le=1.0)
    entry: EntryKind = "market_open"
    limit_price: float | None = None
    skip_if_gap_pct: float | None = Field(default=None, ge=0.0)
    stop_price: float | None = None
    target_price: float | None = None


class DecisionOrders(BaseModel):
    """Everything decided on one date. Tickers not mentioned keep their position and
    protective orders unchanged. A date with no DecisionOrders changes nothing."""

    date: str
    intents: list[OrderIntent]
    contaminated: bool = False


# ------------------------------------------------------------------------- stage outputs


class TickerPlan(BaseModel):
    ticker: str
    target_weight: float = Field(ge=0.0, le=1.0)
    stop_pct: float = Field(gt=0.0, lt=1.0, description="stop distance below the decision close, as a fraction")
    target_pct: float | None = Field(default=None, gt=0.0, description="profit target above the decision close")
    horizon_weeks: int = Field(default=4, ge=1, le=26)
    conviction: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str
    changes_my_mind: str
    memo_sources: list[str] = Field(default_factory=list, description="Source ids from the memos")


class TradePlan(BaseModel):
    """Stage 2 output. Weights sum to <= 1, the remainder is cash."""

    decision_date: str
    strategy_name: str
    summary: str
    plans: list[TickerPlan]


class OrderDraft(BaseModel):
    """Stage 3 output for one ticker: HOW to execute, not what to hold."""

    ticker: str
    entry: EntryKind = "market_open"
    limit_offset_atr: float | None = Field(
        default=None, ge=0.0, le=3.0, description="limit = close -/+ this many ATRs (buys below, sells above)"
    )
    skip_if_gap_pct: float | None = Field(default=None, ge=0.0, le=0.2)
    note: str = ""


class ExecutionPlan(BaseModel):
    decision_date: str
    orders: list[OrderDraft]
    notes: str = ""


# --------------------------------------------------------------------------- persistence


class DecisionRecord(BaseModel):
    """Everything one decision date produced, written to reports/wf/<run>/decisions/<date>.json."""

    decision_date: str
    contaminated: bool
    model_id: str
    memos: list[Memo]
    abstained_analysts: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    plan: TradePlan
    execution: ExecutionPlan
    orders: DecisionOrders
    masked: bool = False
    notes: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    run_id: str
    created: str
    config: dict
    git_sha: str | None = None
    data_hashes: dict[str, str] = Field(default_factory=dict)
    prompt_hash: str | None = None
    window: dict = Field(default_factory=dict)
    contaminated: bool = False
    notes: list[str] = Field(default_factory=list)
