"""Fund isolation, migration, persistence, and mandate validation."""

import asyncio

import pytest
from pydantic import ValidationError

from backend.app.agent import AgentManager
from backend.app.funds import FundStore, Mandate


def test_legacy_board_survives_and_fund_files_do_not_cross(tmp_path):
    legacy = AgentManager(root=tmp_path)
    (legacy.root / "workspace" / "original.txt").write_text("existing team work")
    store = FundStore(legacy, root=tmp_path)
    assert store.runtime("general") is legacy
    one = store.create(
        Mandate(name="Income fund", risk="conservative"), "kush@example.com"
    )
    two = store.create(
        Mandate(name="Growth fund", capital=250000), "mayank@example.com"
    )
    first, second = store.runtime(one["id"]), store.runtime(two["id"])
    (first.root / "workspace" / "private.txt").write_text("first fund research")
    assert not (second.root / "workspace" / "private.txt").exists()
    assert not (first.root / "workspace" / "original.txt").exists()
    assert (
        legacy.root / "workspace" / "original.txt"
    ).read_text() == "existing team work"
    assert store.by_token(first.token) is first
    assert store.by_token(second.token) is second
    assert first.token != second.token
    restored = FundStore(legacy, root=tmp_path)
    assert restored.detail(two["id"])["metrics"]["cash"] == 250000
    assert (
        restored.runtime(one["id"]).root / "workspace" / "private.txt"
    ).read_text() == "first fund research"
    assert restored.detail(one["id"])["metrics"]["pnl"] == 0


def test_paused_fund_cannot_start_an_agent(tmp_path):
    manager = AgentManager(root=tmp_path)
    manager.paused = True
    with pytest.raises(ValueError, match="paused"):
        asyncio.run(manager.agents["dexter"].start("Place a trade"))
    assert manager.agents["dexter"].state["messages"] == []


def test_start_fund_dispatches_delegated_workflow_without_changing_consent(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient

    import backend.app.funds as module
    from backend.app import main

    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        main, "AgentManager", lambda: AgentManager(root=tmp_path / ".local")
    )
    with TestClient(main.app, base_url="http://localhost") as client:
        fund_id = client.post(
            "/api/funds", json={"name": "Delegation regression"}
        ).json()["id"]
        runtime = main.app.state.funds.runtime(fund_id)
        tasks = []

        async def capture_task(prompt, source):
            tasks.append(prompt)

        monkeypatch.setattr(runtime.agents["dexter"], "start", capture_task)
        before = client.get(f"/api/funds/{fund_id}").json()
        assert client.post(f"/api/funds/{fund_id}/plan").status_code == 202
        assert len(tasks) == 1
        assert "create_agent" in tasks[0]
        assert "Do not create subagents" not in tasks[0]
        assert "strategy_id" in tasks[0] and "backtester" in tasks[0]
        assert "does not authorize order submission" not in tasks[0]
        assert "paper execution agent" in tasks[0]
        assert "final independent review" in tasks[0]
        assert "Never clear the emergency stop" in tasks[0]
        after = client.get(f"/api/funds/{fund_id}").json()
        for field in (
            "trading_allowed",
            "approval_required",
            "min_cash",
            "mode",
            "cutoff",
        ):
            assert after[field] == before[field]


@pytest.mark.parametrize(
    "values",
    [
        {"name": "  "},
        {"name": "Invalid", "capital": -1},
        {"name": "Invalid", "universe": ["../other"]},
        {"name": "Invalid", "max_drawdown": float("inf")},
        {"name": "Invalid", "cutoff": "2024-02-31"},
    ],
)
def test_invalid_mandates_rejected(values):
    with pytest.raises(ValidationError):
        Mandate(**values)


def test_fund_api_scopes_files_tokens_and_layout(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import backend.app.funds as module
    from backend.app import main

    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        main, "AgentManager", lambda: AgentManager(root=tmp_path / ".local")
    )
    with TestClient(main.app, base_url="http://localhost") as client:
        first = client.post("/api/funds", json={"name": "First fund"}).json()["id"]
        second = client.post("/api/funds", json={"name": "Second fund"}).json()["id"]
        runtime = main.app.state.funds.runtime(first)
        (runtime.root / "workspace" / "secret.txt").write_text("first fund only")
        assert (
            client.get(
                f"/api/funds/{first}/agents/dexter/file", params={"path": "secret.txt"}
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/funds/{second}/agents/dexter/file", params={"path": "secret.txt"}
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/funds/{second}/agents/dexter/file",
                params={"path": "../../secret.txt"},
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/funds/{first}/board/layout",
                json={"agent_id": "dexter", "position": {"x": 42, "y": 80}},
            ).status_code
            == 200
        )
        assert client.get(f"/api/funds/{second}/agents").json()["positions"] == {}
        assert (
            client.get(f"/api/funds/{first}/agents").json()["positions"]["dexter"]["x"]
            == 42
        )
        assert (
            client.get(
                "/api/internal/agents",
                headers={"X-Agent-ID": "dexter", "X-Agent-Token": runtime.token},
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/internal/agents",
                headers={"X-Agent-ID": "dexter", "X-Agent-Token": "invalid"},
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/funds/{first}/status", json={"status": "paused"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/funds/{first}/agents/dexter/messages", json={"text": "Run now"}
            ).status_code
            == 409
        )
        assert (
            client.patch(
                f"/api/funds/{first}/status", json={"status": "active"}
            ).status_code
            == 200
        )
        assert client.get("/api/funds/does-not-exist").status_code == 404


def test_live_research_context_does_not_activate_saved_historical_cutoff(tmp_path):
    import json

    legacy = AgentManager(root=tmp_path)
    store = FundStore(legacy, root=tmp_path)
    live = store.create(
        Mandate(name="Live research", mode="paper", cutoff="2024-06-01"), "Team"
    )
    historical = store.create(
        Mandate(name="Historical research", mode="historical", cutoff="2024-06-01"),
        "Team",
    )
    assert json.loads(store.runtime(live["id"]).context)["mandate"]["cutoff"] is None
    assert store.records[live["id"]]["cutoff"] == "2024-06-01"
    assert (
        json.loads(store.runtime(historical["id"]).context)["mandate"]["cutoff"]
        == "2024-06-01"
    )
