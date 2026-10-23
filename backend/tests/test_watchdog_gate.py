"""The watchdog inside the real paper-order path and its routes, with a broker stub."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app import agent as runtime
from backend.app import paper
from backend.app.desk import (
    OrderInput,
    Policy,
    ReviewInput,
    StrategyInput,
    desk_for,
    digest,
)
from backend.app.main import app
from backend.app.watchdog import SWITCH, feedback, gate, store


@pytest.fixture(autouse=True)
def isolated_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_DIR", str(tmp_path / "watchdog-global"))


def approved_desk(manager):
    desk = desk_for(manager)
    desk.set_policy(
        Policy(
            universe=["AAPL", "MSFT"],
            max_position=0.7,
            max_drawdown=0.5,
            min_sharpe=-100,
            min_excess_return=-1,
            max_order_notional=1000,
            max_daily_orders=10,
            trading_allowed=True,
        )
    )
    strategy = StrategyInput(
        name="Test",
        weights={"AAPL": 0.5, "MSFT": 0.5},
        cutoff="2023-01-01",
        end="2023-06-30",
        rationale="Cited evidence",
        memo_paths=["memo.md"],
        changes_my_mind="Evidence changes",
    )
    sid = desk.register(strategy, "author")["id"]
    desk.review(
        ReviewInput(
            strategy_id=sid,
            verdict="APPROVE",
            critique="An independent review checked concentration and dated inputs.",
        ),
        "reviewer",
    )
    desk.evaluate(sid)
    desk.state["approvals"][sid] = digest(desk.state["policy"])
    desk.state["stop"] = False
    desk.save()
    return desk, sid


@pytest.fixture
def approved(tmp_path):
    manager = SimpleNamespace(registry=tmp_path / "agents.json", paused=False)
    return approved_desk(manager)


def account(positions=(), equity="10000", cash="10000"):
    return {
        "account": {
            "status": "ACTIVE",
            "trading_blocked": False,
            "account_blocked": False,
            "equity": equity,
            "cash": cash,
        },
        "positions": list(positions),
        "open_orders": [],
    }


def order(sid, **overrides):
    base = {"strategy_id": sid, "symbol": "AAPL", "side": "buy", "notional": 100, "client_order_id": "stable-order-001"}
    return OrderInput(**{**base, **overrides})


def stub_broker(monkeypatch):
    calls = []

    def fake(method, path, body):
        calls.append(body)
        return {"id": f"broker-{len(calls)}", "status": "accepted", "filled_qty": "0"}

    monkeypatch.setattr(paper, "broker", fake)
    return calls


def test_clean_order_passes_watchdog_and_reaches_broker(approved, monkeypatch):
    desk, sid = approved
    monkeypatch.setattr(paper, "account_snapshot", account)
    calls = stub_broker(monkeypatch)
    assert paper.submit(desk, order(sid))["status"] == "accepted"
    assert len(calls) == 1
    assert feedback.entries(desk)[-1]["kind"] == "approve"


def test_same_day_wash_trade_is_blocked_before_broker(approved, monkeypatch):
    desk, sid = approved
    calls = stub_broker(monkeypatch)
    monkeypatch.setattr(paper, "account_snapshot", account)
    paper.submit(desk, order(sid))
    held = [{"symbol": "AAPL", "qty": "1", "market_value": "100"}]
    monkeypatch.setattr(paper, "account_snapshot", lambda: account(held, cash="9900"))
    with pytest.raises(ValueError, match="Watchdog blocked this order: .*wash-trade"):
        paper.submit(desk, order(sid, side="sell", client_order_id="stable-order-002"))
    assert len(calls) == 1
    assert feedback.entries(desk)[-1]["rules"] == ["wash_trade"]


def test_firm_wide_halt_stops_orders_in_every_fund(approved, tmp_path, monkeypatch):
    desk, sid = approved
    other, other_sid = approved_desk(SimpleNamespace(registry=tmp_path / "fund2" / "agents.json", paused=False))
    monkeypatch.setattr(paper, "account_snapshot", account)
    calls = stub_broker(monkeypatch)
    SWITCH.trip("Demo: halting all agents", "Aaron")
    for d, s in [(desk, sid), (other, other_sid)]:
        with pytest.raises(ValueError, match="Firm-wide emergency stop"):
            paper.submit(d, order(s))
    assert calls == []
    SWITCH.reset("Checked", "Aaron")
    assert paper.submit(desk, order(sid))["status"] == "accepted"


def test_block_writes_lessons_into_shared_workspace(approved, monkeypatch):
    desk, sid = approved
    monkeypatch.setattr(paper, "account_snapshot", lambda: account(equity="2000", cash="2000"))
    stub_broker(monkeypatch)
    with pytest.raises(ValueError, match="order_size|of equity"):
        paper.submit(desk, order(sid, notional=900))
    lessons = (store.workspace_dir(desk) / "LESSONS.md").read_text()
    assert "Watchdog lessons for Team 4 board" in lessons
    assert "`order_size`, blocked 1 time" in lessons
    assert "Split large trades" in lessons


def test_fund_mandate_is_merged_strictly(approved):
    desk, _ = approved
    desk.manager.context = json.dumps(
        {
            "mandate": {
                "name": "Calder Family Trust",
                "risk": "conservative",
                "capital": 50_000,
                "universe": ["AAPL", "NVDA"],
                "max_position": 10,
                "max_drawdown": 8,
                "trading_allowed": True,
                "mode": "paper",
            }
        }
    )
    mandate = gate.mandate_for(desk, desk.policy())
    assert mandate.client == "Calder Family Trust"
    assert mandate.risk == "conservative"
    assert mandate.universe == ["AAPL"]
    assert mandate.max_position == pytest.approx(0.10)
    assert mandate.max_drawdown == pytest.approx(0.08)
    assert mandate.trading_allowed is True
    desk.manager.context = json.dumps({"mandate": {"name": "X", "trading_allowed": True, "mode": "historical"}})
    assert gate.mandate_for(desk, desk.policy()).trading_allowed is False


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    monkeypatch.setattr(runtime, "LOCAL", tmp_path / ".local/agent")
    manager = runtime.AgentManager()
    manager.token = "TOKEN"
    for role in ["executor", "research"]:
        manager.agents[role] = runtime.LocalAgent(manager, role, role, "dexter", role)
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.delattr(app.state, "funds", raising=False)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    with_client = TestClient(app, base_url="http://localhost")
    yield manager, with_client
    with_client.close()


def test_halt_route_is_human_only(client):
    _, http = client
    worker = {"X-Agent-Token": "TOKEN", "X-Agent-ID": "executor"}
    assert http.put("/api/watchdog/halt", json={"halted": True, "reason": "x"}, headers=worker).status_code == 403
    tripped = http.put("/api/watchdog/halt", json={"halted": True, "reason": "Demo stop"})
    assert tripped.json()["halted"] is True
    assert "Firm-wide emergency stop" in http.get("/api/watchdog").json()["halted_reason"]
    assert http.put("/api/watchdog/halt", json={"halted": False, "reason": "Clear"}).json()["halted"] is False


def test_dry_run_review_blocks_oversized_conservative_order(client):
    manager, http = client
    _, sid = approved_desk(manager)
    manager.context = json.dumps(
        {
            "mandate": {
                "name": "Calder Family Trust",
                "risk": "conservative",
                "capital": 100_000,
                "universe": ["AAPL", "MSFT"],
                "max_position": 10,
                "max_drawdown": 8,
                "trading_allowed": True,
                "mode": "paper",
            }
        }
    )
    body = {
        "symbol": "AAPL",
        "side": "buy",
        "notional": 40_000,
        "strategy_id": sid,
        "portfolio": {"equity": 100_000, "cash": 100_000},
    }
    verdict = http.post("/api/watchdog/review", json=body).json()
    assert verdict["decision"] == "block"
    assert "position_size" in verdict["blocked_by"]
    assert "conservative mandate caps any one position at 10.0%" in verdict["reason"]


def test_lessons_tool_respects_roles(client):
    _, http = client
    executor = {"X-Agent-Token": "TOKEN", "X-Agent-ID": "executor"}
    research = {"X-Agent-Token": "TOKEN", "X-Agent-ID": "research"}
    assert "Watchdog lessons" in http.get("/api/internal/watchdog/lessons", headers=executor).json()["lessons"]
    assert http.get("/api/internal/watchdog/lessons", headers=research).status_code == 403


def test_monitor_loop_starts_with_the_app(tmp_path, monkeypatch):
    import threading

    from backend.app import funds
    from backend.app.watchdog import monitor

    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    monkeypatch.setattr(runtime, "LOCAL", tmp_path / ".local/agent")
    monkeypatch.setattr(funds, "ROOT", tmp_path)
    monkeypatch.setenv("WATCHDOG_INTERVAL_SECONDS", "0.05")
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    swept = threading.Event()
    monkeypatch.setattr(monitor, "sweep", lambda _app: swept.set() or {})
    with TestClient(app, base_url="http://localhost"):
        assert swept.wait(5)
