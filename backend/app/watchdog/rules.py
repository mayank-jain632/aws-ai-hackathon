"""Deterministic pre-trade gate. No LLM anywhere in this path.

`review_order(order, mandate, portfolio)` runs every rule and returns a Verdict:
`block` if any rule blocks, otherwise `approve`, with near misses listed so the
feedback loop can learn from orders that almost tripped a limit.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from backend.app.watchdog import halt as halt_switch
from backend.app.watchdog.models import (
    RuleResult,
    Verdict,
    WatchMandate,
    WatchOrder,
    WatchPortfolio,
)

# Watchdog operating guardrails per risk band, used when a mandate does not set its own.
# These are operational limits on order flow, not evaluation thresholds (see D19).
GUARDRAILS = {
    "conservative": {
        "max_concentration": 0.50,
        "max_daily_turnover": 0.35,
        "max_order_fraction": 0.10,
        "price_band": 0.03,
    },
    "balanced": {
        "max_concentration": 0.65,
        "max_daily_turnover": 0.60,
        "max_order_fraction": 0.20,
        "price_band": 0.05,
    },
    "aggressive": {
        "max_concentration": 0.85,
        "max_daily_turnover": 1.00,
        "max_order_fraction": 0.35,
        "price_band": 0.08,
    },
}
RAPID_WINDOW_SECONDS = 60
RAPID_MAX_ORDERS = 5
DUPLICATE_WINDOW_SECONDS = 300
NEAR_MISS = 0.9
DEAD_STATUSES = {"rejected", "canceled", "cancelled", "expired", "blocked"}
QTY_PRICE_TOLERANCE = 0.05


def known_symbols() -> set[str]:
    from backend.app import data

    return set(data.ALL_TICKERS)


def money(x: float) -> str:
    return f"${x:,.0f}"


def pct(x: float) -> str:
    return f"{x:.1%}"


def parse_time(value: str) -> datetime:
    stamp = datetime.fromisoformat(value)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def guardrail(mandate: WatchMandate, name: str) -> float:
    own = getattr(mandate, name)
    return own if own is not None else GUARDRAILS[mandate.risk][name]


def ok(rule: str, message: str, value: float | None = None, limit: float | None = None) -> RuleResult:
    """Pass, or near miss when a measured value sits within 10% of its limit."""
    close = value is not None and limit and value / limit >= NEAR_MISS
    return RuleResult(
        rule=rule,
        severity="near_miss" if close else "pass",
        message=message,
        value=value,
        limit=limit,
    )


def block(rule: str, message: str, value: float | None = None, limit: float | None = None) -> RuleResult:
    return RuleResult(rule=rule, severity="block", message=message, value=value, limit=limit)


def info(rule: str, message: str) -> RuleResult:
    return RuleResult(rule=rule, severity="info", message=message)


def live_orders(portfolio: WatchPortfolio):
    return [o for o in portfolio.recent_orders if o.status.lower() not in DEAD_STATUSES]


# --------------------------------------------------------------------------- rules


def rule_emergency_stop(halt: str | None) -> RuleResult:
    if halt:
        return block("emergency_stop", f"{halt}. No orders go out until a person clears it.")
    return ok("emergency_stop", "No emergency stop is on.")


def rule_trading_permission(mandate: WatchMandate) -> RuleResult:
    if not mandate.trading_allowed:
        return block(
            "trading_permission",
            f"{mandate.client} has not given permission for paper trading.",
        )
    return ok("trading_permission", "Paper trading is allowed for this client.")


def rule_universe(order: WatchOrder, mandate: WatchMandate) -> RuleResult:
    allowed = {s.upper() for s in mandate.universe}
    if order.symbol.upper() not in allowed:
        return block(
            "universe",
            f"{order.symbol} is outside {mandate.client}'s approved list ({', '.join(sorted(allowed))}).",
        )
    return ok("universe", f"{order.symbol} is in the approved list.")


def rule_known_ticker(order: WatchOrder, known: set[str]) -> RuleResult:
    if order.symbol.upper() not in known:
        return block(
            "known_ticker",
            f"{order.symbol} does not exist in the desk's price data, so nothing the agents claim about it can be checked.",
        )
    return ok("known_ticker", f"{order.symbol} exists in the desk's price data.")


def rule_backtest_pass(order: WatchOrder, portfolio: WatchPortfolio) -> RuleResult:
    verdict = (portfolio.backtest_verdict or "").upper()
    if verdict == "PASS":
        return ok("backtest_pass", "The strategy behind this order has a backend PASS.")
    if order.side == "sell":
        return info("backtest_pass", "No PASS on record, allowed because a sell only reduces risk.")
    shown = verdict or "no backtest"
    return block(
        "backtest_pass",
        f"The strategy behind this buy has {shown} on record; a backend PASS is required before buying.",
    )


def rule_quantity_sanity(order: WatchOrder, portfolio: WatchPortfolio) -> RuleResult:
    if not math.isfinite(order.notional) or order.notional <= 0:
        return block("quantity_sanity", f"Order value {order.notional} is not a positive dollar amount.")
    if order.qty is not None:
        if not math.isfinite(order.qty) or order.qty <= 0:
            return block("quantity_sanity", f"Quantity {order.qty} is not a positive number of shares.")
        if order.price:
            implied = order.qty * order.price
            if abs(implied - order.notional) / order.notional > QTY_PRICE_TOLERANCE:
                return block(
                    "quantity_sanity",
                    f"{order.qty:g} shares at ${order.price:,.2f} is {money(implied)}, not the stated {money(order.notional)}.",
                )
    held = portfolio.positions.get(order.symbol, 0.0)
    if order.side == "buy":
        if order.notional > portfolio.cash:
            return block(
                "quantity_sanity",
                f"Buying {money(order.notional)} needs more than the {money(portfolio.cash)} cash available.",
                order.notional,
                portfolio.cash,
            )
        return ok("quantity_sanity", "Cash covers the buy.", order.notional, portfolio.cash)
    if order.notional > held + 0.01:
        return block(
            "quantity_sanity",
            f"Selling {money(order.notional)} of {order.symbol} with only {money(held)} held would open a short.",
            order.notional,
            held,
        )
    return ok("quantity_sanity", "The sell is covered by the position held.", order.notional, held)


def rule_order_size(order: WatchOrder, mandate: WatchMandate, portfolio: WatchPortfolio) -> RuleResult:
    if mandate.max_order_notional and order.notional > mandate.max_order_notional:
        return block(
            "order_size",
            f"{money(order.notional)} is over the {money(mandate.max_order_notional)} per-order limit.",
            order.notional,
            mandate.max_order_notional,
        )
    cap = guardrail(mandate, "max_order_fraction")
    fraction = order.notional / portfolio.equity if portfolio.equity > 0 else math.inf
    if fraction > cap:
        return block(
            "order_size",
            f"One order of {money(order.notional)} is {pct(fraction)} of equity; a {mandate.risk} mandate allows at most {pct(cap)} per order.",
            fraction,
            cap,
        )
    return ok("order_size", f"Order is {pct(fraction)} of equity.", fraction, cap)


def capital_base(mandate: WatchMandate, portfolio: WatchPortfolio) -> float:
    if mandate.capital:
        return min(mandate.capital, portfolio.equity) if portfolio.equity > 0 else mandate.capital
    return portfolio.equity


def post_trade(order: WatchOrder, portfolio: WatchPortfolio) -> dict[str, float]:
    after = dict(portfolio.positions)
    delta = order.notional if order.side == "buy" else -order.notional
    after[order.symbol] = max(0.0, after.get(order.symbol, 0.0) + delta)
    return after


def rule_position_size(order: WatchOrder, mandate: WatchMandate, portfolio: WatchPortfolio) -> RuleResult:
    if order.side == "sell":
        return info("position_size", "A sell cannot grow a position.")
    base = capital_base(mandate, portfolio)
    size = post_trade(order, portfolio)[order.symbol]
    fraction = size / base if base > 0 else math.inf
    if fraction > mandate.max_position + 1e-9:
        return block(
            "position_size",
            f"Buying {money(order.notional)} of {order.symbol} would make it {pct(fraction)} of {mandate.client}'s {money(base)} capital; the {mandate.risk} mandate caps any one position at {pct(mandate.max_position)}.",
            fraction,
            mandate.max_position,
        )
    return ok(
        "position_size",
        f"{order.symbol} would be {pct(fraction)} of capital.",
        fraction,
        mandate.max_position,
    )


def rule_concentration(order: WatchOrder, mandate: WatchMandate, portfolio: WatchPortfolio) -> RuleResult:
    if order.side == "sell":
        return info("concentration", "A sell cannot raise concentration.")
    cap = guardrail(mandate, "max_concentration")
    top = sorted(post_trade(order, portfolio).values(), reverse=True)[:3]
    base = capital_base(mandate, portfolio)
    share = sum(top) / base if base > 0 else math.inf
    if share > cap:
        return block(
            "concentration",
            f"After this buy the three largest holdings would be {pct(share)} of capital; a {mandate.risk} mandate keeps them under {pct(cap)}.",
            share,
            cap,
        )
    return ok("concentration", f"Top three holdings would be {pct(share)} of capital.", share, cap)


def rule_drawdown(order: WatchOrder, mandate: WatchMandate, portfolio: WatchPortfolio) -> RuleResult:
    tested = portfolio.backtest_max_drawdown
    if order.side == "buy" and tested is not None and abs(tested) > mandate.max_drawdown:
        return block(
            "drawdown",
            f"The strategy's tested drawdown of {pct(abs(tested))} is deeper than the {pct(mandate.max_drawdown)} this client tolerates.",
            abs(tested),
            mandate.max_drawdown,
        )
    peak = max(portfolio.peak_equity or 0.0, portfolio.equity)
    drawdown = 1 - portfolio.equity / peak if peak > 0 else 0.0
    if order.side == "buy" and drawdown >= mandate.max_drawdown:
        return block(
            "drawdown",
            f"The account is {pct(drawdown)} below its peak, at or past the {pct(mandate.max_drawdown)} drawdown limit; only risk-reducing sells are allowed.",
            drawdown,
            mandate.max_drawdown,
        )
    return ok("drawdown", f"Account is {pct(drawdown)} below its peak.", drawdown, mandate.max_drawdown)


def rule_price_band(order: WatchOrder, mandate: WatchMandate, portfolio: WatchPortfolio) -> RuleResult:
    if order.price is None:
        return info("price_band", "Market order with no stated price; nothing to compare to the last close.")
    last = portfolio.last_close.get(order.symbol)
    if not last:
        return info("price_band", f"No last close for {order.symbol} to compare the ${order.price:,.2f} price against.")
    band = guardrail(mandate, "price_band")
    gap = abs(order.price / last - 1)
    if gap > band:
        return block(
            "price_band",
            f"${order.price:,.2f} is {pct(gap)} away from {order.symbol}'s last close of ${last:,.2f}; a {mandate.risk} mandate allows {pct(band)}.",
            gap,
            band,
        )
    return ok("price_band", f"Price is {pct(gap)} from the last close.", gap, band)


def rule_rapid_fire(order: WatchOrder, portfolio: WatchPortfolio, now: datetime) -> RuleResult:
    recent = [
        o for o in portfolio.recent_orders if (now - parse_time(o.time)).total_seconds() <= RAPID_WINDOW_SECONDS
    ]
    count = len(recent) + 1
    if count > RAPID_MAX_ORDERS:
        return block(
            "rapid_fire",
            f"This would be order {count} in {RAPID_WINDOW_SECONDS} seconds; more than {RAPID_MAX_ORDERS} looks like a runaway agent.",
            count,
            RAPID_MAX_ORDERS,
        )
    return ok("rapid_fire", f"{count} orders in the last {RAPID_WINDOW_SECONDS} seconds.", count, RAPID_MAX_ORDERS)


def rule_duplicate(order: WatchOrder, portfolio: WatchPortfolio, now: datetime) -> RuleResult:
    for past in live_orders(portfolio):
        if (
            past.symbol == order.symbol
            and past.side == order.side
            and past.client_order_id != order.client_order_id
            and abs(past.notional - order.notional) <= 0.01 * order.notional
            and (now - parse_time(past.time)).total_seconds() <= DUPLICATE_WINDOW_SECONDS
        ):
            return block(
                "duplicate",
                f"An identical {order.side} of {money(order.notional)} {order.symbol} went out at {past.time[11:19]} UTC under a different order id; this looks like a double submit.",
            )
    return ok("duplicate", "No matching order in the last five minutes.")


def rule_wash_trade(order: WatchOrder, portfolio: WatchPortfolio, now: datetime) -> RuleResult:
    opposite = "sell" if order.side == "buy" else "buy"
    for past in live_orders(portfolio):
        if past.symbol == order.symbol and past.side == opposite and parse_time(past.time).date() == now.date():
            return block(
                "wash_trade",
                f"{order.symbol} was already {'bought' if opposite == 'buy' else 'sold'} today; a same-day {order.side} is a wash-trade pattern.",
            )
    return ok("wash_trade", f"No opposite-side {order.symbol} order today.")


def today_orders(portfolio: WatchPortfolio, now: datetime):
    return [o for o in live_orders(portfolio) if parse_time(o.time).date() == now.date()]


def rule_turnover(order: WatchOrder, mandate: WatchMandate, portfolio: WatchPortfolio, now: datetime) -> RuleResult:
    cap = guardrail(mandate, "max_daily_turnover")
    traded = sum(o.notional for o in today_orders(portfolio, now)) + order.notional
    base = capital_base(mandate, portfolio)
    turnover = traded / base if base > 0 else math.inf
    if turnover > cap:
        return block(
            "turnover",
            f"Today's trading would reach {money(traded)}, {pct(turnover)} of capital; a {mandate.risk} mandate caps daily turnover at {pct(cap)}.",
            turnover,
            cap,
        )
    return ok("turnover", f"Daily turnover would be {pct(turnover)}.", turnover, cap)


def rule_daily_orders(mandate: WatchMandate, portfolio: WatchPortfolio, now: datetime) -> RuleResult:
    if not mandate.max_daily_orders:
        return info("daily_orders", "No daily order count limit on this mandate.")
    count = len(today_orders(portfolio, now)) + 1
    if count > mandate.max_daily_orders:
        return block(
            "daily_orders",
            f"This would be order {count} today; the mandate allows {mandate.max_daily_orders}.",
            count,
            mandate.max_daily_orders,
        )
    return ok("daily_orders", f"Order {count} of {mandate.max_daily_orders} today.", count, mandate.max_daily_orders)


# --------------------------------------------------------------------------- gate


def review_order(
    order: WatchOrder,
    mandate: WatchMandate,
    portfolio: WatchPortfolio,
    *,
    halt: str | None = None,
    now: datetime | None = None,
    known: set[str] | None = None,
) -> Verdict:
    """Run every rule. Block if any rule blocks. Pure apart from reading the halt switch."""
    now = now or datetime.now(UTC)
    halt = halt or halt_switch.halt_reason()
    order = order.model_copy(update={"symbol": order.symbol.upper()})
    results = [
        rule_emergency_stop(halt),
        rule_trading_permission(mandate),
        rule_universe(order, mandate),
        rule_known_ticker(order, known if known is not None else known_symbols()),
        rule_backtest_pass(order, portfolio),
        rule_quantity_sanity(order, portfolio),
        rule_order_size(order, mandate, portfolio),
        rule_position_size(order, mandate, portfolio),
        rule_concentration(order, mandate, portfolio),
        rule_drawdown(order, mandate, portfolio),
        rule_price_band(order, mandate, portfolio),
        rule_rapid_fire(order, portfolio, now),
        rule_duplicate(order, portfolio, now),
        rule_wash_trade(order, portfolio, now),
        rule_turnover(order, mandate, portfolio, now),
        rule_daily_orders(mandate, portfolio, now),
    ]
    blocked = [r for r in results if r.severity == "block"]
    near = [r for r in results if r.severity == "near_miss"]
    if blocked:
        reason = " ".join(r.message for r in blocked)
    else:
        reason = f"Approved: all {len(results)} checks passed."
        if near:
            reason += " Close to a limit: " + ", ".join(r.rule for r in near) + "."
    return Verdict(
        decision="block" if blocked else "approve",
        reason=reason,
        blocked_by=[r.rule for r in blocked],
        near_misses=[r.rule for r in near],
        rules=results,
        order=order,
        client=mandate.client,
        risk=mandate.risk,
    )
