"""Background monitor: audits each fund's desk after runs and on a timer.

`audit(desk)` looks for runaway order bursts, agents retrying blocked orders, orders with
unknown broker outcomes, holdings that drift past the mandate, and strategy memos whose
claims do not check out. Each finding becomes a ModeratorEvent, written once (repeat
sweeps do not duplicate it) beside the desk, mirrored to `workspace/watchdog/events.jsonl`
and logged on the desk so `inspect_desk` shows it. A critical runaway trips the firm-wide
stop. Then flagged orders get a second opinion and the lessons file is refreshed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from datetime import UTC, datetime

import httpx

from backend.app.watchdog import claims, feedback, gate, opinion, store
from backend.app.watchdog.halt import SWITCH
from backend.app.watchdog.models import ModeratorEvent
from backend.app.watchdog.rules import parse_time

log = logging.getLogger("desk.watchdog")

WINDOW_SECONDS = 600
RUNAWAY_ORDERS = 10
RETRY_WARN = 3
RETRY_CRITICAL = 6
DRIFT_TOLERANCE = 1.05


def recent(stamps: list[str], now: datetime) -> list[str]:
    return [t for t in stamps if (now - parse_time(t)).total_seconds() <= WINDOW_SECONDS]


def bucket(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:") + f"{now.minute // 10}"


def order_events(desk, now: datetime) -> list[tuple[str, ModeratorEvent]]:
    found = []
    orders = list(desk.state["orders"].values())
    burst = recent([o["time"] for o in orders], now)
    if len(burst) > RUNAWAY_ORDERS:
        found.append(
            (
                f"runaway:{bucket(now)}",
                ModeratorEvent(
                    kind="runaway",
                    severity="critical",
                    subject="executor",
                    message=f"{len(burst)} paper orders in the last {WINDOW_SECONDS // 60} minutes; the watchdog tripped the firm-wide stop.",
                    details={"orders": len(burst)},
                ),
            )
        )
    blocked = [
        e["result"].get("agent") or "unknown agent"
        for e in desk.state["events"]
        if e["check"] == "paper_order_blocked" and recent([e["time"]], now)
    ]
    for agent, count in Counter(blocked).items():
        if count >= RETRY_WARN:
            critical = count >= RETRY_CRITICAL
            found.append(
                (
                    f"retry:{agent}:{bucket(now)}:{'critical' if critical else 'warn'}",
                    ModeratorEvent(
                        kind="retry_loop",
                        severity="critical" if critical else "warn",
                        subject=agent,
                        message=f"Agent {agent} had {count} orders blocked in {WINDOW_SECONDS // 60} minutes and keeps retrying"
                        + ("; the watchdog tripped the firm-wide stop." if critical else "."),
                        details={"blocked": count},
                    ),
                )
            )
    for o in orders:
        if o.get("status") == "unknown":
            found.append(
                (
                    f"unknown:{o['client_order_id']}",
                    ModeratorEvent(
                        kind="uncertain_order",
                        severity="warn",
                        subject=o["client_order_id"],
                        message=f"Order {o['client_order_id']} ({o['side']} {o['symbol']}) has no confirmed broker outcome; check Alpaca before anyone resubmits it.",
                        details={"reason": o.get("reason", "")},
                    ),
                )
            )
    return found


def position_events(desk, snapshot: dict) -> list[tuple[str, ModeratorEvent]]:
    try:
        policy = desk.policy()
    except ValueError:
        return []
    mandate = gate.mandate_for(desk, policy)
    equity = float(snapshot["account"]["equity"])
    capital = min(mandate.capital, equity) if mandate.capital else equity
    found = []
    for p in snapshot.get("positions", []):
        symbol, value, qty = p["symbol"], float(p["market_value"]), float(p["qty"])
        if qty < 0:
            found.append(
                (
                    f"short:{symbol}",
                    ModeratorEvent(
                        kind="position",
                        severity="critical",
                        subject=symbol,
                        message=f"The paper account is short {symbol}; {mandate.client}'s mandate is long-only.",
                    ),
                )
            )
        elif capital > 0 and value / capital > mandate.max_position * DRIFT_TOLERANCE:
            found.append(
                (
                    f"drift:{symbol}:{round(value / capital, 2)}",
                    ModeratorEvent(
                        kind="position",
                        severity="warn",
                        subject=symbol,
                        message=f"{symbol} has grown to {value / capital:.1%} of capital, past {mandate.client}'s {mandate.max_position:.0%} cap; consider trimming.",
                        details={"value": value, "capital": capital},
                    ),
                )
            )
        if symbol not in mandate.universe:
            found.append(
                (
                    f"outside:{symbol}",
                    ModeratorEvent(
                        kind="position",
                        severity="warn",
                        subject=symbol,
                        message=f"The shared paper account holds {symbol}, which is outside {mandate.client}'s approved list.",
                    ),
                )
            )
    return found


def claim_events(desk) -> list[tuple[str, ModeratorEvent]]:
    workspace = store.workspace_dir(desk).parent
    found = []
    for strategy in desk.state["strategies"].values():
        for event in claims.check_strategy_memos(workspace, strategy):
            key = f"claim:{event.details['strategy_id']}:{event.details['memo']}:{event.details['problem']}"
            found.append((key, event))
    return found


def record_outcomes(desk, state: dict) -> None:
    seen = state.setdefault("outcomes", {})
    for o in desk.state["orders"].values():
        status = str(o.get("status"))
        if status != "submitting" and seen.get(o["client_order_id"]) != status:
            detail = {k: o.get(k) for k in ["symbol", "side", "notional", "broker_id", "filled_qty", "filled_avg_price"]}
            feedback.record_outcome(desk, o["client_order_id"], status, detail)
            seen[o["client_order_id"]] = status


def emit(desk, event: ModeratorEvent) -> None:
    record = event.model_dump()
    store.append_jsonl(store.private_dir(desk) / feedback.EVENTS, record)
    store.append_jsonl(store.workspace_dir(desk) / feedback.EVENTS, record)
    with desk.lock:
        desk.event("watchdog_event", record)


def audit(desk, snapshot: dict | None = None, now: datetime | None = None, opinions: bool = True) -> list[ModeratorEvent]:
    """One pass over a desk. Returns only the events that are new since the last pass."""
    now = now or datetime.now(UTC)
    # Same lock order as the order path (desk, then store) so a sweep cannot deadlock an order.
    with desk.lock, store.LOCK:
        state = store.load_state(desk)
        seen = set(state.get("seen", []))
        candidates = order_events(desk, now) + claim_events(desk)
        if snapshot:
            candidates += position_events(desk, snapshot)
        new = []
        for key, event in candidates:
            if key in seen:
                continue
            seen.add(key)
            emit(desk, event)
            new.append(event)
            if event.kind in {"runaway", "retry_loop"} and event.severity == "critical":
                SWITCH.trip(event.message, "watchdog")
        record_outcomes(desk, state)
        state["seen"] = sorted(seen)[-2000:]
        state["last_audit"] = now.isoformat()
        store.save_state(desk, state)
    if opinions:
        opinion.review_flagged(desk)
    feedback.refresh_lessons(desk)
    return new


# ------------------------------------------------------------------- background loop


def managers(app) -> list:
    found = [getattr(app.state, "manager", None)]
    funds = getattr(app.state, "funds", None)
    if funds is not None:
        found += list(funds.managers.values())
    unique = {id(m): m for m in found if m is not None}
    return list(unique.values())


def account_or_none() -> dict | None:
    from backend.app.paper import account_snapshot

    try:
        return account_snapshot()
    except (ValueError, httpx.HTTPError):
        return None


def active(desk) -> bool:
    return desk.path.exists() or bool(desk.state["orders"] or desk.state["strategies"])


def sweep(app) -> dict[str, int]:
    from backend.app.desk import desk_for

    desks = [desk_for(m) for m in managers(app)]
    desks = [d for d in desks if active(d)]
    snapshot = account_or_none() if any(d.state["orders"] for d in desks) else None
    return {str(d.path.parent): len(audit(d, snapshot)) for d in desks}


async def run_forever(app, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            counts = await asyncio.to_thread(sweep, app)
            if any(counts.values()):
                log.info("watchdog sweep: %s", json.dumps(counts))
        except Exception:
            log.exception("watchdog sweep failed")
