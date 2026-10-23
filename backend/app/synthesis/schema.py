"""Contracts for the synthesis layer. Research in, frozen strategy and order plan out."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schema import Memo, Source


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ResearchBundle(Strict):
    """What the research group hands to the synthesis group.

    Memos use the Desk `Memo` shape (per-ticker stance, confidence, note, source ids) so
    the five existing analysts and the canvas research agents can both produce them.
    `memo_paths` are the shared-workspace files the strategy record will cite.
    """

    cutoff: date
    end: date
    memos: list[Memo] = Field(min_length=1, max_length=20)
    sources: list[Source] = Field(default_factory=list, max_length=500)
    memo_paths: list[str] = Field(min_length=1, max_length=30)
    notes: str = Field(default="", max_length=4000)


class SynthesisRequest(Strict):
    name: str = Field(min_length=1, max_length=120)
    bundle: ResearchBundle
    use_model: bool = Field(
        default=True,
        description="Refine the deterministic seed with one Bedrock call; false keeps the seed",
    )


class SeedDetail(Strict):
    conviction: dict[str, float]
    seed_weights: dict[str, float]
    dropped: dict[str, str]
    clamped: list[str]


class SynthesisResult(Strict):
    strategy: dict
    seed: SeedDetail
    model_used: bool
    model_note: str = ""


class WindowResult(Strict):
    cutoff: str
    end: str
    portfolio: float
    spy: float
    equal_weight: float
    excess_vs_spy: float
    excess_vs_equal: float
    max_drawdown: float


class Significance(Strict):
    strategy_id: str
    horizon_days: int
    n_windows: int
    hit_rate_vs_spy: float
    hit_rate_vs_equal: float
    mean_excess_vs_spy: float
    mean_excess_vs_equal: float
    t_stat_vs_spy: float
    p_value_vs_spy: float
    ci95_excess_vs_spy: tuple[float, float]
    worst_drawdown: float
    windows: list[WindowResult]
    limitations: str


OrderSide = Literal["buy", "sell"]


class PlannedOrder(Strict):
    strategy_id: str
    symbol: str
    side: OrderSide
    notional: float
    client_order_id: str
    target_value: float
    current_value: float
    note: str = ""


class OrderPlan(Strict):
    strategy_id: str
    capital: float
    cash: float
    orders: list[PlannedOrder]
    blocked: list[str]
    skipped: dict[str, str]
    ready: bool
