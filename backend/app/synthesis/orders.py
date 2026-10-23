"""Deterministic order plan: frozen weights x capital - current holdings -> notional orders.

The executor agent used to do this arithmetic in prose. This function does it in code and
hands the executor a list it can submit one by one through the existing guarded
`submit_paper_order`. It submits nothing itself, and every limit it applies is re-checked
by `backend.app.paper.submit` at submission time.
"""

from __future__ import annotations

import re

from backend.app.desk import Policy
from backend.app.synthesis.schema import OrderPlan, PlannedOrder

MIN_TRADE = 5.0  # dollars; smaller rebalances are noise


def _order_id(run: str, symbol: str, side: str) -> str:
    raw = f"{run}-{symbol}-{side}"
    return re.sub(r"[^a-zA-Z0-9_-]", "", raw)[:48]


def plan_orders(
    strategy_id: str,
    weights: dict[str, float],
    snapshot: dict,
    policy: Policy,
    mandate: dict | None,
    run_tag: str,
) -> OrderPlan:
    account = snapshot["account"]
    equity, cash = float(account["equity"]), float(account["cash"])
    positions = {p["symbol"]: float(p["market_value"]) for p in snapshot.get("positions", [])}
    blocked: list[str] = []
    skipped: dict[str, str] = {}

    if account.get("status") != "ACTIVE" or account.get("trading_blocked") or account.get("account_blocked"):
        blocked.append("paper account is not active for trading")
    if snapshot.get("open_orders"):
        blocked.append(f"{len(snapshot['open_orders'])} open orders must resolve first")
    if equity <= 0:
        blocked.append("account equity is not positive")
    if any(v < 0 for v in positions.values()):
        blocked.append("account holds a short position")

    capital = equity
    position_cap = policy.max_position
    if mandate:
        capital = min(capital, float(mandate.get("capital", capital)))
        position_cap = min(position_cap, float(mandate.get("max_position", 100)) / 100)
        if mandate.get("max_sector", 100) < 100:
            blocked.append("sector limit has no enforcement engine yet")
        if mandate.get("min_cash", 0) or mandate.get("exclusions") or mandate.get("rebalance", "monthly") != "monthly":
            blocked.append("cash reserve, exclusions or non-monthly rebalance need a matching engine")

    sells: list[PlannedOrder] = []
    buys: list[PlannedOrder] = []
    for symbol in sorted(set(weights) | set(positions)):
        target_w = min(weights.get(symbol, 0.0), position_cap)
        target = target_w * capital
        current = positions.get(symbol, 0.0)
        delta = target - current
        if symbol not in weights and current > 0:
            note = "not in strategy; sell to zero"
        elif abs(delta) < MIN_TRADE:
            skipped[symbol] = f"within {MIN_TRADE:.0f} of target"
            continue
        else:
            note = ""
        side = "buy" if delta > 0 else "sell"
        notional = abs(delta)
        if notional > policy.max_order_notional:
            notional = policy.max_order_notional
            note = (note + "; " if note else "") + "capped at max_order_notional, more orders needed"
        if symbol not in weights and side == "buy":
            continue
        order = PlannedOrder(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            notional=round(notional, 2),
            client_order_id=_order_id(run_tag, symbol, side),
            target_value=round(target, 2),
            current_value=round(current, 2),
            note=note,
        )
        (sells if side == "sell" else buys).append(order)

    # sells first, largest first; buys sized against cash on hand only (sell proceeds are
    # not assumed to settle in time for the same batch)
    sells.sort(key=lambda o: -o.notional)
    buys.sort(key=lambda o: -o.notional)
    spendable = cash
    kept_buys: list[PlannedOrder] = []
    for b in buys:
        if b.notional <= spendable:
            kept_buys.append(b)
            spendable -= b.notional
        elif spendable >= MIN_TRADE:
            kept_buys.append(b.model_copy(update={"notional": round(spendable, 2), "note": (b.note + "; " if b.note else "") + "reduced to available cash"}))
            spendable = 0.0
        else:
            skipped[b.symbol] = "no cash left in this batch"
    orders = sells + kept_buys
    if len(orders) > policy.max_daily_orders:
        for o in orders[policy.max_daily_orders :]:
            skipped[o.symbol] = "over max_daily_orders; next batch"
        orders = orders[: policy.max_daily_orders]
    if not orders and not blocked:
        blocked.append("nothing to trade: holdings already match the strategy")

    return OrderPlan(
        strategy_id=strategy_id,
        capital=round(capital, 2),
        cash=round(cash, 2),
        orders=orders,
        blocked=blocked,
        skipped=skipped,
        ready=not blocked and bool(orders),
    )
