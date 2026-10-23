"""Chart-ready response for one fund (read-only). Exactly the contract the frontend draws."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyInfo(Strict):
    id: str
    name: str
    author: str | None = None
    created_at: str | None = None
    cutoff: str
    end: str
    verdict: Literal["PASS", "FAIL"] | None = None
    engine: Literal["wf", "legacy"]
    label: str | None = None


class StrategyRow(Strict):
    id: str
    name: str
    created_at: str | None = None
    verdict: Literal["PASS", "FAIL"] | None = None


class Month(Strict):
    month: str
    portfolio: float
    benchmark: float


class MetricSet(Strict):
    total_return: float
    cagr: float
    max_drawdown: float
    sharpe: float


class MetricPair(Strict):
    portfolio: MetricSet
    baseline: MetricSet


class Checks(Strict):
    drawdown: bool
    sharpe: bool
    excess_return: bool
    mandate: bool


class Thresholds(Strict):
    max_drawdown: float | None = None
    min_sharpe: float | None = None
    min_excess_return: float | None = None
    max_position: float | None = None


class Backtest(Strict):
    dates: list[str]
    portfolio: list[float]
    benchmark: list[float]
    equal_weight: list[float] | None = None
    drawdown: list[float]
    benchmark_drawdown: list[float]
    monthly: list[Month]
    metrics: MetricPair
    checks: Checks | None = None
    thresholds: Thresholds
    consistent: bool
    note: str


class Allocation(Strict):
    strategy_id: str
    weights: dict[str, float]
    max_position: float | None = None


class OrderRow(Strict):
    client_order_id: str
    symbol: str
    side: str
    notional: float
    status: str | None = None
    time: str | None = None


class Team(Strict):
    title: str
    first: str
    last: str
    dates: list[str]
    series: dict[str, list[float]]
    note: str


class FundCharts(Strict):
    fund_id: str
    fund_name: str
    capital: float
    generated_at: str
    strategy: StrategyInfo | None = None
    strategies: list[StrategyRow]
    backtest: Backtest | None = None
    allocation: Allocation | None = None
    orders: list[OrderRow]
    team: Team | None = None
    notes: list[str]
