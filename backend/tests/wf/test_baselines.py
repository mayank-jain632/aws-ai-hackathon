"""Baselines run through the same engine. Hand check of momentum with lookback 3, skip 1:
score = close[-2] / close[-4] - 1 on closes up to the decision date.
    A: 100,110,120,121 -> 120/100 - 1 = 0.2     B: 100,100,100,200 -> 100/100 - 1 = 0
top_n = 1 picks A even though B jumped on the last day (that day is skipped).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.app.backtest import rebalanced_curve
from backend.app.wf.baselines import (
    equal_weight_buy_hold,
    equal_weight_weekly,
    from_target_weights,
    momentum_rule,
    random_policy,
    spy_buy_hold,
)
from backend.app.wf.engine import run_engine
from backend.tests.wf._synth import cfg, rf


def test_momentum_hand_computed_and_ignores_the_future():
    idx = pd.bdate_range("2024-01-02", periods=4)
    closes = pd.DataFrame(
        {"A": [100, 110, 120, 121], "B": [100, 100, 100, 200]}, index=idx, dtype=float
    )
    out = momentum_rule(
        closes, [str(idx[-1].date())], ["A", "B"], lookback=3, skip=1, top_n=1
    )
    assert {i.ticker: i.target_weight for i in out[0].intents} == {"A": 1.0, "B": 0.0}


def test_momentum_truncating_closes_at_the_decision_date_gives_identical_output():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2023-01-02", periods=400)
    closes = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0, 0.01, (400, 6)), axis=0),
        index=idx,
        columns=list("ABCDEF"),
    )
    dates = [str(idx[i].date()) for i in (300, 320, 340)]
    full = momentum_rule(closes, dates, list(closes.columns), top_n=3)
    cut = momentum_rule(closes.loc[: idx[340]], dates, list(closes.columns), top_n=3)
    poisoned = closes.copy()
    poisoned.loc[idx[341:]] = rng.uniform(1, 1000, poisoned.loc[idx[341:]].shape)
    assert full == cut == momentum_rule(poisoned, dates, list(closes.columns), top_n=3)
    assert len(full) == 3 and all(
        sum(i.target_weight for i in d.intents) == pytest.approx(1) for d in full
    )


def test_momentum_short_history_emits_no_decision():
    idx = pd.bdate_range("2024-01-02", periods=10)
    closes = pd.DataFrame({"A": range(1, 11)}, index=idx, dtype=float)
    assert momentum_rule(closes, [str(idx[-1].date())], ["A"]) == []


def test_equal_weight_buy_hold_matches_rebalanced_curve_without_costs():
    rng = np.random.default_rng(5)
    idx = pd.bdate_range(
        "2024-01-02", periods=15
    )  # all inside January: no monthly rebalance
    closes = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0, 0.01, (15, 3)), axis=0),
        index=idx,
        columns=list("ABC"),
    )
    closes.iloc[1] = closes.iloc[
        0
    ]  # day-1 open == decision close so the fill price equals the curve's start
    bars = {
        t: pd.DataFrame(
            {
                "open": closes[t],
                "high": closes[t],
                "low": closes[t],
                "close": closes[t],
                "volume": 1e12,
            }
        )
        for t in closes
    }
    c = cfg(slippage_bps=0.0, rebalance_band=0.0, volume_participation_cap=1.0)
    dates = [str(idx[0].date())]
    res = run_engine(
        bars,
        equal_weight_buy_hold(dates, list("ABC")),
        c,
        rf(),
        dates[0],
        str(idx[-1].date()),
    )
    expect = rebalanced_curve(closes.iloc[1:], pd.Series(1.0, index=list("ABC")))
    assert (res.equity.iloc[1:] / c.start_cash).to_numpy() == pytest.approx(
        expect.to_numpy(), rel=1e-9
    )
    w = res.positions[res.positions.date == idx[1]].weight
    assert w.tolist() == pytest.approx([1 / 3] * 3)


def test_builders_shapes():
    dates = ["2024-01-05", "2024-01-12"]
    t = list("ABCD")
    bh = equal_weight_buy_hold(dates, t)
    assert len(bh) == 1 and all(
        i.stop_price is None and i.target_price is None for i in bh[0].intents
    )
    assert len(equal_weight_weekly(dates, t)) == 2
    assert spy_buy_hold(dates, "SPY")[0].intents[0].target_weight == 1.0
    with pytest.raises(ValueError):
        from_target_weights({dates[0]: {"A": 0.7, "B": 0.7}})


def test_random_policy_is_seeded_and_fully_invested():
    dates = ["2024-01-05", "2024-01-12"]
    a = random_policy(dates, list("ABCDEF"), seed=1, n_names=3)
    assert (
        a
        == random_policy(dates, list("ABCDEF"), seed=1, n_names=3)
        != random_policy(dates, list("ABCDEF"), seed=2, n_names=3)
    )
    for d in a:
        assert sum(i.target_weight for i in d.intents) == pytest.approx(1.0)
        assert sum(i.target_weight > 0 for i in d.intents) == 3
