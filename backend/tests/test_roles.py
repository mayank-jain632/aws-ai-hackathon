"""Exercise role boundaries through the actual API without Bedrock or brokerage I/O."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import agent as runtime
from backend.app.desk import Policy, StrategyInput, desk_for
from backend.app.main import app
from backend.app.roles import PROFILES


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    monkeypatch.setattr(runtime, "LOCAL", tmp_path / ".local/agent")
    manager = runtime.AgentManager()
    for role in PROFILES:
        if role != "orchestrator":
            manager.agents[role] = runtime.LocalAgent(
                manager, role, role, "dexter", role
            )
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.delattr(app.state, "funds", raising=False)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    client = TestClient(app, base_url="http://localhost")
    yield manager, client
    client.close()


def headers(role="dexter"):
    return {"X-Agent-Token": "TOKEN", "X-Agent-ID": role}


def test_role_tools_and_route_denial(board):
    manager, client = board
    manager.token = "TOKEN"
    assert PROFILES["backtester"]["tools"] == ["run_backtest"]
    for role in ["backtester", "executor", "moderator"]:
        assert (
            client.get("/api/internal/agents", headers=headers(role)).status_code == 403
        )
    assert (
        client.post(
            "/api/internal/desk/order",
            headers=headers("research"),
            json={
                "strategy_id": "x",
                "symbol": "AAPL",
                "side": "buy",
                "notional": 10,
                "client_order_id": "order-test",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/internal/desk/strategy",
            headers=headers("executor"),
            json=strategy_body(),
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/internal/desk/inspect", headers=headers("backtester")
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/internal/desk/stop",
            headers=headers("executor"),
            json={"reason": "test"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/internal/desk/stop",
            headers=headers("moderator"),
            json={"reason": "test"},
        ).json()["stopped"]
        is True
    )
    assert (
        client.put(
            "/api/desk/stop",
            headers=headers("moderator"),
            json={"stopped": False, "reason": "bypass"},
        ).status_code
        == 403
    )


def test_delegation_cannot_escalate_roles(board):
    manager, client = board
    manager.token = "TOKEN"
    for caller in [
        "research",
        "adversarial",
        "strategy",
        "backtester",
        "executor",
        "moderator",
    ]:
        response = client.post(
            "/api/internal/agents/create",
            headers=headers(caller),
            json={"role": "executor", "name": "Escalate", "task": "Trade"},
        )
        assert response.status_code == 403
    assert len(manager.agents) == 7
    response = client.post(
        "/api/internal/agents/message",
        headers=headers("research"),
        json={"agent_id": "executor", "task": "Trade"},
    )
    assert response.status_code in {403, 409}


def policy_body():
    return {
        "universe": ["AAPL", "MSFT"],
        "max_position": 0.7,
        "max_drawdown": 0.5,
        "min_sharpe": -100,
        "min_excess_return": -1,
        "max_order_notional": 1000,
        "max_daily_orders": 10,
        "trading_allowed": True,
        "approval_required": True,
    }


def strategy_body():
    return {
        "name": "Dated allocation",
        "weights": {"AAPL": 0.5, "MSFT": 0.5},
        "cutoff": "2023-01-01",
        "end": "2023-06-30",
        "rationale": "Research rationale withheld from backtester",
        "memo_paths": ["research.md"],
        "changes_my_mind": "Review if cited inputs change",
    }


def test_backend_gate_and_bound_evaluator(board):
    manager, client = board
    manager.token = "TOKEN"
    assert client.put("/api/desk/policy", json=policy_body()).status_code == 200
    registered = client.post(
        "/api/internal/desk/strategy", headers=headers("strategy"), json=strategy_body()
    )
    assert registered.status_code == 200, registered.text
    sid = registered.json()["id"]
    assert (
        client.post(
            "/api/internal/desk/backtest",
            headers=headers("backtester"),
            json={"strategy_id": sid},
        ).status_code
        == 403
    )
    manager.agents["backtester"].state["strategy_id"] = sid
    tested = client.post(
        "/api/internal/desk/backtest",
        headers=headers("backtester"),
        json={"strategy_id": sid},
    )
    assert tested.status_code == 200, tested.text
    assert tested.json()["verdict"] == "PASS"
    assert tested.json()["metrics"]["portfolio"]["total_return"] != 0
    assert "rationale" not in tested.json()
    desk = desk_for(manager)
    desk.state["stop"] = False
    with pytest.raises(ValueError, match="adversarial"):
        desk.execution_checks(sid)
    review = client.post(
        "/api/internal/desk/review",
        headers=headers("adversarial"),
        json={
            "strategy_id": sid,
            "verdict": "APPROVE",
            "critique": "Concentration and available evidence checked independently.",
        },
    )
    assert review.status_code == 200, review.text
    with pytest.raises(ValueError, match="approval"):
        desk.execution_checks(sid)
    assert client.post(f"/api/desk/strategies/{sid}/approve").status_code == 200
    desk.execution_checks(sid)
    client.put("/api/desk/policy", json=policy_body())
    assert desk.state["stop"] is True
    assert not desk.state["approvals"]
    later = strategy_body() | {"end": "2026-01-01"}
    sid2 = desk.register(StrategyInput(**later), "strategy")["id"]
    with pytest.raises(ValueError, match="Snapshot ends"):
        desk.evaluate(sid2)


def test_blind_worker_payload_and_role_persistence(board, tmp_path, monkeypatch):
    manager, _ = board
    desk = desk_for(manager)
    desk.set_policy(Policy(**policy_body()))
    sid = desk.register(StrategyInput(**strategy_body()), "strategy")["id"]
    desk.state["reviews"][sid] = {"verdict": "APPROVE"}
    source = tmp_path / "source"
    source.mkdir()
    (source / ".revision").write_text("test")
    monkeypatch.setattr(runtime, "DEXTER_SOURCE", source)
    monkeypatch.setattr(runtime, "bun_binary", lambda: "bun")
    captured = []

    async def fake_run(self, prompt, history):
        captured.append((prompt, history, self.role))
        self.state["status"] = "idle"

    monkeypatch.setattr(runtime.LocalAgent, "run", fake_run)

    async def exercise():
        child = await manager.create(
            "dexter",
            "Leaked research in name",
            "SECRET FUTURE RESEARCH",
            "backtester",
            sid,
        )
        await child.task
        assert child.state["strategy_id"] == sid
        assert child.snapshot()["role"] == "backtester"
        return child.id

    child_id = asyncio.run(exercise())
    prompt, history, role = captured[0]
    assert role == "backtester" and history == []
    assert (
        "SECRET" not in prompt
        and "rationale" not in prompt
        and "memo_paths" not in prompt
    )
    assert sid in prompt
    restored = runtime.AgentManager()
    assert restored.agents[child_id].role == "backtester"
    assert restored.agents[child_id].state["strategy_id"] == sid
    assert any(
        row["role"] == "backtester" for row in json.loads(manager.registry.read_text())
    )


def test_invalid_weights_and_unconfigured_gate(board):
    manager, _ = board
    with pytest.raises(ValueError):
        StrategyInput(**(strategy_body() | {"weights": {"AAPL": float("nan")}}))
    with pytest.raises(ValueError, match="configure"):
        desk_for(manager).register(StrategyInput(**strategy_body()), "strategy")


def test_desk_artifacts_and_worker_tokens_are_fund_scoped(tmp_path, monkeypatch):
    import backend.app.funds as funds_module
    from backend.app.funds import FundStore, Mandate

    manager = runtime.AgentManager(root=tmp_path / ".local")
    monkeypatch.setattr(funds_module, "ROOT", tmp_path)
    store = FundStore(manager, root=manager.root)
    one = store.create(Mandate(name="First fund"), "team")
    two = store.create(Mandate(name="Second fund"), "team")
    first, second = store.runtime(one["id"]), store.runtime(two["id"])
    first.agents["strategy"] = runtime.LocalAgent(
        first, "strategy", "Strategy", "dexter", "strategy"
    )
    second.agents["strategy"] = runtime.LocalAgent(
        second, "strategy", "Strategy", "dexter", "strategy"
    )
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.setattr(app.state, "funds", store, raising=False)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    client = TestClient(app, base_url="http://localhost")
    try:
        assert (
            client.put(
                f"/api/funds/{one['id']}/desk/policy", json=policy_body()
            ).status_code
            == 200
        )
        h1 = {"X-Agent-Token": first.token, "X-Agent-ID": "strategy"}
        registered = client.post(
            "/api/internal/desk/strategy", headers=h1, json=strategy_body()
        )
        assert registered.status_code == 200, registered.text
        sid = registered.json()["id"]
        assert sid in client.get(f"/api/funds/{one['id']}/desk").json()["strategies"]
        assert (
            sid not in client.get(f"/api/funds/{two['id']}/desk").json()["strategies"]
        )
        h2 = {"X-Agent-Token": second.token, "X-Agent-ID": "strategy"}
        assert (
            sid
            not in client.get("/api/internal/desk/inspect", headers=h2).json()[
                "strategies"
            ]
        )
        assert (
            client.put(
                f"/api/funds/{one['id']}/desk/policy", headers=h2, json=policy_body()
            ).status_code
            == 403
        )
        assert first.desk.path.parent != second.desk.path.parent
    finally:
        client.close()
