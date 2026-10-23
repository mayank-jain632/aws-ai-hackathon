"""Synthetic test bars only; every simulated fill uses the actual WF engine."""
import json
import threading
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.app import historical_execution as historical
from backend.app import paper


@pytest.fixture
def replay(tmp_path, monkeypatch):
    dates = pd.bdate_range("2026-01-05", periods=5)
    bars = pd.DataFrame({"open": [99, 110, 120, 130, 140], "high": [102, 114, 124, 134, 144],
                         "low": [98, 109, 119, 129, 139], "close": [100, 112, 122, 132, 142],
                         "volume": [10000] * 5}, index=dates, dtype=float)
    monkeypatch.setattr(historical.market, "load_bars", lambda *args: {"AAPL": bars.copy()})
    monkeypatch.setattr(historical.market, "rf_annual_pct", lambda idx, *args: pd.Series(0., index=idx))
    monkeypatch.setattr(paper, "broker", lambda *args: pytest.fail("Historical execution called Alpaca"))
    strategy = {"weights": {"AAPL": .2}, "cutoff": "2026-01-05", "end": "2026-01-09"}
    desk = SimpleNamespace(path=tmp_path / "desk.json", lock=threading.RLock(),
                           manager=SimpleNamespace(context=json.dumps({"mandate": {"capital": 1000, "min_cash": 5, "max_sector": 40}}), paused=False),
                           state={"tests": {"strategy": {"evaluation_id": "evaluation", "engine": "wf", "leakage": "Synthetic test fixture"}}},
                           strategy=lambda sid: strategy if sid == "strategy" else (_ for _ in ()).throw(ValueError("Unknown strategy")),
                           test_is_current=lambda sid: True,
                           policy=lambda: SimpleNamespace(max_order_notional=200, max_position=.2))
    return historical.HistoricalReplay(desk), desk, bars


def test_real_engine_next_open_slippage_accounting_and_persistence(replay):
    service, desk, _ = replay
    start = service.start("strategy", "evaluation")
    assert start["account"]["cash"] == 1000 and start["quotes"] == {"AAPL": 100}
    result = service.place_order(start["replay_id"], start["clock"], "AAPL", "buy", 100, "historic-order-1")
    fill = result["fills"][0]
    assert fill["date"] == "2026-01-06" and fill["price"] == pytest.approx(110 * 1.0005)
    assert fill["shares"] == 1
    assert result["account"]["cash"] == pytest.approx(1000 - fill["price"])
    assert result["account"]["equity"] == pytest.approx(1000 - fill["price"] + 112)
    assert result["orders"][0]["status"] == "simulated_fill"
    assert result["orders"][0]["filled_notional"] == pytest.approx(fill["price"])
    assert historical.HistoricalReplay(desk).inspect(start["replay_id"]) == result
    assert service.place_order(start["replay_id"], start["clock"], "AAPL", "buy", 100, "historic-order-1") == result
    with pytest.raises(ValueError, match="different request"):
        service.place_order(start["replay_id"], start["clock"], "AAPL", "buy", 101, "historic-order-1")


def test_sell_uses_virtual_position_and_actual_next_open(replay):
    service, _, _ = replay
    start = service.start("strategy", "evaluation")
    bought = service.place_order(start["replay_id"], start["clock"], "AAPL", "buy", 100, "historic-order-1")
    sold = service.place_order(start["replay_id"], bought["clock"], "AAPL", "sell", 112, "historic-order-2")
    assert sold["account"]["positions"] == {}
    assert sold["fills"][-1]["side"] == "sell"
    assert sold["fills"][-1]["price"] == pytest.approx(120 * .9995)


