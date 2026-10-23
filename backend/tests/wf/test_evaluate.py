"""Statistics tests. weekly_returns hand check: equity 100 on a Friday (base, alone in its week),
then 105 -> 110 at the end of week 1 (return 0.10) and 99 at the end of week 2 (return -0.10).
forward_returns hand check: closes 100,101,102,104,108 with decision on day 0 and horizon 2 use the
close of day 1 (101) and day 3 (104): 104/101 - 1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.app.backtest import metrics
from backend.app.wf.calendar import decision_dates, next_session
from backend.app.wf.evaluate import (
    attribution_table,
    forward_returns,
    paired_excess_ci,
    random_policy_percentile,
    rank_ic,
    sharpe_diff_ci,
    summarize,
    weekly_returns,
)


def test_weekly_returns_hand_computed():
    idx = pd.to_datetime(
        ["2024-01-05", "2024-01-08", "2024-01-12", "2024-01-15", "2024-01-19"]
    )
    r = weekly_returns(pd.Series([100, 105, 110, 104, 99], index=idx, dtype=float))
    assert r.tolist() == pytest.approx([0.10, -0.10])
    assert list(r.index) == [idx[2], idx[4]]


def test_paired_excess_ci_contains_true_mean_and_is_seeded():
    rng = np.random.default_rng(11)
    idx = pd.date_range("2024-01-05", periods=200, freq="W-FRI")
    strat = pd.Series(0.002 + rng.normal(0, 0.01, 200), index=idx)
    base = pd.Series(0.0, index=idx)
    ci = paired_excess_ci(strat, base, block=4, n_boot=2000, seed=0)
    assert ci.lo <= 0.002 <= ci.hi and ci.lo < ci.mean < ci.hi and ci.n == 200
    assert ci == paired_excess_ci(strat, base, block=4, n_boot=2000, seed=0)


def test_sharpe_diff_ci_zero_for_identical_and_positive_for_better():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2024-01-05", periods=150, freq="W-FRI")
    noise = pd.Series(rng.normal(0.0, 0.01, 150), index=idx)
    same = sharpe_diff_ci(noise, noise)
    assert (same.mean, same.lo, same.hi) == (0.0, 0.0, 0.0)
    better = sharpe_diff_ci(noise + 0.01, noise, seed=3)
    assert better.mean > 0 and better.lo > 0


def test_random_policy_percentile():
    assert random_policy_percentile(4.5, range(10)) == 50.0
    assert random_policy_percentile(100, [1, 2, 3]) == 100.0
    assert random_policy_percentile(1, [1, 1]) == 50.0


def test_rank_ic_perfect_and_random():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-05", periods=60, freq="W-FRI")
    fwd = pd.DataFrame(rng.normal(size=(60, 30)), index=idx)
    perfect = rank_ic(fwd * 3 + 1, fwd)
    assert perfect.mean == pytest.approx(1.0) and perfect.hit_rate == 1.0
    noise = rank_ic(pd.DataFrame(rng.normal(size=(60, 30)), index=idx), fwd)
    assert abs(noise.mean) < 0.06 and abs(noise.t_stat) < 3 and noise.n == 60


def test_forward_returns_hand_computed_and_ignores_data_at_or_before_decision():
    idx = pd.bdate_range("2024-01-02", periods=5)
    closes = pd.DataFrame({"A": [100, 101, 102, 104, 108]}, index=idx, dtype=float)
    d = [str(idx[0].date())]
    fr = forward_returns(closes, d, 2)
    assert fr.loc[d[0], "A"] == pytest.approx(104 / 101 - 1)
    poisoned = closes.copy()
    poisoned.iloc[0] = 1e9
    pd.testing.assert_frame_equal(fr, forward_returns(poisoned, d, 2))
    assert np.isnan(
        forward_returns(closes, [str(idx[3].date())], 2).iloc[0, 0]
    )  # horizon not complete


def test_calendar_week_ends_and_holiday_friday():
    idx = pd.bdate_range("2024-03-25", "2024-04-12").drop(
        pd.Timestamp("2024-03-29")
    )  # Good Friday
    got = decision_dates(idx, "2024-03-25", "2024-04-12")
    assert got == ["2024-03-28", "2024-04-05", "2024-04-12"]
    assert decision_dates(idx, "2024-04-01", "2024-04-08") == ["2024-04-05"]
    assert next_session(idx, "2024-03-28") == "2024-04-01"
    assert next_session(idx, "2024-04-12") is None


def test_summarize_matches_backtest_metrics_and_attribution_table():
    from backend.app.wf.engine import run_engine
    from backend.tests.wf._synth import cfg, random_walk_bars, rf

    data = random_walk_bars(["A", "B"], 30, seed=4)
    idx = data["A"].index
    res = run_engine(data, [], cfg(), rf(1.0), str(idx[0].date()), str(idx[-1].date()))
    assert summarize(res.equity, 1.0) == metrics(res.equity, 1.0)
    table = attribution_table({"cash": res})
    assert table.loc["cash", "n_fills"] == 0 and table.loc[
        "cash", "final_equity"
    ] == pytest.approx(res.equity.iloc[-1])
