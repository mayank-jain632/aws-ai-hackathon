"""Background monitor, claim checks and the second opinion, all offline."""

import os
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app.agents import base
from backend.app.desk import Policy, StrategyInput, desk_for
from backend.app.schema import Source
from backend.app.watchdog import SWITCH, claims, feedback, monitor, opinion, store
from backend.app.watchdog.models import Verdict, WatchOrder

NOW = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_DIR", str(tmp_path / "watchdog-global"))
    monkeypatch.setattr(base, "mock_mode", lambda: True)


@pytest.fixture
def desk(tmp_path):
    manager = SimpleNamespace(registry=tmp_path / "fund" / "agents.json", paused=False)
    desk = desk_for(manager)
    desk.set_policy(
        Policy(
            universe=["AAPL", "MSFT", "NVDA", "JPM"],
            max_position=0.3,
            max_drawdown=0.2,
            min_sharpe=-100,
            min_excess_return=-1,
            max_order_notional=5000,
            max_daily_orders=50,
            trading_allowed=True,
        )
    )
    return desk


def add_orders(desk, count, minutes_ago=1, status="accepted"):
    for i in range(count):
        oid = f"order-{minutes_ago}-{i:03d}"
        desk.state["orders"][oid] = {
            "time": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
            "symbol": "AAPL",
            "side": "buy",
            "notional": 100,
            "client_order_id": oid,
            "status": status,
        }


def add_blocks(desk, agent, count):
    for _ in range(count):
        desk.state["events"].append(
            {"time": NOW.isoformat(), "check": "paper_order_blocked", "result": {"agent": agent, "reason": "x"}}
        )


def kinds(events):
    return [(e.kind, e.severity) for e in events]


def test_runaway_burst_trips_firm_wide_stop_once(desk):
    add_orders(desk, 11)
    events = monitor.audit(desk, now=NOW)
    assert ("runaway", "critical") in kinds(events)
    assert SWITCH.state()["halted"] is True
    assert SWITCH.state()["by"] == "watchdog"
    assert monitor.audit(desk, now=NOW) == []


def test_normal_flow_raises_nothing(desk):
    add_orders(desk, 3)
    assert monitor.audit(desk, now=NOW) == []
    assert SWITCH.state()["halted"] is False


def test_retry_loop_warns_then_trips(desk):
    add_blocks(desk, "executor-7", 3)
    assert ("retry_loop", "warn") in kinds(monitor.audit(desk, now=NOW))
    assert SWITCH.state()["halted"] is False
    add_blocks(desk, "executor-7", 3)
    assert ("retry_loop", "critical") in kinds(monitor.audit(desk, now=NOW))
    assert SWITCH.state()["halted"] is True


def test_unknown_broker_outcome_is_flagged(desk):
    add_orders(desk, 1, status="unknown")
    events = monitor.audit(desk, now=NOW)
    assert ("uncertain_order", "warn") in kinds(events)


def test_events_are_mirrored_to_workspace_and_desk(desk):
    add_orders(desk, 1, status="unknown")
    monitor.audit(desk, now=NOW)
    mirrored = store.read_jsonl(store.workspace_dir(desk) / "events.jsonl")
    assert mirrored[0]["kind"] == "uncertain_order"
    assert desk.state["events"][-1]["check"] == "watchdog_event"


def test_position_drift_short_and_outside_universe(desk):
    snapshot = {
        "account": {"equity": "10000", "cash": "2000"},
        "positions": [
            {"symbol": "AAPL", "qty": "10", "market_value": "4000"},
            {"symbol": "MSFT", "qty": "-2", "market_value": "-800"},
            {"symbol": "XOM", "qty": "5", "market_value": "500"},
        ],
    }
    found = kinds(monitor.audit(desk, snapshot, now=NOW))
    assert found.count(("position", "warn")) == 2
    assert ("position", "critical") in found


def test_outcomes_are_logged_once_per_status(desk):
    add_orders(desk, 1)
    monitor.audit(desk, now=NOW)
    monitor.audit(desk, now=NOW)
    outcomes = [e for e in feedback.entries(desk) if e["kind"] == "outcome"]
    assert len(outcomes) == 1 and outcomes[0]["status"] == "accepted"


def register(desk, memo_paths, cutoff="2023-01-01", end="2023-06-30"):
    return desk.register(
        StrategyInput(
            name="Quality tilt",
            weights={"AAPL": 0.25, "MSFT": 0.25, "NVDA": 0.25, "JPM": 0.25},
            cutoff=cutoff,
            end=end,
            rationale="Margins expanding per the memo.",
            memo_paths=memo_paths,
            changes_my_mind="Margins fall",
        ),
        "strategy-1",
    )


