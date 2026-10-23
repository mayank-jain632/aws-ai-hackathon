"""Model selection reaches workers, persists, and cannot unpin evaluators."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import agent as runtime
from backend.app.main import app
from backend.app.models import BACKTEST_MODEL, CATALOG, DEFAULT_MODEL, select_model

SOL = "us.openai.gpt-6.1-sol"
OPUS = "us.anthropic.claude-opus-5-5"


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "environment", dict)
    manager = runtime.AgentManager(root=tmp_path / "state")
    manager.agents["backtester"] = runtime.LocalAgent(
        manager, "backtester", "Evaluator", "dexter", "backtester"
    )
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.delattr(app.state, "funds", raising=False)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    with TestClient(app, base_url="http://localhost") as client:
        # TestClient lifespan installs its own manager, restore the isolated board.
        app.state.manager = manager
        yield manager, client


def test_human_selection_persists_and_workers_cannot_change_it(board):
    manager, client = board
    root = manager.agents["dexter"]
    assert root.model == DEFAULT_MODEL
    assert client.get("/api/agent-models").json() == CATALOG
    response = client.put("/api/agents/dexter/model", json={"model": OPUS})
    assert response.status_code == 200, response.text
    assert response.json()["model"] == OPUS
    assert len(response.json()["modelChoices"]) == 2
    restored = runtime.AgentManager(root=manager.root)
    assert restored.agents["dexter"].model == OPUS
    denied = client.put(
        "/api/agents/dexter/model",
        json={"model": DEFAULT_MODEL},
        headers={"X-Agent-Token": manager.token},
    )
    assert denied.status_code == 403
    assert root.model == OPUS
    assert (
        client.put("/api/agents/dexter/model", json={"model": "made-up"}).status_code
        == 409
    )
    assert root.model == OPUS
    assert (
        client.put("/api/agents/missing/model", json={"model": OPUS}).status_code == 404
    )


def test_backtester_pin_and_child_inheritance(board, tmp_path, monkeypatch):
    manager, client = board
    assert manager.agents["backtester"].model == BACKTEST_MODEL
    assert (
        client.put("/api/agents/backtester/model", json={"model": SOL}).status_code
        == 409
    )
    assert len(manager.agents["backtester"].snapshot()["modelChoices"]) == 1
    assert select_model("backtester", inherited=SOL) == BACKTEST_MODEL
    with pytest.raises(ValueError, match="pinned"):
        select_model("backtester", requested=SOL)
    source = tmp_path / "source"
    source.mkdir()
    (source / ".revision").write_text("test")
    monkeypatch.setattr(runtime, "DEXTER_SOURCE", source)
    monkeypatch.setattr(runtime, "bun_binary", lambda: "bun")

    async def run(self, prompt, history):
        self.state["status"] = "idle"
        self.publish()

    monkeypatch.setattr(runtime.LocalAgent, "run", run)

    async def exercise():
        await manager.agents["dexter"].set_model(OPUS)
        first = await manager.create("dexter", "Inherited", "Task", "research")
        await first.task
        second = await manager.create(
            first.id, "Override", "Task", "strategy", model=DEFAULT_MODEL
        )
        await second.task
        assert first.model == OPUS and second.model == DEFAULT_MODEL
        restored = runtime.AgentManager(root=manager.root)
        assert restored.agents[first.id].model == OPUS
        assert restored.agents[second.id].model == DEFAULT_MODEL

    asyncio.run(exercise())


def test_live_run_model_cannot_change_and_exact_model_reaches_worker(
    board, monkeypatch
):
    manager, _ = board
    captured = []
    monkeypatch.setattr(runtime, "bun_binary", lambda: "bun")

    async def spawn(*args, **kwargs):
        captured.append(kwargs["env"]["LOCAL_AGENT_MODEL"])
        raise RuntimeError("Intentional stop after observing worker environment")

    monkeypatch.setattr(runtime.asyncio, "create_subprocess_exec", spawn)

    async def exercise():
        root = manager.agents["dexter"]
        await root.set_model(SOL)
        root.task = asyncio.create_task(asyncio.Event().wait())
        with pytest.raises(ValueError, match="Stop"):
            await root.set_model(DEFAULT_MODEL)
        root.task.cancel()
        await asyncio.gather(root.task, return_exceptions=True)
        await root.run("hello", [])
        await manager.agents["backtester"].run("frozen numeric input", [])

    asyncio.run(exercise())
    assert captured == [SOL, BACKTEST_MODEL]


def test_legacy_state_migration_preserves_conversation(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "environment", dict)
    path = tmp_path / "agent/state.json"
    path.parent.mkdir()
    messages = [{"id": "a", "role": "assistant", "text": "existing answer"}]
    path.write_text(
        json.dumps(
            {"messages": messages, "activity": [], "model": "us.openai.gpt-5.6-luna"}
        )
    )
    manager = runtime.AgentManager(root=tmp_path)
    assert manager.agents["dexter"].model == DEFAULT_MODEL
    assert manager.agents["dexter"].state["messages"] == messages
    monkeypatch.setattr(runtime, "environment", lambda: {"MAIN_AGENT_MODEL": OPUS})
    assert runtime.AgentManager(root=tmp_path / "new").agents["dexter"].model == OPUS


def test_model_changes_are_fund_scoped(tmp_path, monkeypatch):
    from backend.app.funds import FundStore, Mandate

    monkeypatch.setattr(runtime, "environment", dict)
    manager = runtime.AgentManager(root=tmp_path / "state")
    store = FundStore(manager, root=manager.root)
    first = store.create(Mandate(name="Model fund one"), "team")
    second = store.create(Mandate(name="Model fund two"), "team")
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.setattr(app.state, "funds", store, raising=False)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    client = TestClient(app, base_url="http://localhost")
    try:
        response = client.put(
            f"/api/funds/{first['id']}/agents/dexter/model", json={"model": OPUS}
        )
        assert response.status_code == 200, response.text
        assert store.runtime(first["id"]).agents["dexter"].model == OPUS
        assert store.runtime(second["id"]).agents["dexter"].model == DEFAULT_MODEL
        assert (
            client.put(
                "/api/funds/missing/agents/dexter/model", json={"model": OPUS}
            ).status_code
            == 404
        )
    finally:
        client.close()
