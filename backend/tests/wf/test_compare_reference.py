from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.app import backtest
from backend.app.wf.compare_reference import (
    compare_to_reference,
    corrected_reference_curve,
    historical_reference_curve,
)

W = {"AAPL": 0.3, "MSFT": 0.3, "NVDA": 0.2, "JPM": 0.2}


def test_historical_diagnostic_preserves_old_bug_but_production_is_corrected() -> None:
    idx = pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"])
    closes = pd.DataFrame({"A": [100.0, 100.0, 110.0, 110.0]}, index=idx)
    t = pd.Series({"A": 1.0})
    assert historical_reference_curve(closes, t).tolist() == [1.0, 1.0, 1.0, 1.0]  # the +10% day is lost
    assert backtest.rebalanced_curve(closes, t).tolist() == pytest.approx([1.0, 1.0, 1.1, 1.1])
    assert corrected_reference_curve(closes, t).tolist() == pytest.approx([1.0, 1.0, 1.1, 1.1])


def test_corrected_curve_matches_buy_and_hold_for_single_month() -> None:
    idx = pd.bdate_range("2024-03-01", periods=10)
    px = pd.DataFrame({"A": np.linspace(100, 120, 10), "B": np.linspace(50, 40, 10)}, index=idx)
    got = corrected_reference_curve(px, pd.Series({"A": 0.5, "B": 0.5}))
    hold = 0.5 * px["A"] / px["A"].iloc[0] + 0.5 * px["B"] / px["B"].iloc[0]
    assert got.to_numpy() == pytest.approx(hold.to_numpy())


def test_window_beyond_reference_data_is_refused() -> None:
    with pytest.raises(ValueError, match="2025-06-30"):
        compare_to_reference(W, "2024-01-02", "2025-12-31")


def test_zero_cost_curves_match_the_corrected_reference_closely() -> None:
    cmp = compare_to_reference(W, "2023-01-03", "2025-06-30", costs_bps=5.0)
    assert cmp.max_abs_curve_diff_corrected < 0.03  # measured 0.016: next-open fills vs same-close
    assert cmp.max_abs_curve_diff > 5 * cmp.max_abs_curve_diff_corrected  # the reference's first-day bug
    assert 0 < cmp.cost_drag < 0.02
    assert cmp.rows[0].label == "historical reference (before month-start fix)" and len(cmp.rows) == 4