def test_identity_clock_boundaries_and_no_short_or_outside_strategy(replay):
    service, desk, _ = replay
    start = service.start("strategy", "evaluation")
    with pytest.raises(ValueError, match="clock changed"):
        service.place_order(start["replay_id"], "2026-01-06", "AAPL", "buy", 100, "historic-order-1")
    with pytest.raises(ValueError, match="Unknown historical replay"):
        service.inspect("other-fund")
    with pytest.raises(ValueError, match="outside"):
        service.place_order(start["replay_id"], start["clock"], "MSFT", "buy", 100, "historic-order-1")
    with pytest.raises(ValueError, match="long-only"):
        service.place_order(start["replay_id"], start["clock"], "AAPL", "sell", 100, "historic-order-1")
    desk.state["tests"]["strategy"]["evaluation_id"] = "replaced"
    assert service.inspect(start["replay_id"]) == start
    with pytest.raises(ValueError, match="exact current"):
        service.advance(start["replay_id"], start["clock"])


def test_future_bars_do_not_affect_current_view_or_next_fill(replay):
    service, _, bars = replay
    start = service.start("strategy", "evaluation")
    bars.loc["2026-01-07":, ["open", "close", "high", "low"]] *= 100
    assert service.inspect(start["replay_id"]) == start
    filled = service.place_order(start["replay_id"], start["clock"], "AAPL", "buy", 100, "historic-order-1")
    assert filled["clock"] == "2026-01-06" and filled["quotes"]["AAPL"] == 112
    assert filled["fills"][0]["price"] == pytest.approx(110 * 1.0005)
    assert all(row["date"] <= filled["clock"] for row in filled["equity_curve"])


def test_volume_limited_partial_fill_and_end_clock(replay):
    service, _, bars = replay
    bars.loc["2026-01-06", "volume"] = 1
    start = service.start("strategy", "evaluation")
    state = service.place_order(start["replay_id"], start["clock"], "AAPL", "buy", 100, "historic-order-1")
    assert state["fills"][0]["shares"] == pytest.approx(.05)
    assert state["orders"][0]["status"] == "simulated_partial_fill"
    while not state["complete"]:
        state = service.advance(state["replay_id"], state["clock"])
    assert state["clock"] == "2026-01-09"
    with pytest.raises(ValueError, match="complete"):
        service.advance(state["replay_id"], state["clock"])


def test_ledger_is_persisted_and_prior_prices_cannot_rewrite_fills(replay):
    service, _, bars = replay
    assert service.current() is None
    start = service.start("strategy", "evaluation")
    filled = service.place_order(start["replay_id"], start["clock"], "AAPL", "buy", 100, "historic-order-1")
    bars.loc["2026-01-06", "open"] = 999
    assert service.current() == filled
    assert json.loads(service.path.read_text())["ledger"]["fills"] == filled["fills"]
    with pytest.raises(ValueError, match="inputs changed"):
        service.advance(filled["replay_id"], filled["clock"])


def test_real_snapshot_next_open_and_virtual_fill(tmp_path, monkeypatch):
    """Local recorded price data, no model or broker call."""
    from backend.app.wf import market

    strategy = {"weights": {"AAPL": .2}, "cutoff": "2025-10-06", "end": "2025-10-08"}
    if not (market.DEFAULT_DATA_DIR / "prices" / "AAPL.csv").exists():
        pytest.skip("Recorded WF snapshot unavailable")
    desk = SimpleNamespace(path=tmp_path / "desk.json", lock=threading.RLock(), manager=SimpleNamespace(context="", paused=False),
                           state={"tests": {"strategy": {"evaluation_id": "evaluation", "engine": "wf"}}},
                           strategy=lambda _: strategy, test_is_current=lambda _: True,
                           policy=lambda: SimpleNamespace(max_order_notional=2000, max_position=.2))
    monkeypatch.setattr(paper, "broker", lambda *args: pytest.fail("Historical fill called broker"))
    service = historical.HistoricalReplay(desk)
    start = service.start("strategy", "evaluation")
    filled = service.place_order(start["replay_id"], start["clock"], "AAPL", "buy", 1000, "real-bars-order-1")
    bars = market.load_bars(tickers=["AAPL"])["AAPL"]
    fill = filled["fills"][0]
    assert fill["date"] == "2025-10-07"
    assert fill["price"] == pytest.approx(float(bars.loc[fill["date"], "open"]) * 1.0005)
    assert fill["shares"] == pytest.approx(1000 / float(bars.loc[start["clock"], "close"]))
    assert filled["source"] == "historical_simulation"
