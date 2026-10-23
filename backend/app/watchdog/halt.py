"""Firm-wide emergency stop.

One persisted flag across every fund. It sits on top of each fund's existing desk stop
(`desk.state["stop"]`), it does not replace it. The watchdog or a person can trip it;
only a person can reset it. Tripping it does not cancel orders a broker already accepted.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from backend.app.watchdog.models import utcnow

REPO_ROOT = Path(__file__).resolve().parents[3]


def state_dir() -> Path:
    return Path(os.getenv("WATCHDOG_DIR") or REPO_ROOT / ".local" / "watchdog")


class HaltSwitch:
    def __init__(self, path: Path | None = None):
        self._path = path
        self.lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path or state_dir() / "halt.json"

    def state(self) -> dict:
        if not self.path.exists():
            return {"halted": False, "reason": "", "by": "", "time": "", "history": []}
        return json.loads(self.path.read_text())

    def _write(self, state: dict) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.chmod(0o600)
        tmp.replace(self.path)
        return state

    def _set(self, halted: bool, reason: str, by: str) -> dict:
        with self.lock:
            state = self.state()
            entry = {"halted": halted, "reason": reason, "by": by, "time": utcnow()}
            state.update(entry)
            state["history"] = (state.get("history", []) + [entry])[-100:]
            self._write(state)
        from backend.app.watchdog import aws

        aws.publish_halt(state)
        return state

    def trip(self, reason: str, by: str) -> dict:
        return self._set(True, reason, by)

    def reset(self, reason: str, by: str) -> dict:
        return self._set(False, reason, by)


SWITCH = HaltSwitch()


def halt_reason(desk=None) -> str | None:
    """Why orders are halted right now, or None when trading may proceed."""
    state = SWITCH.state()
    if state["halted"]:
        return f"Firm-wide emergency stop is on ({state['reason']}, set by {state['by']})"
    if desk is not None:
        if desk.state.get("stop"):
            return "This fund's desk emergency stop is on"
        if getattr(desk.manager, "paused", False):
            return "This fund is paused"
    return None


def is_halted(desk=None) -> bool:
    """Execution calls this before every order. True blocks the order."""
    return halt_reason(desk) is not None
