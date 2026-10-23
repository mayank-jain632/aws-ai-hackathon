"""Adapter from the desk's live paper-order path to the pure `review_order` gate.

`paper.submit` calls `enforce(...)` after it has the Alpaca account snapshot and before
it records order intent, so every executor order passes the watchdog. A block raises
ValueError, which the existing order route records as `paper_order_blocked`.
"""

from __future__ import annotations

import json
import os

from backend.app.watchdog import feedback, market, store
from backend.app.watchdog.halt import halt_reason
from backend.app.watchdog.models import (
    PastOrder,
    Verdict,
    WatchMandate,
    WatchOrder,
    WatchPortfolio,
)
from backend.app.watchdog.rules import review_order


def fund_mandate(desk) -> dict | None:
    return json.loads(getattr(desk.manager, "context", "") or "{}").get("mandate")


def mandate_for(desk, policy) -> WatchMandate:
    """Strictest combination of the desk policy and the fund dashboard mandate."""
    fund = fund_mandate(desk)
    if not fund:
        return WatchMandate(
            client="Team 4 board",
            trading_allowed=policy.trading_allowed,
            universe=policy.universe,
            max_position=policy.max_position,
            max_drawdown=policy.max_drawdown,
            max_order_notional=policy.max_order_notional,
            max_daily_orders=policy.max_daily_orders,
        )
    allowed = set(fund.get("universe", policy.universe))
    return WatchMandate(
        client=fund.get("name", "this fund"),
        risk=fund.get("risk", "balanced"),
        trading_allowed=policy.trading_allowed
        and bool(fund.get("trading_allowed"))
        and fund.get("mode") == "paper",
        universe=[s for s in policy.universe if s in allowed],
        capital=fund.get("capital"),
        max_position=min(policy.max_position, fund.get("max_position", 100) / 100),
        max_drawdown=min(policy.max_drawdown, fund.get("max_drawdown", 100) / 100),
        max_order_notional=policy.max_order_notional,
        max_daily_orders=policy.max_daily_orders,
    )


def past_orders(desk) -> list[PastOrder]:
    return [
        PastOrder(
            time=o["time"],
            symbol=o["symbol"],
            side=o["side"],
            notional=o["notional"],
            client_order_id=o.get("client_order_id", ""),
            status=str(o.get("status", "submitted")),
        )
        for o in desk.state["orders"].values()
    ]


def own_holdings(desk, snapshot: dict) -> dict[str, float]:
    """Market value of what this fund itself bought and still holds, from its own filled orders."""
    qty, fill_price = {}, {}
    for o in list(desk.state["orders"].values()):
        filled = float(o.get("filled_qty") or 0)
        if filled <= 0:
            continue
        qty[o["symbol"]] = qty.get(o["symbol"], 0.0) + (filled if o["side"] == "buy" else -filled)
        if o.get("filled_avg_price"):
            fill_price[o["symbol"]] = float(o["filled_avg_price"])
    mark = {
        p["symbol"]: float(p["market_value"]) / float(p["qty"])
        for p in snapshot.get("positions", [])
        if float(p.get("qty") or 0) > 0
    }
    return {s: q * mark.get(s, fill_price.get(s, 0.0)) for s, q in qty.items() if q > 0}


def recheck_halt(desk) -> None:
    """Last check before the broker call: the firm-wide stop may have been set mid-review."""
    reason = halt_reason(desk)
    if reason:
        raise ValueError(f"Watchdog blocked this order: {reason}. No orders go out until a person clears it.")


def live_market(symbols: list[str]):
    """Live venue data unless turned off (tests set WATCHDOG_LIVE_DATA=0)."""
    if os.getenv("WATCHDOG_LIVE_DATA", "1") == "0":
        return None
    return market.live_market(symbols)


def portfolio_for(desk, strategy_id: str | None, snapshot: dict, symbol: str | None = None) -> WatchPortfolio:
    account = snapshot["account"]
    equity = float(account["equity"])
    positions, last_close = {}, {}
    for p in snapshot.get("positions", []):
        positions[p["symbol"]] = positions.get(p["symbol"], 0.0) + float(p["market_value"])
        if p.get("lastday_price"):
            last_close[p["symbol"]] = float(p["lastday_price"])
    live = live_market(sorted({*positions, *([symbol] if symbol else [])}))
    if live and not live.error:
        last_close.update(live.prev_close)
    with store.LOCK:
        state = store.load_state(desk)
        broker_peak = live.equity_peak if live and not live.error and live.equity_peak else 0.0
        state["peak_equity"] = max(state.get("peak_equity", 0.0), equity, broker_peak)
        store.save_state(desk, state)
    test = desk.state["tests"].get(strategy_id or "", {})
    tested_drawdown = test.get("metrics", {}).get("portfolio", {}).get("max_drawdown")
    return WatchPortfolio(
        equity=equity,
        cash=float(account["cash"]),
        positions=positions,
        own_positions=own_holdings(desk, snapshot),
        peak_equity=state["peak_equity"],
        last_close=last_close,
        recent_orders=past_orders(desk),
        backtest_verdict=test.get("verdict"),
        backtest_max_drawdown=tested_drawdown,
        live=live,
    )


def review_desk_order(desk, body, policy, snapshot, agent_id: str | None = None) -> Verdict:
    order = WatchOrder(
        symbol=body.symbol,
        side=body.side,
        notional=body.notional,
        client_order_id=body.client_order_id,
        strategy_id=body.strategy_id,
        agent_id=agent_id,
    )
    return review_order(
        order,
        mandate_for(desk, policy),
        portfolio_for(desk, body.strategy_id, snapshot, body.symbol.upper()),
        halt=halt_reason(desk),
    )


def enforce(desk, body, policy, snapshot, agent_id: str | None = None) -> Verdict:
    """Review, log the verdict for the feedback loop, and raise on a block."""
    verdict = review_desk_order(desk, body, policy, snapshot, agent_id)
    feedback.record_verdict(desk, verdict)
    if verdict.decision == "block":
        raise ValueError(f"Watchdog blocked this order: {verdict.reason}")
    return verdict
