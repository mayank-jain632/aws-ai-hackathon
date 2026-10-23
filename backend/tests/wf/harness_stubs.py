"""Tiny in-test components and data for the harness tests (registered under t_* names)."""

from __future__ import annotations

from typing import ClassVar

import pandas as pd

from backend.app.wf.interfaces import (
    ComponentSpec,
    DecisionContext,
    PortfolioSnapshot,
    TargetBook,
)
from backend.app.wf.registry import register_decider, register_execution
from backend.app.wf.runspec import EngineSpec, RunSpec, WindowSpec
from backend.app.wf.schemas import DecisionOrders, OrderIntent
from backend.tests.wf._synth import BIG

DECIDE_CALLS: list[str] = []
SEEN: dict[str, PortfolioSnapshot] = {}


class StubPit:
    """Satisfies the harness: date-taking PIT with no data."""

    def evidence(self, analyst, as_of, universe):
        return "", []

    def execution_context(self, as_of, tickers):
        return {}

    def last_close(self, as_of, ticker):
        return 100.0


@register_decider("t_const")
class ConstDecider:
    name, version = "t_const", "1"
    stateless: ClassVar[bool] = True

    def __init__(self, weights: dict[str, float]) -> None:
        self.weights = dict(weights)

    def decide(self, ctx: DecisionContext) -> TargetBook:
        DECIDE_CALLS.append(ctx.as_of)
        return TargetBook(decision_date=ctx.as_of, weights=self.weights)


@register_decider("t_stateful")
class StatefulDecider(ConstDecider):
    name = "t_stateful"
    stateless: ClassVar[bool] = False

    def decide(self, ctx: DecisionContext) -> TargetBook:
        SEEN[f"decide:{ctx.as_of}"] = ctx.portfolio
        return TargetBook(decision_date=ctx.as_of, weights=self.weights)


@register_execution("t_market_open")
class MarketOpenExecution:
    name, version = "t_market_open", "1"

    def plan(self, ctx: DecisionContext, book: TargetBook) -> DecisionOrders:
        SEEN[ctx.as_of] = ctx.portfolio
        intents = [OrderIntent(ticker=t, target_weight=w) for t, w in sorted(book.weights.items())]
        return DecisionOrders(date=ctx.as_of, intents=intents)


@register_execution("t_drift")
class DriftExecution:
    """State dependent: trades only names whose current weight drifted from target."""

    name, version = "t_drift", "1"

    def __init__(self, threshold: float = 0.05) -> None:
        self.threshold = threshold

    def plan(self, ctx: DecisionContext, book: TargetBook) -> DecisionOrders:
        SEEN[ctx.as_of] = ctx.portfolio
        intents = [
            OrderIntent(ticker=t, target_weight=w)
            for t, w in sorted(book.weights.items())
            if abs(w - ctx.portfolio.weight(t)) > self.threshold
        ]
        return DecisionOrders(date=ctx.as_of, intents=intents, blocked=[] if intents else ["no drift"])


class NotAComponent:
    pass


def flat_bars(tickers, dates, px: float = 100.0, last_close: dict[str, tuple] | None = None) -> dict[str, pd.DataFrame]:
    out = {}
    for t in tickers:
        close = pd.Series(px, index=dates)
        if last_close and t in last_close:
            close.loc[last_close[t][0]] = last_close[t][1]
        out[t] = pd.DataFrame(
            {"open": px, "high": close.clip(lower=px), "low": close.clip(upper=px), "close": close, "volume": BIG},
            index=dates,
        )
    return out


def make_spec(first="2024-01-05", last="2024-03-29", end="2024-04-10", cutoff="2023-06", **kw) -> RunSpec:
    base = {
        "name": "t",
        "window": WindowSpec(first_decision=first, last_decision=last, mark_end=end, dev_decisions=2),
        "universe": ("A", "B"),
        "decider": ComponentSpec(ref="t_const", params={"weights": {"A": 0.5, "B": 0.25}}),
        "execution": ComponentSpec(ref="t_market_open"),
        "engine": EngineSpec(start_cash=100_000.0, slippage_bps=0.0),
        "model_id": "stub-model",
        "model_training_cutoff": cutoff,
    }
    return RunSpec(**{**base, **kw})
