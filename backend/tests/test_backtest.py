"""Hand-computed two-asset check of backend/app/backtest.py.

Prices (synthetic, two assets A and B plus a reference column):

    date         A     B    SPY
    2023-01-02  100   100   400
    2023-01-16   90   100   410
    2023-01-31  150    90   420
    2023-02-01  150    90   420   <- first trading day of February: rebalance
    2023-02-15  150   100   441

Target 60% A / 40% B, start value 1.0:
    Jan 02: units A = 0.6/100 = 0.006, B = 0.4/100 = 0.004
    Jan 16: 0.006*90  + 0.004*100 = 0.54 + 0.40 = 0.94
    Jan 31: 0.006*150 + 0.004*90  = 0.90 + 0.36 = 1.26
    Feb 01: value still 1.26; rebalance -> A = 0.756/150 = 0.00504, B = 0.504/90 = 0.0056
    Feb 15: 0.00504*150 + 0.0056*100 = 0.756 + 0.56 = 1.316

Equal weight 50/50:
    Jan 16: 0.005*90 + 0.005*100 = 0.95
    Jan 31: 0.75 + 0.45 = 1.20
    Feb 01: rebalance at 1.20 -> A = 0.6/150 = 0.004, B = 0.6/90 = 0.006667
    Feb 15: 0.6 + 0.666667 = 1.266667

SPY: 400 -> 441 is 1.1025 at the end.
Portfolio metrics: total return 0.316; max drawdown 0.94 - 1 = -0.06;
CAGR = 1.316 ** (365.25 / 44) - 1 over 44 calendar days; Sharpe from the four daily
returns (-0.06, 0.340426, 0, 0.044444) with rf = 0, ddof = 1, times sqrt(252).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backend.app.backtest import backtest, metrics, rebalanced_curve
from backend.app.schema import Weight

DATES = pd.to_datetime(["2023-01-02", "2023-01-16", "2023-01-31", "2023-02-01", "2023-02-15"])
CLOSES = pd.DataFrame(
    {"A": [100, 90, 150, 150, 150], "B": [100, 100, 90, 90, 100], "SPY": [400, 410, 420, 420, 441]},
    index=DATES,
    dtype=float,
)


def _weights() -> list[Weight]:
    return [
        Weight(ticker="A", weight=0.6, rationale="", changes_my_mind="", analyst_influence={}),
        Weight(ticker="B", weight=0.4, rationale="", changes_my_mind="", analyst_influence={}),
    ]


def test_rebalanced_curve_matches_hand_computation():
    curve = rebalanced_curve(CLOSES[["A", "B"]], pd.Series({"A": 0.6, "B": 0.4}))
    assert curve.tolist() == pytest.approx([1.0, 0.94, 1.26, 1.26, 1.316])


def test_backtest_curves_and_metrics():
    equity, m = backtest(
        _weights(), cutoff="2023-01-01", end="2023-02-28", universe=["A", "B"],
        closes=CLOSES, rf_annual_pct=0.0,
    )
    assert equity.dates == [d.strftime("%Y-%m-%d") for d in DATES]
    assert equity.portfolio == pytest.approx([1.0, 0.94, 1.26, 1.26, 1.316])
    assert equity.equal_weight == pytest.approx([1.0, 0.95, 1.20, 1.20, 1.266667], abs=1e-6)
    assert equity.spy == pytest.approx([1.0, 1.025, 1.05, 1.05, 1.1025])

    p = m.portfolio
    assert p.total_return == pytest.approx(0.316)
    assert p.max_drawdown == pytest.approx(-0.06)
    assert p.cagr == pytest.approx(1.316 ** (365.25 / 44) - 1)
    rets = np.array([-0.06, 1.26 / 0.94 - 1, 0.0, 1.316 / 1.26 - 1])
    assert p.sharpe == pytest.approx(rets.mean() / rets.std(ddof=1) * math.sqrt(252))

    b = m.baseline  # equal weight
    assert b.total_return == pytest.approx(1.266667 - 1, abs=1e-6)
    assert b.max_drawdown == pytest.approx(-0.05)


def test_spy_baseline_and_rf():
    _, m = backtest(
        _weights(), cutoff="2023-01-01", end="2023-02-28", universe=["A", "B"],
        closes=CLOSES, rf_annual_pct=5.0, baseline="spy",
    )
    assert m.baseline.total_return == pytest.approx(0.1025)
    # a positive risk-free rate lowers Sharpe relative to rf = 0
    _, m0 = backtest(
        _weights(), cutoff="2023-01-01", end="2023-02-28", universe=["A", "B"],
        closes=CLOSES, rf_annual_pct=0.0,
    )
    assert m.portfolio.sharpe < m0.portfolio.sharpe


def test_weights_are_normalised_and_unknown_tickers_rejected():
    half = [Weight(ticker="A", weight=0.3, rationale="", changes_my_mind="", analyst_influence={}),
            Weight(ticker="B", weight=0.2, rationale="", changes_my_mind="", analyst_influence={})]
    eq, _ = backtest(half, "2023-01-01", "2023-02-28", universe=["A", "B"], closes=CLOSES, rf_annual_pct=0)
    assert eq.portfolio == pytest.approx([1.0, 0.94, 1.26, 1.26, 1.316])
    with pytest.raises(ValueError):
        backtest([Weight(ticker="ZZZ", weight=1, rationale="", changes_my_mind="", analyst_influence={})],
                 "2023-01-01", "2023-02-28", universe=["A", "B"], closes=CLOSES, rf_annual_pct=0)


def test_metrics_flat_curve():
    flat = pd.Series([1.0, 1.0, 1.0], index=pd.to_datetime(["2023-01-02", "2023-01-03", "2023-01-04"]))
    m = metrics(flat, 0.0)
    assert m.total_return == 0 and m.max_drawdown == 0 and m.sharpe == 0


@pytest.mark.skipif(
    not (pd.io.common.os.path.exists(__file__.rsplit("backend", 1)[0] + "data/prices/close.csv")),
    reason="committed price snapshot not present",
)
def test_real_data_smoke():
    from backend.app import data

    ws = [Weight(ticker=t, weight=0.1, rationale="", changes_my_mind="", analyst_influence={})
          for t in data.UNIVERSE]
    eq, m = backtest(ws, "2023-01-01")
    assert eq.dates[0] >= "2023-01-01" and eq.dates[-1] <= "2025-06-30"
    assert eq.portfolio[0] == 1.0 and eq.equal_weight[0] == 1.0 and eq.spy[0] == 1.0
    # 10% in each name rebalanced monthly is the equal-weight baseline itself
    assert eq.portfolio == pytest.approx(eq.equal_weight)
    assert m.portfolio.total_return == pytest.approx(m.baseline.total_return)
    assert -1 < m.portfolio.max_drawdown <= 0
