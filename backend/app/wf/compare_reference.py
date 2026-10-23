"""Run the team's blind backtester and our engine on the SAME frozen weights and window.

    compare_to_reference({"AAPL": .3, "MSFT": .7}, "2023-01-03", "2025-06-30")

Both evaluators rebalance monthly. The current reference marks holdings before rebalancing
at the first trading day's close; the walk-forward engine decides after that close and fills
at the next open. The diagnostic-only historical reference below preserves the former
month-start bug so earlier recorded comparisons remain interpretable. It is never used by
the Desk or execution gate.

With ``costs_bps > 0`` the report adds the cost drag (zero-cost minus costed total return).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from backend.app import backtest, data
from backend.app.schema import Metrics
from backend.app.wf.adapters.evaluators import (
    DATA_END,
    ReferenceEvaluator,
    WfEvaluator,
    validate_weights,
)
from backend.app.wf.interfaces import EvalResult


class CompareRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    total_return: float
    max_drawdown: float
    sharpe: float


class ReferenceComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[CompareRow]
    max_abs_curve_diff: float  # wf (zero cost) vs reference, normalised equity curves
    max_abs_curve_diff_corrected: float  # wf (zero cost) vs reference with the first-day bug fixed
    max_abs_curve_diff_with_costs: float | None = None
    cost_drag: float | None = None  # total return, zero cost minus costed
    notes: list[str]


def corrected_reference_curve(closes: pd.DataFrame, target: pd.Series) -> pd.Series:
    """Current production reference; its month-start marking is now corrected."""
    return backtest.rebalanced_curve(closes, target)


def historical_reference_curve(closes: pd.DataFrame, target: pd.Series) -> pd.Series:
    """Pre-fix diagnostic ONLY: reproduces the missing month-start return in old reports."""
    target = target.reindex(closes.columns).fillna(0.0)
    target = target / target.sum()
    px = closes.to_numpy()
    months = closes.index.to_period("M")
    values = np.empty(len(closes))
    value, units, prev_month = 1.0, None, None
    for i in range(len(closes)):
        if months[i] != prev_month:
            units = value * target.to_numpy() / px[i]
            prev_month = months[i]
        value = float(np.dot(units, px[i]))
        values[i] = value
    return pd.Series(values, index=closes.index)


def _row(label: str, m: Metrics) -> CompareRow:
    return CompareRow(label=label, total_return=m.total_return, max_drawdown=m.max_drawdown, sharpe=m.sharpe)


def _curve(result: EvalResult) -> pd.Series:
    eq = result.equity or {}
    return pd.Series(eq["portfolio"], index=pd.to_datetime(eq["dates"]), dtype=float)


def _max_diff(a: pd.Series, b: pd.Series) -> float:
    common = a.index.intersection(b.index)
    if len(common) != len(a) or len(common) != len(b):
        raise ValueError("curves cover different dates")
    return float((a.loc[common] - b.loc[common]).abs().max())


def _historical(weights: dict[str, float], cutoff: str, end: str, universe: list[str], ref: ReferenceEvaluator):
    closes = ref._closes if ref._closes is not None else data.prices_full(universe + [data.REFERENCE])
    win = closes[(closes.index >= pd.Timestamp(cutoff)) & (closes.index <= pd.Timestamp(end))].dropna(how="any")
    curve = historical_reference_curve(win[universe], pd.Series(weights, dtype=float))
    return curve, backtest.metrics(curve, data.fedfunds_at(cutoff))


def compare_to_reference(
    weights: dict[str, float], cutoff: str, end: str = DATA_END, *, costs_bps: float = 0.0
) -> ReferenceComparison:
    """Evaluate ``weights`` with both engines over [cutoff, end] (``end`` <= 2025-06-30)."""
    if end > DATA_END:
        raise ValueError(f"the reference data ends {DATA_END}; got end={end}")
    universe = list(data.UNIVERSE)
    clean = validate_weights(weights, universe)
    ref_eval = ReferenceEvaluator()
    ref = ref_eval.evaluate(clean, cutoff, end)
    zero = WfEvaluator(costs_bps=0.0).evaluate(clean, cutoff, end)
    old_curve, old_metrics = _historical(clean, cutoff, end, universe, ref_eval)
    rows = [
        _row("historical reference (before month-start fix)", old_metrics),
        _row("reference (month-start marking corrected)", ref.portfolio),
        _row("wf engine, zero cost", zero.portfolio),
    ]
    out = {
        "max_abs_curve_diff": _max_diff(old_curve, _curve(zero)),
        "max_abs_curve_diff_corrected": _max_diff(_curve(ref), _curve(zero)),
    }
    if costs_bps > 0:
        costed = WfEvaluator(costs_bps=costs_bps).evaluate(clean, cutoff, end)
        rows.append(_row(f"wf engine, {costs_bps:g} bps", costed.portfolio))
        out["max_abs_curve_diff_with_costs"] = _max_diff(old_curve, _curve(costed))
        out["cost_drag"] = zero.portfolio.total_return - costed.portfolio.total_return
    return ReferenceComparison(rows=rows, notes=_notes(), **out)


def _notes() -> list[str]:
    return [
        "engine fills at the next open; the reference rebalances at the same day's close",
        ("historical reference reproduces the old missing month-start return for comparison only; "
         "current production reference marks holdings before rebalancing"),
        "identical close prices in data/prices and data/wf for the overlap",
    ]
