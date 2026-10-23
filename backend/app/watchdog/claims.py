"""Claim checks: every source an agent cites is real and dated on or before the decision.

Two entry points. `check_sources` validates Desk `Source` records (the analysts' citation
shape) and reuses `assert_no_lookahead`. `check_strategy_memos` audits a registered canvas
strategy: each cited memo must exist in the fund's shared workspace, must not cite dates
after the strategy's cutoff, and must not have been edited after the strategy was frozen.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from backend.app.agents.base import assert_no_lookahead
from backend.app.schema import Source
from backend.app.watchdog.models import ModeratorEvent

ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def check_sources(sources: list[Source], decision_date: str, known_ids: set[str] | None = None) -> list[str]:
    """Problems with a list of cited sources; empty means every claim checks out."""
    problems = []
    if known_ids is not None:
        invented = sorted(s.id for s in sources if s.id not in known_ids)
        if invented:
            problems.append(f"cites sources that do not exist in the evidence set: {invented}")
    try:
        assert_no_lookahead(sources, decision_date)
    except AssertionError as error:
        problems.append(str(error))
    return problems


def memo_sources(path: str, text: str) -> list[Source]:
    return [
        Source(id=f"{path}#{n}", kind="price", title=path, date=found, excerpt=found)
        for n, found in enumerate(ISO_DATE.findall(text))
    ]


def check_strategy_memos(workspace: Path, strategy: dict) -> list[ModeratorEvent]:
    events = []
    root = workspace.resolve()
    cutoff, end = strategy["cutoff"], strategy["end"]
    frozen = datetime.fromisoformat(strategy["created_at"])
    sid = strategy["id"]
    for path in strategy["memo_paths"]:
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            events.append(
                ModeratorEvent(
                    kind="claim",
                    severity="warn",
                    subject=sid,
                    message=f"Strategy {strategy['name']} cites memo {path}, which does not exist in the fund's shared files.",
                    details={"strategy_id": sid, "memo": path, "problem": "missing"},
                )
            )
            continue
        text = target.read_text(errors="replace")
        # The test window's end date is a parameter, not evidence, so it is allowed.
        cited = [s for s in memo_sources(path, text) if s.date != end]
        problems = check_sources(cited, cutoff)
        if problems:
            late = sorted({s.date for s in cited if s.date > cutoff})
            events.append(
                ModeratorEvent(
                    kind="claim",
                    severity="critical",
                    subject=sid,
                    message=f"Memo {path} behind strategy {strategy['name']} cites dates after its {cutoff} decision cutoff ({', '.join(late[:5])}); possible look-ahead.",
                    details={"strategy_id": sid, "memo": path, "problem": "lookahead", "late_dates": late},
                )
            )
        edited = datetime.fromtimestamp(target.stat().st_mtime, UTC)
        if edited > frozen:
            events.append(
                ModeratorEvent(
                    kind="claim",
                    severity="warn",
                    subject=sid,
                    message=f"Memo {path} was edited after strategy {strategy['name']} was frozen, so it may not be the evidence that was reviewed.",
                    details={"strategy_id": sid, "memo": path, "problem": "edited_after_freeze"},
                )
            )
    return events
