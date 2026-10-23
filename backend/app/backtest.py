"""Forward backtest of the PM's target weights against equal-weight and SPY.

Rules (PLAN.md section 5):
  * Window: first trading day on/after ``cutoff`` through ``end`` (default 2025-06-30).
  * Monthly rebalance: on the first trading day of each calendar month (and on day one)
    holdings are reset to the target weights using that day's close. Between rebalances
    positions drift with price.
  * Long-only, weights are normalised to sum to 1 (a ticker absent from ``weights``
    gets 0). No transaction costs. Price returns (closes are not dividend-adjusted).
  * All three curves are normalised to 1.0 on the first day of the window.
  * Metrics: total_return = V_T/V_0 - 1; cagr annualised over calendar days;
    max_drawdown = min over t of V_t / max_{s<=t} V_s - 1 (a negative number);
    sharpe = mean(daily excess return) / std(daily return, ddof=1) * sqrt(252), with the
    risk-free rate = FEDFUNDS at cutoff (annual percent) converted to a daily rate /252.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from backend.app import data
from backend.app.schema import Baseline, Equity, Metrics, RunMetrics, Weight

TRADING_DAYS = 252


def rebalanced_curve(closes: pd.DataFrame, target: pd.Series) -> pd.Series:
    """Value of a portfolio rebalanced to ``target`` weights on the first trading day of
    each month, starting at 1.0 on closes.index[0]. ``target`` is indexed by ticker."""
    target = target.reindex(closes.columns).fillna(0.0)
    if target.sum() <= 0:
        raise ValueError("weights must sum to a positive number")
    target = target / target.sum()
    values = np.empty(len(closes))
    value = 1.0
    units = None
    months = closes.index.to_period("M")
    prev_month = None
    px = closes.to_numpy()
    for i in range(len(closes)):
        if months[i] != prev_month:  # first trading day of a new month: rebalance
            units = value * target.to_numpy() / px[i]
            prev_month = months[i]
        value = float(np.dot(units, px[i]))
        values[i] = value
    return pd.Series(values, index=closes.index)


def metrics(curve: pd.Series, rf_annual_pct: float) -> Metrics:
    v0, vT = float(curve.iloc[0]), float(curve.iloc[-1])
    days = (curve.index[-1] - curve.index[0]).days
    total = vT / v0 - 1
    cagr = (vT / v0) ** (365.25 / days) - 1 if days > 0 else 0.0
    dd = float((curve / curve.cummax() - 1).min())
    rets = curve.pct_change().dropna()
    rf_daily = rf_annual_pct / 100 / TRADING_DAYS
    sd = float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
    sharpe = float((rets.mean() - rf_daily) / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    return Metrics(total_return=total, cagr=cagr, max_drawdown=dd, sharpe=sharpe)


def backtest(
    weights: list[Weight],
    cutoff: str,
    end: str = "2025-06-30",
    baseline: Baseline = "equal_weight",
    universe: list[str] | None = None,
    closes: pd.DataFrame | None = None,
    rf_annual_pct: float | None = None,
) -> tuple[Equity, RunMetrics]:
    """Run the forward test. ``closes`` and ``rf_annual_pct`` exist for tests; in
    production they come from data.prices_full() and data.fedfunds_at(cutoff)."""
    universe = list(universe or data.UNIVERSE)
    if closes is None:
        closes = data.prices_full(universe + [data.REFERENCE])
    if rf_annual_pct is None:
        rf_annual_pct = data.fedfunds_at(cutoff)

    window = closes[(closes.index >= pd.Timestamp(cutoff)) & (closes.index <= pd.Timestamp(end))]
    window = window.dropna(how="any")
    if len(window) < 2:
        raise ValueError(f"no price history between {cutoff} and {end}")

    target = pd.Series({w.ticker: w.weight for w in weights}, dtype=float)
    unknown = set(target.index) - set(universe)
    if unknown:
        raise ValueError(f"weights for tickers outside the universe: {sorted(unknown)}")

    stocks = window[universe]
    portfolio = rebalanced_curve(stocks, target)
    equal = rebalanced_curve(stocks, pd.Series(1.0, index=universe))
    spy_col = window.columns[-1] if data.REFERENCE not in window else data.REFERENCE
    spy = window[spy_col] / window[spy_col].iloc[0]

    equity = Equity(
        dates=[d.strftime("%Y-%m-%d") for d in window.index],
        portfolio=[round(float(v), 6) for v in portfolio],
        equal_weight=[round(float(v), 6) for v in equal],
        spy=[round(float(v), 6) for v in spy],
    )
    base_curve = equal if baseline == "equal_weight" else spy
    run_metrics = RunMetrics(
        portfolio=metrics(portfolio, rf_annual_pct),
        baseline=metrics(base_curve, rf_annual_pct),
    )
    return equity, run_metrics


__all__ = ["backtest", "rebalanced_curve", "metrics"]
