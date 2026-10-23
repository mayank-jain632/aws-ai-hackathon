"""Evaluators: frozen weights + dates -> `EvalResult` (hub D22).

ReferenceEvaluator  the team's blind backtester (`backend.app.backtest.backtest`), with month-start marking corrected
WfEvaluator         the same frozen weights through OUR engine on `data/wf` bars

Both rebalance on the first trading day of each month, so their curves are comparable
(`compare_reference.py` measures the gap).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from backend.app import backtest, data
from backend.app.schema import Weight
from backend.app.wf import baselines, evaluate, market
from backend.app.wf.config import WfConfig
from backend.app.wf.engine import run_engine
from backend.app.wf.interfaces import EvalResult
from backend.app.wf.registry import register_evaluator
from backend.app.wf.schemas import DecisionOrders

log = logging.getLogger("wf.adapters.evaluators")
DATA_END = "2025-06-30"  # the `data/` snapshot used by the reference backtester ends here
WF_START_CASH = 1_000_000.0


def validate_weights(
    weights: Mapping[str, float], universe: Sequence[str], normalize: bool = True
) -> dict[str, float]:
    """Mapping -> plain dict; rejects tickers outside the universe, negatives, > 1, all-zero."""
    out = {str(t): float(w) for t, w in weights.items()}
    unknown = sorted(set(out) - set(universe))
    if unknown:
        raise ValueError(f"weights for tickers outside the universe: {unknown}")
    if any(w < 0 or w > 1 for w in out.values()):
        raise ValueError("weights must lie in [0, 1]")
    total = sum(out.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    if not normalize and total > 1 + 1e-9:
        raise ValueError(f"weights sum to {total:.6f} > 1")
    return out


def _round_list(values) -> list[float]:
    return [round(float(v), 6) for v in values]


@register_evaluator("reference_backtest")
class ReferenceEvaluator:
    """Wraps `backtest.backtest`. Assumptions: monthly rebalance on the first trading day of each
    month, fully invested (weights normalised to 1), no costs, no dividends (price returns), the
    `data/prices` snapshot which ends 2025-06-30. Params: ``universe`` (default `data.UNIVERSE`);
    ``closes`` / ``rf_annual_pct`` can be injected for tests."""

    name = "reference_backtest"
    version = "2"

    def __init__(
        self,
        universe: Sequence[str] | None = None,
        closes: pd.DataFrame | None = None,
        rf_annual_pct: float | None = None,
    ) -> None:
        self.universe = list(universe or data.UNIVERSE)
        self._closes, self._rf = closes, rf_annual_pct

    def evaluate(self, weights: Mapping[str, float], cutoff: str, end: str) -> EvalResult:
        clean = validate_weights(weights, self.universe)
        wl = [
            Weight(ticker=t, weight=w, rationale="frozen weight", changes_my_mind="n/a", analyst_influence={})
            for t, w in sorted(clean.items())
        ]
        kw = {"universe": self.universe, "closes": self._closes, "rf_annual_pct": self._rf}
        equity, vs_ew = backtest.backtest(wl, cutoff, end, baseline="equal_weight", **kw)
        _, vs_spy = backtest.backtest(wl, cutoff, end, baseline="spy", **kw)
        return EvalResult(
            cutoff=cutoff,
            end=end,
            portfolio=vs_ew.portfolio,
            benchmark=vs_spy.baseline,
            equal_weight=vs_ew.baseline,
            assumptions=[
                "monthly rebalance on the first trading day of each month, at that day's close",
                "fully invested: weights normalised to sum to 1",
                "no transaction costs, no slippage",
                "no dividends (price returns)",
                f"data/prices snapshot ends {DATA_END}",
            ],
            equity=equity.model_dump(),
        )


def _month_starts(sessions: pd.DatetimeIndex) -> list[pd.Timestamp]:
    firsts = pd.Series(sessions, index=sessions).groupby(sessions.to_period("M")).min()
    return list(firsts)


def _schedule(dates: list[pd.Timestamp], weights: Mapping[str, float]) -> list[DecisionOrders]:
    sched = {d.strftime("%Y-%m-%d"): dict(weights) for d in dates}
    return baselines.from_target_weights(sched)


@register_evaluator("wf_frozen")
class WfEvaluator:
    """Frozen weights through the wf engine: decisions on the first trading day of each month
    (matching the reference), filled at the NEXT open with slippage ``costs_bps`` (default
    `WfConfig.slippage_bps`) per fill, fractional shares, no dividends, cash earns the Fed funds
    rate. Params: ``costs_bps``, ``data_dir`` (default `data/wf`), ``universe``, ``normalize``
    (default True, like the reference), ``volume_participation_cap``."""

    name = "wf_frozen"
    version = "1"

    def __init__(
        self,
        costs_bps: float | None = None,
        data_dir: str | Path | None = None,
        universe: Sequence[str] | None = None,
        normalize: bool = True,
        volume_participation_cap: float | None = None,
    ) -> None:
        base = WfConfig()
        self.cfg = WfConfig(
            start_cash=WF_START_CASH,
            slippage_bps=base.slippage_bps if costs_bps is None else float(costs_bps),
            rebalance_band=0.0,
            volume_participation_cap=volume_participation_cap or base.volume_participation_cap,
        )
        self.data_dir = None if data_dir is None else Path(data_dir)
        self.universe = list(universe or base.universe)
        self.normalize = normalize

    def _window(self, bars: dict, cutoff: str, end: str) -> pd.DatetimeIndex:
        idx = None
        for b in bars.values():
            idx = b.index if idx is None else idx.intersection(b.index)
        win = idx[(idx >= pd.Timestamp(cutoff)) & (idx <= pd.Timestamp(end))].sort_values()
        if len(win) < 2:
            raise ValueError(f"no price history between {cutoff} and {end}")
        return win

    def _curve(self, bars, decisions, rf, win) -> pd.Series:
        res = run_engine(bars, decisions, self.cfg, rf, win[0].strftime("%Y-%m-%d"), win[-1].strftime("%Y-%m-%d"))
        return res.equity / res.equity.iloc[0]

    def evaluate(self, weights: Mapping[str, float], cutoff: str, end: str) -> EvalResult:
        clean = validate_weights(weights, self.universe, self.normalize)
        total = sum(clean.values()) if self.normalize else 1.0
        target = {t: w / total for t, w in clean.items()}
        ref = WfConfig().reference
        bars = market.load_bars(self.data_dir, [*self.universe, ref])
        win = self._window(bars, cutoff, end)
        rf = market.rf_annual_pct(win, self.data_dir)
        months = _month_starts(win)
        eq = {t: 1 / len(self.universe) for t in self.universe}
        curves = {
            "portfolio": self._curve(bars, _schedule(months, target), rf, win),
            "equal_weight": self._curve(bars, _schedule(months, eq), rf, win),
            "spy": self._curve(bars, _schedule(months[:1], {ref: 1.0}), rf, win),
        }
        rf0 = float(market.rf_annual_pct(pd.DatetimeIndex([cutoff]), self.data_dir).iloc[0])
        m = {k: evaluate.summarize(v, rf0) for k, v in curves.items()}
        return EvalResult(
            cutoff=cutoff,
            end=end,
            portfolio=m["portfolio"],
            benchmark=m["spy"],
            equal_weight=m["equal_weight"],
            assumptions=self._assumptions(),
            equity={"dates": [d.strftime("%Y-%m-%d") for d in win], **{k: _round_list(v) for k, v in curves.items()}},
        )

    def _assumptions(self) -> list[str]:
        return [
            "decisions on the first trading day of each month; fills at the NEXT session open",
            f"slippage {self.cfg.slippage_bps} bps against us on every fill, no commissions",
            "fractional shares, long-only, sells before buys, no rebalance band",
            f"volume cap {self.cfg.volume_participation_cap:.0%} of daily volume per order",
            "no dividends (price returns); idle cash earns the Fed funds rate",
            "SPY benchmark bought at the first open and held",
            "bars from data/wf",
        ]
