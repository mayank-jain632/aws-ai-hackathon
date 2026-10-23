"""Closed-loop engine: decision_fn must equal precomputed decisions and see the true account state."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from backend.app.wf import baselines, market
from backend.app.wf.engine import run_engine
from backend.app.wf.schemas import DecisionOrders
from backend.tests.wf._synth import (
    D0,
    D1,
    D2,
    D3,
    bars,
    buy,
    cfg,
    dec,
    flat,
    random_walk_bars,
    rf,
)

FROZEN = Path(__file__).resolve().parents[3] / "reports" / "wf" / "final"


def _assert_same(a, b) -> None:
    assert_series_equal(a.equity, b.equity, check_exact=True)
    assert_frame_equal(a.fills, b.fills, check_exact=True)
    assert_frame_equal(a.skipped, b.skipped, check_exact=True)
    assert_frame_equal(a.positions, b.positions, check_exact=True)
    assert a.costs == b.costs


def _weekly_decisions(data, n_dates: int = 8) -> list[DecisionOrders]:
    idx = next(iter(data.values())).index
    fridays = [d.strftime("%Y-%m-%d") for d in idx[idx.day_of_week == 4]][:n_dates]
    out = baselines.random_policy(fridays, list(data), seed=3, n_names=2)
    stops = [
        d.model_copy(update={"intents": [
            i.model_copy(update={"stop_price": 95.0, "target_price": 130.0, "skip_if_gap_pct": 0.05})
            if i.target_weight > 0 else i
            for i in d.intents
        ]})
        for d in out
    ]
    stops[1] = stops[1].model_copy(update={"blocked": ["watchdog: gross cap"]})
    return stops


def test_closed_loop_equals_precomputed_on_random_walk() -> None:
    data = random_walk_bars(["A", "B", "C"], 60, seed=1)
    c, decisions = cfg(), _weekly_decisions(data)
    start, end = decisions[0].date, "2024-03-20"
    old = run_engine(data, decisions, c, rf(2.0), start, end)
    by_date = {d.date: d for d in decisions}
    new = run_engine(data, [], c, rf(2.0), start, end, lambda d, snap: by_date.get(d), list(by_date))
    _assert_same(old, new)
    assert (new.skipped["reason"] == "blocked").sum() == 1


def test_precomputed_wins_and_fn_not_called_on_that_date() -> None:
    data = {"A": bars([flat(D0, 100), flat(D1, 100), flat(D2, 100), flat(D3, 100)])}
    called: list[str] = []

    def fn(date, snap):
        called.append(date)

    run_engine(data, [dec(D0, buy("A", 0.5))], cfg(), rf(), "2024-01-02", "2024-01-05", fn, None)
    assert called == ["2024-01-03", "2024-01-04"]  # D0 precomputed, last session has no next open


def test_snapshot_matches_hand_computed_state() -> None:
    data = {"A": bars([flat(D0, 100), (D1, 100, 110, 100, 110), flat(D2, 110), flat(D3, 110)])}
    seen: dict = {}

    def fn(date, snap):
        seen[date] = snap
        return dec(date, buy("A", 0.5)) if date == "2024-01-02" else None

    run_engine(data, [], cfg(slippage_bps=0.0), rf(), "2024-01-02", "2024-01-05", fn, ["2024-01-02", "2024-01-03"])
    s0, s1 = seen["2024-01-02"], seen["2024-01-03"]
    assert (s0.equity, s0.cash, dict(s0.positions), s0.open_orders) == (100_000.0, 100_000.0, {}, ())
    # bought 500 sh at the D1 open (100); D1 close 110 -> 50k cash + 55k stock
    assert s1.equity == pytest.approx(105_000.0)
    assert s1.cash == pytest.approx(50_000.0)
    assert dict(s1.positions) == {"A": pytest.approx(55_000.0)}
    assert dict(s1.shares) == {"A": pytest.approx(500.0)}
    assert s1.weight("A") == pytest.approx(55_000 / 105_000)


@pytest.mark.skipif(not (FROZEN / "results_all" / "equity.csv").exists(), reason="frozen run absent")
def test_frozen_run_columns_reproduce_through_both_paths() -> None:
    from backend.app.wf.config import WfConfig
    from backend.app.wf.runner import run_all_strategies
    from backend.app.wf.schemas import DecisionRecord

    c = WfConfig()
    recs = [DecisionRecord.model_validate_json(p.read_text()) for p in sorted((FROZEN / "decisions").glob("*.json"))]
    data = market.load_bars(tickers=[*c.universe, c.reference])
    rate = market.rf_annual_pct(data[c.reference].index)
    dates = [r.decision_date for r in recs]
    saved = pd.read_csv(FROZEN / "results_all" / "equity.csv", index_col=0, parse_dates=True)
    res = run_all_strategies(recs, data, rate, c, dates, c.mark_end)
    by_date = {r.decision_date: r.orders for r in recs}
    closed = run_engine(data, [], c, rate, dates[0], c.mark_end, lambda d, s: by_date.get(d), dates)
    for name in ("pipeline", "equal_weight_buy_hold"):
        assert (res[name].equity - saved[name]).abs().max() < 1e-9
    assert (closed.equity - saved["pipeline"]).abs().max() < 1e-9
    _assert_same(res["pipeline"], closed)
