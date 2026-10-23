"""Each deterministic watchdog rule, one approve and one block case where it applies."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.app.watchdog import (
    SWITCH,
    PastOrder,
    WatchMandate,
    WatchOrder,
    WatchPortfolio,
    review_order,
)

NOW = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_DIR", str(tmp_path / "watchdog"))


def mandate(**overrides):
    base = {
        "client": "Calder Family Trust",
        "risk": "balanced",
        "trading_allowed": True,
        "universe": ["AAPL", "MSFT", "NVDA", "JPM"],
        "capital": 100_000,
        "max_position": 0.20,
        "max_drawdown": 0.15,
    }
    return WatchMandate(**{**base, **overrides})


def portfolio(**overrides):
    base = {
        "equity": 100_000,
        "cash": 100_000,
        "positions": {},
        "backtest_verdict": "PASS",
        "backtest_max_drawdown": -0.08,
    }
    return WatchPortfolio(**{**base, **overrides})


def order(**overrides):
    base = {"symbol": "AAPL", "side": "buy", "notional": 5_000, "client_order_id": "order-0001"}
    return WatchOrder(**{**base, **overrides})


def past(minutes_ago, **overrides):
    base = {
        "time": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "symbol": "MSFT",
        "side": "buy",
        "notional": 1_000,
        "client_order_id": f"past-{minutes_ago}",
        "status": "accepted",
    }
    return PastOrder(**{**base, **overrides})


def review(o=None, m=None, p=None, **kwargs):
    return review_order(o or order(), m or mandate(), p or portfolio(), now=NOW, **kwargs)


def rule(verdict, name):
    return next(r for r in verdict.rules if r.rule == name)


def test_clean_order_is_approved():
    verdict = review()
    assert verdict.decision == "approve"
    assert verdict.blocked_by == []
    assert verdict.reason.startswith("Approved: all 16 checks passed")


def test_emergency_stop_blocks_everything():
    verdict = review(halt="Firm-wide emergency stop is on (demo, set by Aaron)")
    assert verdict.decision == "block"
    assert verdict.blocked_by[0] == "emergency_stop"


def test_global_switch_is_read_when_no_halt_is_passed():
    SWITCH.trip("runaway executor", "watchdog")
    assert review().blocked_by == ["emergency_stop"]
    SWITCH.reset("checked", "Aaron")
    assert review().decision == "approve"


def test_trading_permission_off_blocks():
    verdict = review(m=mandate(trading_allowed=False))
    assert "trading_permission" in verdict.blocked_by
    assert "Calder Family Trust has not given permission" in verdict.reason


def test_symbol_outside_client_universe_blocks():
    verdict = review(o=order(symbol="XOM"))
    assert "universe" in verdict.blocked_by


def test_symbol_missing_from_our_data_blocks():
    verdict = review(o=order(symbol="ZZZZ"), m=mandate(universe=["ZZZZ"]))
    assert verdict.blocked_by == ["known_ticker"]


def test_lowercase_symbol_is_normalized():
    assert review(o=order(symbol="aapl")).decision == "approve"


def test_buy_without_pass_blocks_but_sell_is_allowed():
    assert "backtest_pass" in review(p=portfolio(backtest_verdict="FAIL")).blocked_by
    assert "backtest_pass" in review(p=portfolio(backtest_verdict=None)).blocked_by
    sell = review(
        o=order(side="sell", notional=1_000),
        p=portfolio(backtest_verdict=None, positions={"AAPL": 2_000}),
    )
    assert sell.decision == "approve"
    assert rule(sell, "backtest_pass").severity == "info"


def test_buy_beyond_cash_blocks():
    verdict = review(o=order(notional=6_000), p=portfolio(cash=5_000))
    assert "quantity_sanity" in verdict.blocked_by


def test_sell_more_than_held_blocks_as_short():
    verdict = review(o=order(side="sell", notional=3_000), p=portfolio(positions={"AAPL": 1_000}))
    assert "quantity_sanity" in verdict.blocked_by
    assert "short" in verdict.reason


def test_quantity_and_price_must_agree_with_notional():
    good = review(o=order(qty=20, price=250, notional=5_000), p=portfolio(last_close={"AAPL": 250}))
    assert good.decision == "approve"
    bad = review(o=order(qty=200, price=250, notional=5_000), p=portfolio(last_close={"AAPL": 250}))
    assert "quantity_sanity" in bad.blocked_by


@pytest.mark.parametrize("notional", [0.0, -50.0, float("nan")])
def test_nonpositive_or_nan_notional_blocks(notional):
    assert "quantity_sanity" in review(o=order(notional=notional)).blocked_by


def test_per_order_dollar_limit_blocks():
    verdict = review(m=mandate(max_order_notional=2_000))
    assert "order_size" in verdict.blocked_by


def test_order_fraction_of_equity_follows_risk_band():
    # 15% of equity in one order: fine for balanced (20%), too much for conservative (10%).
    big = order(notional=15_000)
    assert "order_size" not in review(o=big, m=mandate(max_position=0.5)).blocked_by
    conservative = mandate(risk="conservative", max_position=0.5)
    assert "order_size" in review(o=big, m=conservative).blocked_by


def test_position_size_counts_existing_holding():
    verdict = review(o=order(notional=10_000), p=portfolio(positions={"AAPL": 15_000}, cash=85_000))
    assert verdict.blocked_by == ["position_size"]
    assert "25.0%" in verdict.reason


def test_concentration_of_top_three_holdings_blocks():
    # Top three after the buy: 60% of capital. Balanced allows 65%, conservative 50%.
    held = {"MSFT": 20_000, "NVDA": 20_000, "JPM": 20_000}
    book = portfolio(positions=held, cash=40_000)
    assert "concentration" in review(o=order(notional=10_000), p=book).near_misses
    verdict = review(o=order(notional=10_000), m=mandate(risk="conservative"), p=book)
    assert verdict.blocked_by == ["concentration"]


def test_account_drawdown_blocks_buys_but_allows_sells():
    hurt = portfolio(equity=80_000, cash=60_000, peak_equity=100_000, positions={"AAPL": 20_000})
    assert "drawdown" in review(p=hurt).blocked_by
    assert review(o=order(side="sell", notional=5_000), p=hurt).decision == "approve"


def test_strategy_tested_drawdown_beyond_mandate_blocks():
    verdict = review(p=portfolio(backtest_max_drawdown=-0.30))
    assert "drawdown" in verdict.blocked_by


def test_price_far_from_last_close_blocks():
    near = review(o=order(qty=20, price=251, notional=5_020), p=portfolio(last_close={"AAPL": 250}))
    assert near.decision == "approve"
    far = review(o=order(qty=20, price=300, notional=6_000), p=portfolio(last_close={"AAPL": 250}))
    assert "price_band" in far.blocked_by


def test_market_order_skips_price_band():
    assert rule(review(), "price_band").severity == "info"


def test_rapid_fire_blocks_sixth_order_in_a_minute():
    burst = [past(0, symbol=s, client_order_id=f"b{i}") for i, s in enumerate(["MSFT", "NVDA", "JPM", "MSFT", "NVDA"])]
    verdict = review(p=portfolio(recent_orders=burst))
    assert "rapid_fire" in verdict.blocked_by


def test_duplicate_order_under_new_id_blocks():
    twin = past(2, symbol="AAPL", notional=5_000, client_order_id="other-id")
    assert "duplicate" in review(p=portfolio(recent_orders=[twin])).blocked_by
    old_twin = past(30, symbol="AAPL", notional=5_000, client_order_id="other-id")
    assert "duplicate" not in review(p=portfolio(recent_orders=[old_twin])).blocked_by


def test_same_day_opposite_side_is_wash_trade():
    sold = past(90, symbol="AAPL", side="sell", notional=3_000)
    assert "wash_trade" in review(p=portfolio(recent_orders=[sold])).blocked_by
    rejected = past(90, symbol="AAPL", side="sell", notional=3_000, status="rejected")
    assert "wash_trade" not in review(p=portfolio(recent_orders=[rejected])).blocked_by


def test_daily_turnover_cap_blocks():
    traded = [past(100 + i, symbol="MSFT", notional=9_000, client_order_id=f"t{i}") for i in range(7)]
    verdict = review(p=portfolio(recent_orders=traded))
    assert "turnover" in verdict.blocked_by


def test_daily_order_count_limit_blocks():
    earlier = [past(100 + i, client_order_id=f"d{i}") for i in range(3)]
    verdict = review(m=mandate(max_daily_orders=3), p=portfolio(recent_orders=earlier))
    assert "daily_orders" in verdict.blocked_by


def test_near_miss_is_reported_without_blocking():
    verdict = review(o=order(notional=19_000), m=mandate(max_position=0.20))
    assert verdict.decision == "approve"
    assert "position_size" in verdict.near_misses
    assert "Close to a limit" in verdict.reason


def test_oversized_order_for_conservative_client_reads_clearly():
    conservative = mandate(risk="conservative", max_position=0.10)
    verdict = review(o=order(symbol="NVDA", notional=40_000), m=conservative)
    assert verdict.decision == "block"
    assert {"order_size", "position_size", "turnover"} <= set(verdict.blocked_by)
    assert "conservative mandate caps any one position at 10.0%" in verdict.reason


def test_most_serious_block_leads_the_reason():
    verdict = review(o=order(symbol="NVDA", notional=40_000), m=mandate(risk="conservative", max_position=0.10))
    assert verdict.blocked_by[0] == "position_size"
    assert verdict.reason.endswith("It also breaks the order size and turnover limits.")
