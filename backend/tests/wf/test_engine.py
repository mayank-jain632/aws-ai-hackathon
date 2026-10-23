"""Hand-computed scenarios for backend/app/wf/engine.py.

Default config: start cash 100,000, slippage 5 bps, volume cap 5% (volume 1e9 unless stated),
band 1%. Sessions D0 = 2024-01-02 (decision close), D1, D2, D3 follow. Ticker A closes 100 on D0.

Market-open buy (weight 0.5): E_0 = 100,000 so target = 0.5 * 100,000 / 100 = 500 shares.
    D1 open 102 -> fill 102 * 1.0005 = 102.051; cost 500 * 102.051 = 51,025.5; cash 48,974.5;
    slippage_cost = 500 * 102 * 0.0005 = 25.5; D1 close 104 -> equity 48,974.5 + 52,000 = 100,974.5.
    (Filling at the decision close 100 would give 50,000 cash and 101,000: the test rules it out.)

Gap-through stop (stop 95): buy fills D1 open 100 -> 100.05, cost 50,025, cash 49,975.
    D2 opens 90 below the stop: fill at the open, 90 * 0.9995 = 89.955; proceeds 44,977.5; cash 94,952.5.
Stop inside the bar (open 99, low 94): fill 95 * 0.9995 = 94.9525.
Stop and target (95 / 110) in one bar (open 100, high 112, low 94): stop first, 94.9525.
Target: open 100, high 112 -> fill at 110 * 0.9995 = 109.945; gap above target (open 115) -> 115 * 0.9995.

Limit buy 98 (500 shares): D1 low 99 -> not reached, no fill. D2 open 99, low 97.5 -> fill min(99, 98) = 98
    (no slippage); cost 49,000. If D2 opens at 97 -> fill at 97.
Gap skip 3%: close 100; D1 open 103.5 > 103 -> cancelled; open 102.9 -> fills.
Band 1% (D1 open 100, close 104): buy fills at 100.05, cash 49,975, equity 49,975 + 52,000 = 101,975, weight
    52,000 / 101,975 = 0.5099. Target 0.515 -> |diff| 0.0051 < 0.01 -> no trade; target 0.55 -> diff 0.040 -> trade.
Volume cap: D1 volume 2,000 -> at most 0.05 * 2,000 = 100 shares of the 500; remainder 400 lapses (logged).
Cash scaling: A and B both 0.5, opens 102: cost 2 * 500 * 102.051 = 102,051 > 100,000 -> buys scaled by
    100,000 / 102,051, cash ends at 0.
rf accrual: rf 2.52% -> 0.01% per session on 100,000 cash: D1 100,010, D2 100,010 * 1.0001 = 100,020.001.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.app.wf.engine import run_engine
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

SLIP = 5e-4


def run(a_rows, decisions, extra=None, c=None, rf_pct=0.0):
    data = {"A": bars(a_rows), **(extra or {})}
    return run_engine(
        data, decisions, c or cfg(), rf(rf_pct), "2024-01-02", "2024-01-05"
    )


def test_market_open_buy_fills_at_next_open_plus_slippage_not_decision_close():
    res = run(
        [flat(D0, 100), (D1, 102, 105, 101, 104), flat(D2, 104), flat(D3, 104)],
        [dec(D0, buy("A", 0.5))],
    )
    f = res.fills.iloc[0]
    assert f.date == D1 and f.kind == "market_open" and f.side == "buy"
    assert f.shares == pytest.approx(500)
    assert f.price == pytest.approx(102.051)
    assert f.slippage_cost == pytest.approx(25.5)
    assert res.equity[D0] == 100_000 and res.equity[D1] == pytest.approx(100_974.5)
    assert res.costs == pytest.approx(25.5)


GAP_ROWS = [flat(D0, 100), (D1, 100, 101, 98, 100)]


def test_gap_through_stop_fills_at_the_open():
    rows = GAP_ROWS + [(D2, 90, 92, 88, 91), flat(D3, 91)]
    res = run(rows, [dec(D0, buy("A", 0.5, stop_price=95))])
    s = res.fills.iloc[-1]
    assert s.kind == "stop" and s.date == D2 and s.price == pytest.approx(89.955)
    assert res.equity[D2] == pytest.approx(94_952.5)
    assert res.positions[
        res.positions.date == D2
    ].empty  # flat, nothing re-bought on D3
    assert len(res.fills) == 2


def test_stop_inside_bar_fills_at_stop_price():
    res = run(
        GAP_ROWS + [(D2, 99, 100, 94, 96), flat(D3, 96)],
        [dec(D0, buy("A", 0.5, stop_price=95))],
    )
    assert res.fills.iloc[-1].price == pytest.approx(94.9525)


def test_stop_and_target_in_one_bar_stop_first():
    rows = GAP_ROWS + [(D2, 100, 112, 94, 100), flat(D3, 100)]
    res = run(rows, [dec(D0, buy("A", 0.5, stop_price=95, target_price=110))])
    s = res.fills.iloc[-1]
    assert s.kind == "stop" and s.price == pytest.approx(94.9525)


def test_target_fills_and_gap_above_target_fills_at_open():
    inb = run(
        GAP_ROWS + [(D2, 100, 112, 99, 111), flat(D3, 111)],
        [dec(D0, buy("A", 0.5, target_price=110))],
    )
    assert inb.fills.iloc[-1].kind == "target" and inb.fills.iloc[
        -1
    ].price == pytest.approx(109.945)
    gap = run(
        GAP_ROWS + [(D2, 115, 118, 114, 116), flat(D3, 116)],
        [dec(D0, buy("A", 0.5, target_price=110))],
    )
    assert gap.fills.iloc[-1].price == pytest.approx(115 * 0.9995)


def test_limit_not_reached_then_reached_fills_at_min_open_limit():
    rows = [
        flat(D0, 100),
        (D1, 100, 101, 99, 100),
        (D2, 99, 100, 97.5, 99),
        flat(D3, 99),
    ]
    res = run(rows, [dec(D0, buy("A", 0.5, entry="limit", limit_price=98))])
    assert len(res.fills) == 1 and res.fills.iloc[0].date == D2
    assert (
        res.fills.iloc[0].price == pytest.approx(98)
        and res.fills.iloc[0].slippage_cost == 0
    )
    assert res.equity[D1] == 100_000  # no fill on D1
    gap = run(
        [flat(D0, 100), (D1, 97, 98, 96, 97), flat(D2, 97), flat(D3, 97)],
        [dec(D0, buy("A", 0.5, entry="limit", limit_price=98))],
    )
    assert gap.fills.iloc[0].price == pytest.approx(97)


def test_limit_never_reached_no_fill():
    rows = [
        flat(D0, 100),
        (D1, 100, 101, 99, 100),
        (D2, 100, 101, 99, 100),
        flat(D3, 100),
    ]
    res = run(rows, [dec(D0, buy("A", 0.5, entry="limit", limit_price=90))])
    assert res.fills.empty and (res.equity == 100_000).all()


def test_skip_if_gap_cancels_large_gap_but_not_small():
    big = run(
        [flat(D0, 100), flat(D1, 103.5), flat(D2, 103.5), flat(D3, 103.5)],
        [dec(D0, buy("A", 0.5, skip_if_gap_pct=0.03))],
    )
    assert big.fills.empty and "gap_cancel" in set(big.skipped.reason)
    small = run(
        [flat(D0, 100), flat(D1, 102.9), flat(D2, 102.9), flat(D3, 102.9)],
        [dec(D0, buy("A", 0.5, skip_if_gap_pct=0.03))],
    )
    assert len(small.fills) == 1


def test_band_suppresses_small_trades():
    rows = [flat(D0, 100), (D1, 100, 105, 100, 104), flat(D2, 104), flat(D3, 104)]
    small = run(rows, [dec(D0, buy("A", 0.5)), dec(D1, buy("A", 0.515))])
    assert len(small.fills) == 1 and "within_band" in set(small.skipped.reason)
    big = run(rows, [dec(D0, buy("A", 0.5)), dec(D1, buy("A", 0.55))])
    assert len(big.fills) == 2 and big.fills.iloc[1].date == D2


def test_volume_cap_limits_fill_and_logs_remainder():
    rows = [flat(D0, 100), (D1, 100, 100, 100, 100, 2000), flat(D2, 100), flat(D3, 100)]
    res = run(rows, [dec(D0, buy("A", 0.5))])
    assert res.fills.iloc[0].shares == pytest.approx(100)
    assert "volume_cap" in set(res.skipped.reason)


def test_cash_never_negative_buys_scaled():
    a = bars([flat(D0, 100), flat(D1, 102), flat(D2, 102), flat(D3, 102)])
    res = run_engine(
        {"A": a, "B": a.copy()},
        [dec(D0, buy("A", 0.5), buy("B", 0.5))],
        cfg(),
        rf(),
        "2024-01-02",
        "2024-01-05",
    )
    scale = 100_000 / (2 * 500 * 102.051)
    assert res.fills.shares.tolist() == pytest.approx([500 * scale, 500 * scale])
    w = res.positions[res.positions.date == D1].weight.sum()
    assert w == pytest.approx(
        1 - 0.0, abs=1e-9
    )  # fully invested, cash 0 (price flat after the open)


def test_position_never_negative_after_stop_cancels_pending_sell():
    rows = [
        flat(D0, 100),
        (D1, 100, 101, 99, 100),
        (D2, 90, 91, 88, 90),
        (D3, 100, 125, 99, 125),
    ]
    d1 = dec(D1, buy("A", 0.0, entry="limit", limit_price=120))
    res = run(rows, [dec(D0, buy("A", 0.5, stop_price=95)), d1])
    assert (res.positions.shares >= 0).all()
    assert res.fills.side.tolist() == ["buy", "sell"]  # the stop, nothing after


def test_random_runs_keep_cash_and_shares_non_negative():
    data = random_walk_bars(["A", "B", "C"], 40, seed=1, vol=0.04)
    rng = np.random.default_rng(2)
    idx = data["A"].index
    decs = [
        dec(
            idx[i],
            *[
                buy(t, float(w), stop_price=data[t].close.iloc[i] * 0.97)
                for t, w in zip(
                    "ABC", rng.dirichlet(np.ones(3)) * 1.2 / 1.2, strict=True
                )
            ],
        )
        for i in range(0, 38, 5)
    ]
    res = run_engine(data, decs, cfg(), rf(), "2024-01-02", str(idx[-1].date()))
    assert (res.positions.shares >= 0).all()
    assert res.positions.groupby("date").weight.sum().max() <= 1 + 1e-9


def test_rf_accrues_on_cash_per_session():
    res = run(
        [flat(D0, 100), flat(D1, 100), flat(D2, 100), flat(D3, 100)], [], rf_pct=2.52
    )
    assert res.equity[D1] == pytest.approx(100_010) and res.equity[D2] == pytest.approx(
        100_020.001
    )


def test_unmentioned_tickers_keep_position_and_stops_and_no_decision_changes_nothing():
    a = bars([flat(D0, 100), flat(D1, 100), (D2, 90, 91, 88, 90), flat(D3, 90)])
    b = bars([flat(D0, 50), flat(D1, 50), flat(D2, 50), flat(D3, 50)])
    decs = [
        dec(D0, buy("A", 0.4, stop_price=95), buy("B", 0.4)),
        dec(D1, buy("B", 0.4)),
    ]
    res = run_engine({"A": a, "B": b}, decs, cfg(), rf(), "2024-01-02", "2024-01-05")
    stop = res.fills[res.fills.kind == "stop"]
    assert len(stop) == 1 and stop.iloc[0].ticker == "A" and stop.iloc[0].date == D2
    held_b = res.positions[res.positions.ticker == "B"].shares
    assert held_b.nunique() == 1  # B untouched (D2/D3 have no decision)


def test_decision_ignored_when_before_start_and_result_shapes():
    res = run(
        [flat(D0, 100), flat(D1, 100), flat(D2, 100), flat(D3, 100)],
        [dec("2023-12-29", buy("A", 1.0))],
    )
    assert res.fills.empty and list(res.equity.index) == [D0, D1, D2, D3]
    assert list(res.fills.columns) == [
        "date",
        "ticker",
        "side",
        "shares",
        "price",
        "kind",
        "slippage_cost",
    ]
