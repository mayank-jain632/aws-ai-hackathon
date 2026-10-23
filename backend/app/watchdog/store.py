"""Where the watchdog keeps its records for one fund's desk.

Authoritative copies live beside `desk.json`, outside the agents' shared files, so an
agent cannot rewrite its own record. Copies meant for agents and people to read
(moderator events, LESSONS.md) are mirrored into the fund's shared workspace under
`watchdog/`.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

LOCK = threading.RLock()


def private_dir(desk) -> Path:
    return desk.path.parent / "watchdog"


def workspace_dir(desk) -> Path:
    return Path(desk.manager.registry).parent / "workspace" / "watchdog"


def append_jsonl(path: Path, record: dict) -> None:
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(json.dumps(record, allow_nan=False) + "\n")


def read_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows[-limit:] if limit else rows


def write_text(path: Path, text: str) -> None:
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)


def load_state(desk) -> dict:
    path = private_dir(desk) / "state.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(desk, state: dict) -> None:
    write_text(private_dir(desk) / "state.json", json.dumps(state, indent=2))
