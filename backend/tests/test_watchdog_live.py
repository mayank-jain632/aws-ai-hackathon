"""Live Alpaca context in the gate: parsing, rules that use it, and the fallback."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.app.desk import Policy, desk_for
from backend.app.watchdog import gate, market
from backend.app.watchdog.models import (
    LiveMarket,
    WatchMandate,
    WatchOrder,
    WatchPortfolio,
)
from backend.app.watchdog.rules import review_order

NOW = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_DIR", str(tmp_path / "watchdog-global"))
    market.CACHE.clear()


def live(**overrides):
    base = {
        "source": "test",
        "tradable": {"AAPL": True, "MSFT": True},
        "last_trade": {"AAPL": 250.0, "MSFT": 400.0},
        "prev_close": {"AAPL": 248.0, "MSFT": 360.0},
        "market_open": True,
        "equity_peak": 100_000.0,
    }
    return LiveMarket(**{**base, **overrides})


def review(order, live_market, risk="conservative"):
    mandate = WatchMandate(
        client="Calder Family Trust", risk=risk, trading_allowed=True,
        universe=["AAPL", "MSFT", "TSLA"], capital=100_000, max_position=0.25, max_drawdown=0.12,
    )
    portfolio = WatchPortfolio(equity=100_000, cash=100_000, backtest_verdict="PASS", live=live_market)
    return review_order(order, mandate, portfolio, now=NOW, known={"AAPL", "MSFT"})


def rule(verdict, name):
    return next(r for r in verdict.rules if r.rule == name)


def test_venue_tradability_overrides_snapshot_universe():
    tsla = WatchOrder(symbol="TSLA", side="buy", notional=5_000)
    assert "known_ticker" in review(tsla, None).blocked_by
    assert review(tsla, live(tradable={"TSLA": True}, last_trade={}, prev_close={})).decision == "approve"
    halted = review(WatchOrder(symbol="AAPL", side="buy", notional=5_000), live(tradable={"AAPL": False}))
    assert halted.blocked_by == ["known_ticker"]
    assert "Alpaca does not list AAPL" in halted.reason


def test_market_buy_into_a_fast_move_is_blocked():
    # MSFT is up 11.1% on the day; conservative allows 6% for market orders.
    verdict = review(WatchOrder(symbol="MSFT", side="buy", notional=5_000), live())
    assert verdict.blocked_by == ["price_band"]
    assert "11.1% from yesterday's $360.00 close" in verdict.reason
    assert review(WatchOrder(symbol="MSFT", side="buy", notional=5_000), live(), risk="aggressive").decision == "approve"
    assert review(WatchOrder(symbol="AAPL", side="buy", notional=5_000), live()).decision == "approve"


def test_market_hours_is_informational():
    closed = review(WatchOrder(symbol="AAPL", side="buy", notional=5_000), live(market_open=False))
    assert closed.decision == "approve"
    assert "Market is closed" in rule(closed, "market_hours").message


def test_live_failure_falls_back_to_snapshot_and_says_so():
    verdict = review(WatchOrder(symbol="AAPL", side="buy", notional=5_000), LiveMarket(source="unavailable", error="HTTP 503"))
    assert verdict.decision == "approve"
    assert rule(verdict, "known_ticker").message == "AAPL exists in the desk's price data."
    assert "checks used the desk snapshot" in rule(verdict, "market_hours").message


def test_live_market_parses_alpaca_responses(monkeypatch):
    responses = {
        "/v2/assets/AAPL": {"symbol": "AAPL", "status": "active", "tradable": True},
        "/v2/assets/ZZZZ": None,
        "/v2/stocks/snapshots": {"AAPL": {"latestTrade": {"p": 251.5}, "prevDailyBar": {"c": 249.0}}},
        "/v2/clock": {"is_open": False},
        "/v2/account/portfolio/history": {"equity": [100000, 101250.5, None, 99800]},
    }
    calls = []

    def fake_get(base, path, params=None):
        calls.append(path)
        return responses[path]

    monkeypatch.setattr(market, "get", fake_get)
    result = market.live_market(["AAPL", "ZZZZ"])
    assert result.error is None
    assert result.tradable == {"AAPL": True, "ZZZZ": False}
    assert result.last_trade == {"AAPL": 251.5} and result.prev_close == {"AAPL": 249.0}
    assert result.market_open is False and result.equity_peak == 101250.5
    market.live_market(["AAPL", "ZZZZ"])
    assert calls.count("/v2/clock") == 1


def test_live_market_without_credentials_reports_error(monkeypatch):
    monkeypatch.setattr(market, "credentials", lambda: None)
    result = market.live_market(["AAPL"])
    assert result.source == "unavailable" and "not configured" in result.error


def test_gate_uses_live_previous_close_and_broker_equity_peak(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_LIVE_DATA", "1")
    monkeypatch.setattr(market, "live_market", lambda symbols: live(equity_peak=125_000.0))
    desk = desk_for(SimpleNamespace(registry=tmp_path / "agents.json", paused=False))
    desk.set_policy(
        Policy(universe=["AAPL", "MSFT"], max_position=0.5, max_drawdown=0.15, min_sharpe=0,
               min_excess_return=0, max_order_notional=5000, max_daily_orders=5, trading_allowed=True)
    )
    snapshot = {"account": {"equity": "100000", "cash": "100000"}, "positions": []}
    portfolio = gate.portfolio_for(desk, None, snapshot, "AAPL")
    assert portfolio.peak_equity == 125_000.0
    assert portfolio.last_close["MSFT"] == 360.0
    assert portfolio.live.market_open is True
