"""Feedback log and the lessons file it is distilled into.

Every verdict, second opinion and later order outcome is appended to `feedback.jsonl`
beside the desk. `refresh_lessons` turns that log into a short `LESSONS.md` in the fund's
shared workspace, which the strategy and executor agents read on their next run (through
the `watchdog_lessons` tool or the file itself). That is how what the watchdog catches
makes the other agents better.
"""

from __future__ import annotations

from collections import Counter
from uuid import uuid4

from backend.app.watchdog import aws, store
from backend.app.watchdog.models import Verdict, utcnow
from backend.app.watchdog.rules import money

FEEDBACK = "feedback.jsonl"
EVENTS = "events.jsonl"
LESSONS = "LESSONS.md"

ADVICE = {
    "emergency_stop": "No order goes out while a stop is on. Do not retry; report it and wait for a person to clear it.",
    "trading_permission": "This client has not allowed paper trading. Do not submit orders; ask a person to change the mandate.",
    "universe": "Trade only tickers on the client's approved list.",
    "known_ticker": "Trade only tickers the desk has price data for, so every claim can be checked.",
    "backtest_pass": "Buy only for a strategy with a current backend PASS. A failed strategy does not pass under a new name.",
    "quantity_sanity": "Check cash and holdings with alpaca_paper_account first. Never sell more than you hold.",
    "order_size": "Split large trades. One order must stay under the per-order dollar limit and the risk band's share of equity.",
    "position_size": "Size each buy so the position after the trade stays under the mandate's single-position cap.",
    "concentration": "Spread exposure. The three largest holdings share a combined cap set by the risk band.",
    "drawdown": "In a drawdown only reduce risk. A strategy tested deeper than the client's drawdown limit cannot buy.",
    "price_band": "Use prices near the last close. A price far from it looks like a fat finger.",
    "rapid_fire": "Slow down. Bursts of orders look like a runaway loop and can trip the emergency stop.",
    "duplicate": "Never resubmit an order under a new client_order_id. Check the first order's status instead.",
    "wash_trade": "Do not buy and sell the same ticker on the same day.",
    "turnover": "Spread rebalancing across days. Daily turnover is capped by risk band.",
    "daily_orders": "The mandate caps orders per day. Batch trades instead of sending many small ones.",
    "desk_check": "The desk's own gates refused the order (policy, review, approval, strategy target or cash). Fix the named cause before resubmitting.",
}


def describe(e: dict) -> str:
    if not e.get("symbol"):
        return "an order"
    return f"{e['side']} {money(e['notional'])} {e['symbol']}"


def log_path(desk):
    return store.private_dir(desk) / FEEDBACK


def entries(desk, limit: int | None = None) -> list[dict]:
    return store.read_jsonl(log_path(desk), limit)


def append(desk, entry: dict) -> dict:
    entry = {"id": uuid4().hex[:12], "time": utcnow(), **entry}
    store.append_jsonl(log_path(desk), entry)
    return entry


def record_verdict(desk, verdict: Verdict) -> dict:
    if verdict.decision == "block":
        kind, rules = "block", verdict.blocked_by
    elif verdict.near_misses:
        kind, rules = "near_miss", verdict.near_misses
    else:
        kind, rules = "approve", []
    order = verdict.order
    entry = append(
        desk,
        {
            "kind": kind,
            "client": verdict.client,
            "risk": verdict.risk,
            "rules": rules,
            "reason": verdict.reason,
            "symbol": order.symbol,
            "side": order.side,
            "notional": order.notional,
            "client_order_id": order.client_order_id,
            "strategy_id": order.strategy_id,
            "agent_id": order.agent_id,
        },
    )
    fund = store.fund_label(desk)
    aws.publish_verdict(verdict, fund)
    if kind != "approve":
        aws.remember(
            desk,
            f"Watchdog {kind.replace('_', ' ')} for {verdict.client} ({verdict.risk} mandate): "
            f"{order.side} {money(order.notional)} {order.symbol}. {verdict.reason}",
        )
        refresh_lessons(desk)
    return entry


def record_outcome(desk, client_order_id: str, status: str, detail: dict) -> dict:
    return append(
        desk,
        {"kind": "outcome", "client_order_id": client_order_id, "status": status, **detail},
    )


def record_opinion(desk, entry_id: str, opinion: dict) -> dict:
    return append(desk, {"kind": "opinion", "about": entry_id, **opinion})


def distill(desk) -> str:
    log = entries(desk)
    flagged = [e for e in log if e["kind"] in {"block", "near_miss"}]
    opinions = {e["about"]: e for e in log if e["kind"] == "opinion"}
    outcomes = [e for e in log if e["kind"] == "outcome"]
    events = store.read_jsonl(store.private_dir(desk) / EVENTS, 8)
    reviewed = [e for e in log if e["kind"] in {"block", "near_miss", "approve"}]
    client = reviewed[-1]["client"] if reviewed else "this fund"
    blocks = [e for e in flagged if e["kind"] == "block"]
    near = [e for e in flagged if e["kind"] == "near_miss"]

    lines = [
        f"# Watchdog lessons for {client}",
        "",
        (
            f"Updated {utcnow()[:19]} UTC. The watchdog reviews every paper order before it reaches Alpaca. "
            f"Read this before proposing a strategy or submitting an order. From {len(reviewed)} reviewed orders: "
            f"{len(blocks)} blocked, {len(near)} near misses."
        ),
        "",
    ]
    tripped = Counter(rule for e in blocks for rule in e["rules"])
    if tripped:
        lines += ["## Limits that keep tripping", ""]
        lines += [
            f"- `{rule}`, blocked {count} time{'s' if count > 1 else ''}. {ADVICE.get(rule, '')}"
            for rule, count in tripped.most_common()
        ]
        lines.append("")
    close = Counter(rule for e in near for rule in e["rules"])
    if close:
        lines += ["## Close calls", ""]
        lines += [
            f"- `{rule}` came within 10% of its limit {count} time{'s' if count > 1 else ''}. {ADVICE.get(rule, '')}"
            for rule, count in close.most_common()
        ]
        lines.append("")
    if blocks:
        lines += ["## Recent blocks, newest first", ""]
        for e in reversed(blocks[-5:]):
            who = f" by {e['agent_id']}" if e.get("agent_id") else ""
            line = f"- {e['time'][11:16]} UTC, {describe(e)}{who}: {e['reason']}"
            if e["id"] in opinions:
                line += f" Reviewer note: {opinions[e['id']]['explanation']}"
            lines.append(line)
        lines.append("")
    if outcomes:
        lines += ["## What happened to approved orders", ""]
        lines += [
            f"- `{e['client_order_id']}`: {e['status']}"
            + (f", filled at ${float(e['filled_avg_price']):,.2f}" if e.get("filled_avg_price") else "")
            for e in outcomes[-5:]
        ]
        lines.append("")
    if events:
        lines += ["## Moderator events", ""]
        lines += [f"- {e['severity']}: {e['message']}" for e in reversed(events)]
        lines.append("")
    if len(lines) == 4:
        lines += ["Nothing flagged yet. Keep orders inside the mandate and this file stays short.", ""]
    return "\n".join(lines)


def refresh_lessons(desk) -> str:
    text = distill(desk)
    store.write_text(store.private_dir(desk) / LESSONS, text)
    store.write_text(store.workspace_dir(desk) / LESSONS, text)
    return text


def lessons(desk) -> str:
    path = store.private_dir(desk) / LESSONS
    return path.read_text() if path.exists() else refresh_lessons(desk)