def write_memo(desk, name, text, age_seconds=60):
    path = store.workspace_dir(desk).parent / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    old = time.time() - age_seconds
    os.utime(path, (old, old))
    return path


def test_memo_claims_missing_lookahead_and_clean(desk):
    write_memo(desk, "memos/clean.md", "10-Q filed 2022-11-02. Test window ends 2023-06-30.")
    write_memo(desk, "memos/leaky.md", "Earnings beat reported 2023-04-27.")
    register(desk, ["memos/clean.md", "memos/leaky.md", "memos/ghost.md"])
    events = monitor.audit(desk, now=NOW)
    problems = {e.details["memo"]: e.details["problem"] for e in events if e.kind == "claim"}
    assert problems == {"memos/leaky.md": "lookahead", "memos/ghost.md": "missing"}
    assert "2023-04-27" in next(e.message for e in events if e.details.get("problem") == "lookahead")


def test_memo_edited_after_freeze_is_flagged(desk):
    write_memo(desk, "memos/m.md", "Filed 2022-11-02.", age_seconds=600)
    register(desk, ["memos/m.md"])
    path = store.workspace_dir(desk).parent / "memos/m.md"
    os.utime(path, None)
    future = time.time() + 5
    os.utime(path, (future, future))
    problems = [e.details["problem"] for e in monitor.audit(desk, now=NOW) if e.kind == "claim"]
    assert problems == ["edited_after_freeze"]


def test_check_sources_reuses_lookahead_guard_and_catches_invented_ids():
    sources = [
        Source(id="sec-1", kind="sec", title="10-K", date="2022-12-30", excerpt="x"),
        Source(id="news-9", kind="gdelt", title="Later", date="2023-02-01", excerpt="x"),
    ]
    problems = claims.check_sources(sources, "2023-01-01", known_ids={"sec-1"})
    assert any("do not exist" in p for p in problems)
    assert any("look-ahead" in p for p in problems)
    assert claims.check_sources(sources[:1], "2023-01-01", known_ids={"sec-1"}) == []


def flag(desk, agent="executor-7", rules=("wash_trade",)):
    verdict = Verdict(
        decision="block",
        reason="AAPL was already bought today; a same-day sell is a wash-trade pattern.",
        blocked_by=list(rules),
        near_misses=[],
        rules=[],
        order=WatchOrder(symbol="AAPL", side="sell", notional=100, agent_id=agent, strategy_id="s1"),
        client="Calder Family Trust",
        risk="conservative",
    )
    return feedback.record_verdict(desk, verdict)


def test_mock_second_opinion_flags_patterns_and_feeds_lessons(desk):
    flag(desk)
    done = opinion.review_flagged(desk)
    assert done[0]["foul_play"] is True and done[0]["concern"] == "high"
    assert "mock mode" in done[0]["source"]
    lessons = feedback.lessons(desk)
    assert "Reviewer note: The watchdog stopped a sell of $100 AAPL for Calder Family Trust" in lessons
    assert opinion.review_flagged(desk) == []


def test_bedrock_second_opinion_uses_structured_call(desk, monkeypatch):
    seen = {}

    def fake_run_structured(system, user, model_cls):
        seen["system"], seen["user"] = system, user
        return model_cls(
            foul_play=False,
            concern="medium",
            explanation="Looks like a sizing slip, not manipulation.",
            suggested_fix="Check holdings first.",
        )

    monkeypatch.setattr(base, "mock_mode", lambda: False)
    monkeypatch.setattr(base, "run_structured", fake_run_structured)
    flag(desk, rules=("order_size",))
    result = opinion.review_flagged(desk)[0]
    assert result["source"] == f"bedrock:{base.model_id()}"
    assert result["explanation"] == "Looks like a sizing slip, not manipulation."
    assert "untrusted text" in seen["system"]
    assert "Calder Family Trust" in seen["user"]


def test_bedrock_failure_falls_back_and_says_so(desk, monkeypatch):
    def broken(*_):
        raise RuntimeError("expired token")

    monkeypatch.setattr(base, "mock_mode", lambda: False)
    monkeypatch.setattr(base, "run_structured", broken)
    flag(desk, rules=("order_size",))
    assert "Bedrock unavailable: RuntimeError" in opinion.review_flagged(desk)[0]["source"]


def test_sweep_covers_board_and_funds(desk, tmp_path):
    other = desk_for(SimpleNamespace(registry=tmp_path / "fund2" / "agents.json", paused=False))
    add_orders(other, 1, status="unknown")
    other.save()
    desk.save()
    app = SimpleNamespace(
        state=SimpleNamespace(manager=desk.manager, funds=SimpleNamespace(managers={"general": desk.manager, "f2": other.manager}))
    )
    counts = monitor.sweep(app)
    assert len(counts) == 2
    assert counts[str(other.path.parent)] == 1
