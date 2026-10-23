"""A recorded paper order can be reconciled without any repeat submission."""

import copy
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import agent as runtime
from backend.app import paper
from backend.app.desk import Desk
from backend.app.main import app

CLIENT_ID = "flow-status-order-001"
BROKER_ID = "58eb65c8-209d-415e-9513-f9c399205222"


def record():
    return {
        "client_order_id": CLIENT_ID,
        "symbol": "AAPL",
        "side": "buy",
        "notional": 1.0,
        "status": "pending_new",
        "broker_id": BROKER_ID,
        "paper": True,
        "time": "2026-10-23T18:31:44+00:00",
        "request_hash": "unchanged",
    }


def filled():
    return {
        "id": BROKER_ID,
        "client_order_id": CLIENT_ID,
        "symbol": "AAPL",
        "side": "buy",
        "notional": "1",
        "status": "filled",
        "filled_qty": "0.002858099",
        "filled_avg_price": "346.384",
        "filled_at": "2026-10-23T18:31:44.102231414Z",
        "updated_at": "2026-10-23T18:31:44.103007445Z",
    }


@pytest.fixture
def desk(tmp_path):
    current = Desk(SimpleNamespace(registry=tmp_path / "agents.json"))
    current.state["orders"][CLIENT_ID] = record()
    current.save()
    return current


def test_status_get_updates_fill_and_persists_while_stopped(desk, monkeypatch):
    calls = []

    def broker(method, path):
        calls.append((method, path))
        return filled()

    monkeypatch.setattr(paper, "broker", broker)
    assert desk.state["stop"] is True
    updated = paper.order_status(desk, CLIENT_ID)
    assert calls == [("GET", f"/v2/orders/{BROKER_ID}")]
    assert updated["status"] == "filled"
    assert updated["filled_qty"] == "0.002858099"
    assert updated["filled_at"] == filled()["filled_at"]
    assert updated["request_hash"] == "unchanged"
    assert len(desk.state["orders"]) == 1 and desk.state["stop"] is True
    restored = Desk(desk.manager)
    assert restored.state["orders"][CLIENT_ID] == updated
    assert restored.state["events"][-1]["check"] == "paper_order_status"


def test_uncertain_post_is_resolved_by_client_id_without_resubmission(
    desk, monkeypatch
):
    current = desk.state["orders"][CLIENT_ID]
    current.pop("broker_id")
    current.update(status="unknown", reason="Submission response timed out")
    calls = []

    def broker(method, path):
        calls.append((method, path))
        return filled()

    monkeypatch.setattr(paper, "broker", broker)
    result = paper.order_status(desk, CLIENT_ID)
    assert calls == [
        ("GET", "/v2/orders:by_client_order_id?client_order_id=" + CLIENT_ID)
    ]
    assert result["status"] == "filled"
    assert result["previous_uncertainty"] == "Submission response timed out"
    assert len(desk.state["orders"]) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"client_order_id": "another-order-001"},
        {"id": "another-broker-id"},
        {"symbol": "MSFT"},
        {"side": "sell"},
        {"notional": "100"},
        {"filled_qty": "0"},
        {"filled_avg_price": "nan"},
        {"status": ""},
    ],
)
def test_mismatched_or_invalid_broker_response_does_not_overwrite_audit(
    desk, monkeypatch, change
):
    original = copy.deepcopy(desk.state)
    monkeypatch.setattr(paper, "broker", lambda *args: filled() | change)
    with pytest.raises(ValueError, match="does not match"):
        paper.order_status(desk, CLIENT_ID)
    assert desk.state == original


def test_lookup_failure_leaves_unknown_and_never_posts(desk, monkeypatch):
    desk.state["orders"][CLIENT_ID]["status"] = "unknown"
    original = copy.deepcopy(desk.state)

    def broker(method, path):
        assert method == "GET"
        raise httpx.ReadTimeout("Status unavailable")

    monkeypatch.setattr(paper, "broker", broker)
    with pytest.raises(httpx.ReadTimeout):
        paper.order_status(desk, CLIENT_ID)
    assert desk.state == original


def test_role_token_and_fund_boundaries(tmp_path, monkeypatch):
    from backend.app.funds import FundStore, Mandate

    manager = runtime.AgentManager(root=tmp_path / "state")
    store = FundStore(manager, root=manager.root)
    one = store.create(Mandate(name="One"), "team")
    two = store.create(Mandate(name="Two"), "team")
    first, second = store.runtime(one["id"]), store.runtime(two["id"])
    for role in ["executor", "moderator", "research", "backtester"]:
        first.agents[role] = runtime.LocalAgent(first, role, role, "dexter", role)
    first.desk.state["orders"][CLIENT_ID] = record()
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.setattr(app.state, "funds", store, raising=False)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    calls = []

    def broker(method, path):
        assert method == "GET"
        calls.append(path)
        return filled()

    monkeypatch.setattr(paper, "broker", broker)
    client = TestClient(app, base_url="http://localhost")
    path = "/api/internal/desk/orders/" + CLIENT_ID
    try:
        for role in ["dexter", "executor", "moderator"]:
            r = client.get(
                path, headers={"X-Agent-Token": first.token, "X-Agent-ID": role}
            )
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "filled"
        for role in ["research", "backtester"]:
            assert (
                client.get(
                    path, headers={"X-Agent-Token": first.token, "X-Agent-ID": role}
                ).status_code
                == 403
            )
        assert (
            client.get(
                path, headers={"X-Agent-Token": "wrong", "X-Agent-ID": "dexter"}
            ).status_code
            == 403
        )
        r = client.get(
            path, headers={"X-Agent-Token": second.token, "X-Agent-ID": "dexter"}
        )
        assert r.status_code == 422 and "this fund" in r.json()["detail"]
        assert len(calls) == 3
        assert first.desk.state["stop"] is True
    finally:
        client.close()
