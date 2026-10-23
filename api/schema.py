"""The contract between the UI, the data/backtest lane and the agents lane.

Keep this file in sync with web/src/types.ts. Any field added here must be added there.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Stance = Literal["long", "neutral", "avoid"]
Analyst = Literal["technical", "fundamentals", "macro", "sentiment", "geopolitics"]
SourceKind = Literal["sec", "fred", "gdelt", "price"]
Baseline = Literal["equal_weight", "spy"]


class RunRequest(BaseModel):
    universe: list[str]
    cutoff: str = Field(description="ISO date. No data after this date reaches any agent.")
    baseline: Baseline = "equal_weight"


class Source(BaseModel):
    id: str
    kind: SourceKind
    title: str
    date: str = Field(description="ISO date, must be <= cutoff")
    url: str | None = None
    excerpt: str


class View(BaseModel):
    ticker: str
    stance: Stance
    confidence: float = Field(ge=0, le=1)
    note: str
    sources: list[str] = Field(description="Source ids")


class Memo(BaseModel):
    analyst: Analyst
    date: str
    headline: str
    body: str
    views: list[View]


class Weight(BaseModel):
    ticker: str
    weight: float = Field(ge=0, le=1)
    rationale: str
    changes_my_mind: str
    analyst_influence: dict[Analyst, float] = Field(
        description="How much each analyst moved this position, 0..1, informal"
    )


class Equity(BaseModel):
    dates: list[str]
    portfolio: list[float]
    equal_weight: list[float]
    spy: list[float]


class Metrics(BaseModel):
    total_return: float
    cagr: float
    max_drawdown: float
    sharpe: float


class RunMetrics(BaseModel):
    portfolio: Metrics
    baseline: Metrics


class RunResponse(BaseModel):
    universe: list[str]
    cutoff: str
    baseline: Baseline
    sources: list[Source]
    memos: list[Memo]
    weights: list[Weight]
    equity: Equity
    metrics: RunMetrics
