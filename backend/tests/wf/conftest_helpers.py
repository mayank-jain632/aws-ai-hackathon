"""Shared fakes for the stage/pipeline tests."""

from __future__ import annotations

from backend.app.schema import Source

UNIVERSE = ["AAPL", "MSFT", "NVDA"]


def src(i: str, date: str = "2025-10-01") -> Source:
    return Source(
        id=i, kind="gdelt", title=f"title {i}", date=date, excerpt=f"excerpt {i}"
    )


class FakePit:
    def __init__(self, empty: set[str] | None = None, late: bool = False) -> None:
        self.empty = empty or set()
        self.late = late

    def evidence(self, analyst, as_of, universe):
        if analyst in self.empty:
            return "", []
        date = "2099-01-01" if self.late else as_of
        return f"digest {analyst}", [src(f"{analyst}-1", date)]

    def execution_context(self, as_of, tickers):
        return {
            t: {
                "last_close": 100.0,
                "atr14": 2.0,
                "avg_volume20": 1e6,
                "avg_gap_pct": 0.005,
                "ret_1w": 0.01,
                "last_date": as_of,
            }
            for t in tickers
        }

    def last_close(self, as_of, ticker):
        return 100.0


def responder(schema, system, user):
    if schema == "_MemoDraft":
        sid = next(
            ln[1 : ln.index("]")] for ln in user.splitlines() if ln.startswith("[")
        )
        return {
            "headline": "h",
            "body": "b",
            "views": [
                {
                    "ticker": "AAPL",
                    "stance": "long",
                    "confidence": 0.8,
                    "note": "n",
                    "sources": [sid, "bogus"],
                },
                {
                    "ticker": "ZZZZ",
                    "stance": "long",
                    "confidence": 0.8,
                    "note": "n",
                    "sources": [],
                },
            ],
        }
    if schema == "TradePlan":
        return {
            "decision_date": "x",
            "strategy_name": "s",
            "summary": "sum",
            "plans": [
                {
                    "ticker": "AAPL",
                    "target_weight": 0.5,
                    "stop_pct": 0.05,
                    "target_pct": 0.1,
                    "rationale": "r",
                    "changes_my_mind": "c",
                    "memo_sources": [],
                }
            ],
        }
    if schema == "ExecutionPlan":
        return {
            "decision_date": "x",
            "orders": [{"ticker": "AAPL", "entry": "limit", "limit_offset_atr": 0.5}],
        }
    raise AssertionError(schema)
