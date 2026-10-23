"""Cheat-canary and sealed-input tests for the engine.

The canary builds DecisionOrders from FUTURE prices (the next-week winner, weight 1.0). Run
through the same engine it must beat the sealed equal-weight policy by a wide margin; if it
did not, the harness would be unable to detect look-ahead. A second test shows fills never
depend on any bar dated on or before the decision date.
"""

from __future__ import annotations

import pandas as pd

from backend.app.wf.baselines import equal_weight_weekly
from backend.app.wf.calendar import decision_dates
from backend.app.wf.engine import run_engine
from backend.tests.wf._synth import buy, cfg, dec, random_walk_bars, rf

TICKERS = list("ABCDEFGHIJ")


def _setup():
    data = random_walk_bars(TICKERS, 120, seed=7, vol=0.02)
    idx = data["A"].index
    dates = decision_dates(idx, str(idx[0].date()), str(idx[-6].date()))
    return data, idx, dates


def _cheat(data, idx, dates):
    out = []
    for d in dates:
        i = idx.get_loc(pd.Timestamp(d))
        fwd = {
            t: data[t].close.iloc[i + 5] / data[t].close.iloc[i] - 1 for t in TICKERS
        }  # FUTURE
        best = max(fwd, key=fwd.get)
        out.append(dec(d, *[buy(t, 1.0 if t == best else 0.0) for t in TICKERS]))
    return out


def test_cheat_canary_beats_sealed_policy_by_a_wide_margin():
    data, idx, dates = _setup()
    args = (cfg(), rf(), dates[0], str(idx[-1].date()))
    cheat = run_engine(data, _cheat(data, idx, dates), *args)
    sealed = run_engine(data, equal_weight_weekly(dates, TICKERS), *args)
    cheat_ret = cheat.equity.iloc[-1] / cheat.equity.iloc[0] - 1
    sealed_ret = sealed.equity.iloc[-1] / sealed.equity.iloc[0] - 1
    assert cheat_ret > sealed_ret + 1.0 and cheat_ret > 1.0


def test_fill_never_uses_a_bar_on_or_before_the_decision_date():
    data, idx, _ = _setup()
    k = 30
    decision = dec(idx[k], buy("A", 0.5), buy("B", 0.5))
    args = (cfg(), rf(), str(idx[k].date()), str(idx[k + 5].date()))
    control = run_engine(data, [decision], *args)
    poisoned = {}
    for t, b in data.items():
        p = b.copy()
        past = p.index <= idx[k]
        p.loc[past, ["open", "high", "low", "volume"]] = [
            1.0,
            1e6,
            1e-6,
            1.0,
        ]  # close kept: it is decision-time info
        poisoned[t] = p
    res = run_engine(poisoned, [decision], *args)
    pd.testing.assert_frame_equal(control.fills, res.fills)
    assert (control.fills.date > idx[k]).all()
    first = control.fills.iloc[0]
    assert first.date == idx[k + 1]
    assert first.price == data[first.ticker].open.loc[idx[k + 1]] * (1 + 5e-4)
