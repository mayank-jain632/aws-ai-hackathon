"""Watchdog: pre-trade gate, firm-wide emergency stop, monitor, and feedback loop.

Execution calls `is_halted(desk)` and `review_order(order, mandate, portfolio)` before
every order. See `docs/watchdog.md` for the interface other lanes use.
"""

from backend.app.watchdog.halt import SWITCH, halt_reason, is_halted
from backend.app.watchdog.models import (
    ModeratorEvent,
    PastOrder,
    RuleResult,
    Verdict,
    WatchMandate,
    WatchOrder,
    WatchPortfolio,
)
from backend.app.watchdog.rules import GUARDRAILS, review_order

__all__ = [
    "GUARDRAILS",
    "SWITCH",
    "ModeratorEvent",
    "PastOrder",
    "RuleResult",
    "Verdict",
    "WatchMandate",
    "WatchOrder",
    "WatchPortfolio",
    "halt_reason",
    "is_halted",
    "review_order",
]
