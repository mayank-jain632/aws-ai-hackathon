"""Hourly wakeups preserve identities, privacy, cancellation, and explicit opt-in."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app.fund_schedule import AUTHORIZED_FUND, WAKEUP, FundScheduler


class Agent:
    def __init__(self):
        self.state = {"status": "idle"}
        self.task = None
        self.calls = []

    async def start(self, prompt, source):
        self.calls.append((prompt, source))
        self.state["status"] = "running"
        self.task = asyncio.get_running_loop().create_future()


class Runtime:
    def __init__(self):
        self.agents = {"dexter": Agent()}
        self.stops = []

    def publish(self):
        pass

    async def stop(self, agent_id):
        self.stops.append(agent_id)
        for agent in self.agents.values():
            if agent.task is not None:
                agent.task.cancel()
            agent.state["status"] = "stopped"


class Store:
    def __init__(self):
        self.records = {
            key: {"status": "active"} for key in [AUTHORIZED_FUND, "another"]
        }
        self.runtimes = {key: Runtime() for key in self.records}
        self.saves = 0

    def runtime(self, key):
        return self.runtimes[key]

    def save(self):
        self.saves += 1


@pytest.fixture
def setup(monkeypatch):
    from backend.app.watchdog.halt import SWITCH

    monkeypatch.setattr(SWITCH, "state", lambda: {"halted": False})
    clock = SimpleNamespace(now=datetime(2026, 10, 23, 16, tzinfo=UTC))
    store = Store()
    scheduler = FundScheduler(store, clock=lambda: clock.now)
    return store, scheduler, clock


def test_only_explicit_existing_fund_opts_in_and_restart_preserves_disable(setup):
    store, scheduler, clock = setup
    assert scheduler.view(AUTHORIZED_FUND)["enabled"]
    assert not scheduler.view("another")["enabled"]
    asyncio.run(scheduler.configure(AUTHORIZED_FUND, False, "owner@example.com"))
    restored = FundScheduler(store, clock=lambda: clock.now)
    assert not restored.view(AUTHORIZED_FUND)["enabled"]


def test_same_saved_root_runs_once_and_disable_cancels_only_its_run(setup):
    store, scheduler, clock = setup

    async def check():
        root = store.runtime(AUTHORIZED_FUND).agents["dexter"]
        clock.now += timedelta(hours=1)
        await scheduler.tick()
        assert root.calls == [(WAKEUP, "Hourly schedule")]
        await scheduler.tick()
        assert len(root.calls) == 1
        assert scheduler.view(AUTHORIZED_FUND)["last_run_at"] == clock.now.isoformat()
        await scheduler.configure(AUTHORIZED_FUND, False, "owner")
        assert store.runtime(AUTHORIZED_FUND).stops == ["dexter"]
        assert root.task.cancelled()

    asyncio.run(check())


def test_busy_child_or_waiting_parent_is_skipped_without_queue(setup):
    store, scheduler, clock = setup
    runtime = store.runtime(AUTHORIZED_FUND)
    runtime.agents["researcher"] = Agent()
    runtime.agents["researcher"].state["status"] = "waiting"
    clock.now += timedelta(hours=1)
    asyncio.run(scheduler.tick())
    assert not runtime.agents["dexter"].calls
    assert "already working" in scheduler.view(AUTHORIZED_FUND)["last_result"]
    runtime.agents["researcher"].state["status"] = "idle"
    asyncio.run(scheduler.tick())
    assert not runtime.agents["dexter"].calls
    assert (
        scheduler.view(AUTHORIZED_FUND)["next_run_at"]
        == (clock.now + timedelta(hours=1)).isoformat()
    )


def test_overdue_restart_skips_missed_hours_and_nonactive_disables(setup):
    store, _, clock = setup
    clock.now += timedelta(days=5)
    scheduler = FundScheduler(store, clock=lambda: clock.now)
    assert "restart" in scheduler.view(AUTHORIZED_FUND)["last_result"]
    asyncio.run(scheduler.tick())
    assert not store.runtime(AUTHORIZED_FUND).agents["dexter"].calls
    store.records[AUTHORIZED_FUND]["status"] = "archived"
    asyncio.run(scheduler.tick())
    assert not scheduler.view(AUTHORIZED_FUND)["enabled"]
    with pytest.raises(ValueError, match="Resume"):
        asyncio.run(scheduler.configure(AUTHORIZED_FUND, True, "owner"))


def test_disable_does_not_cancel_manual_run(setup):
    store, scheduler, _ = setup

    async def check():
        await store.runtime(AUTHORIZED_FUND).agents["dexter"].start("manual", "You")
        await scheduler.configure(AUTHORIZED_FUND, False, "owner")
        assert not store.runtime(AUTHORIZED_FUND).stops

    asyncio.run(check())


def test_firm_emergency_stop_blocks_wakeup_without_changing_gates(setup, monkeypatch):
    from backend.app.watchdog.halt import SWITCH

    store, scheduler, clock = setup
    monkeypatch.setattr(SWITCH, "state", lambda: {"halted": True})
    clock.now += timedelta(hours=1)
    asyncio.run(scheduler.tick())
    assert not store.runtime(AUTHORIZED_FUND).agents["dexter"].calls
    assert "emergency stop" in scheduler.view(AUTHORIZED_FUND)["last_result"]
    assert SWITCH.state()["halted"]


def test_generated_mandate_is_current_and_has_no_scheduler_or_owner_data(tmp_path):
    from backend.app.agent import AgentManager
    from backend.app.funds import FundStore, Mandate

    store = FundStore(AgentManager(root=tmp_path), root=tmp_path)
    detail = store.create(
        Mandate(
            name="Demo fund",
            capital=95000,
            mode="paper",
            trading_allowed=True,
            approval_required=False,
        ),
        "private@example.com",
    )
    runtime = store.runtime(detail["id"])
    context = json.loads(runtime.context)
    assert context["mandate"]["capital"] == 95000
    assert context["mandate"]["min_cash"] == 5
    assert context["mandate"]["cutoff"] is None
    assert "schedule" not in context["mandate"] and "owner" not in context["mandate"]
    assert context["mandate"]["trading_allowed"] is True
    assert context["mandate"]["approval_required"] is False
    text = (runtime.root / "workspace" / "mandate.md").read_text()
    assert "not a backtest end date" in text
    assert "missing desk policy requires human" in text
    assert store.records[detail["id"]]["cutoff"] == "2024-06-01"


def test_schedule_api_membership_pause_and_root_stop(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import backend.app.funds as module
    from backend.app import main
    from backend.app.agent import AgentManager

    monkeypatch.setenv("APP_ACCESS_PASSWORD", "test-signing-secret")
    monkeypatch.setenv(
        "APP_DEMO_ACCOUNTS",
        json.dumps(
            {
                "owner@example.com": "demo-test-pass",
                "peer@example.com": "peer-test-pass",
            }
        ),
    )
    monkeypatch.delenv("APP_ORIGIN_TOKEN", raising=False)
    monkeypatch.setenv("WATCHDOG_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        main, "AgentManager", lambda: AgentManager(root=tmp_path / ".local")
    )
    with TestClient(main.app, base_url="https://localhost") as client:
        client.post(
            "/login", data={"email": "owner@example.com", "password": "demo-test-pass"}
        )
        fund_id = client.post("/api/funds", json={"name": "Private schedule"}).json()[
            "id"
        ]
        path = f"/api/funds/{fund_id}/schedule"
        assert not client.get(f"/api/funds/{fund_id}").json()["schedule"]["enabled"]
        assert (
            client.put(
                path, json={"enabled": True}, headers={"x-agent-token": "worker"}
            ).status_code
            == 403
        )
        response = client.put(path, json={"enabled": True})
        assert (
            response.status_code == 200 and response.json()["interval_seconds"] == 3600
        )
        assert response.json()["authorized_by"] == "owner@example.com"
        client.post(
            "/login", data={"email": "peer@example.com", "password": "peer-test-pass"}
        )
        assert client.put(path, json={"enabled": False}).status_code == 403
        client.post(
            "/login", data={"email": "owner@example.com", "password": "demo-test-pass"}
        )
        assert (
            client.post(f"/api/funds/{fund_id}/agents/dexter/stop").status_code == 200
        )
        assert not client.get(f"/api/funds/{fund_id}").json()["schedule"]["enabled"]
        assert client.put(path, json={"enabled": True}).status_code == 200
        assert (
            client.patch(
                f"/api/funds/{fund_id}/status", json={"status": "paused"}
            ).status_code
            == 200
        )
        assert not client.get(f"/api/funds/{fund_id}").json()["schedule"]["enabled"]
        assert client.put(path, json={"enabled": True}).status_code == 409
        client.patch(f"/api/funds/{fund_id}/status", json={"status": "active"})
        assert not client.get(f"/api/funds/{fund_id}").json()["schedule"]["enabled"]


def test_dispatch_failure_does_not_retry_until_next_hour(setup, monkeypatch):
    store, scheduler, clock = setup

    async def unavailable(*args, **kwargs):
        raise RuntimeError("Dexter source is missing")

    monkeypatch.setattr(
        store.runtime(AUTHORIZED_FUND).agents["dexter"], "start", unavailable
    )
    clock.now += timedelta(hours=1)
    asyncio.run(scheduler.tick())
    assert "Could not start" in scheduler.view(AUTHORIZED_FUND)["last_result"]
    assert scheduler.view(AUTHORIZED_FUND)["last_run_at"] is None
    assert (
        scheduler.view(AUTHORIZED_FUND)["next_run_at"]
        == (clock.now + timedelta(hours=1)).isoformat()
    )


def test_schedule_persists_and_shutdown_does_not_revoke_authorization(tmp_path):
    from backend.app.agent import AgentManager
    from backend.app.funds import FundStore

    store = FundStore(AgentManager(root=tmp_path), root=tmp_path)
    clock = lambda: datetime(2026, 10, 23, 16, tzinfo=UTC)
    scheduler = FundScheduler(store, clock=clock)

    async def check():
        await scheduler.configure("general", True, "owner@example.com")
        scheduler.start()
        await scheduler.close()

    asyncio.run(check())
    restored = FundScheduler(
        FundStore(AgentManager(root=tmp_path), root=tmp_path), clock=clock
    )
    assert restored.view("general")["enabled"]
    assert restored.view("general")["authorized_by"] == "owner@example.com"
    assert restored.view("general")["next_run_at"] == "2026-10-23T17:00:00+00:00"
