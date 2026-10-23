"""Email grants must cover every fund API, onboarding and revocation."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.agent import AgentManager
from backend.app.sharing import ShareStore


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    import backend.app.funds as module
    from backend.app import main

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
        assert (
            client.post(
                "/login",
                data={"email": "owner@example.com", "password": "demo-test-pass"},
                follow_redirects=False,
            ).status_code
            == 303
        )
        yield client, main.app


def test_existing_team_preserved_but_new_funds_require_sharing(hosted):
    client, _ = hosted
    fund = client.post("/api/funds", json={"name": "Private fund"}).json()["id"]
    client.post(
        "/login", data={"email": "peer@example.com", "password": "peer-test-pass"}
    )
    assert [f["id"] for f in client.get("/api/funds").json()["funds"]] == ["general"]
    assert client.get(f"/api/funds/{fund}/agents").status_code == 403
    client.post(
        "/login", data={"email": "owner@example.com", "password": "demo-test-pass"}
    )
    result = client.post(
        f"/api/funds/{fund}/members", json={"email": " PEER@example.com "}
    )
    assert result.status_code == 200
    assert result.json()["invitation_path"] is None
    client.post(
        "/login", data={"email": "peer@example.com", "password": "peer-test-pass"}
    )
    assert fund in [f["id"] for f in client.get("/api/funds").json()["funds"]]
    assert client.get(f"/api/funds/{fund}/agents").status_code == 200


def test_invited_account_only_sees_shared_fund_and_revocation_covers_routes(hosted):
    client, app = hosted
    first = client.post("/api/funds", json={"name": "Shared fund"}).json()["id"]
    second = client.post("/api/funds", json={"name": "Unrelated fund"}).json()["id"]
    result = client.post(
        f"/api/funds/{first}/members", json={"email": "Teammate@example.net"}
    ).json()
    path = result["invitation_path"]
    assert client.get(path).status_code == 200
    assert client.post(path, data={"password": "short"}).status_code == 400
    response = client.post(
        path, data={"password": "new-teammate-pass"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert client.get("/api/me").json()["email"] == "teammate@example.net"
    assert [f["id"] for f in client.get("/api/funds").json()["funds"]] == [first]
    assert client.get(path).status_code == 410
    assert client.get(f"/api/funds/{first}/agents").status_code == 200
    assert (
        client.patch(
            f"/api/funds/{first}/board/layout",
            json={"agent_id": "dexter", "position": {"x": 55, "y": 30}},
        ).status_code
        == 200
    )
    for suffix in [
        "",
        "/agents",
        "/events",
        "/agents/dexter/file?path=mandate.md",
        "/desk",
        "/watchdog",
        "/members",
    ]:
        assert client.get(f"/api/funds/{second}{suffix}").status_code == 403
    for path in [
        "/api/agents",
        "/api/events",
        "/api/desk",
        "/api/watchdog",
        "/api/internal/agents",
    ]:
        assert client.get(path).status_code == 403
    assert (
        client.delete(f"/api/funds/{first}/members/owner@example.com").status_code
        == 403
    )
    client.post(
        "/login", data={"email": "owner@example.com", "password": "demo-test-pass"}
    )
    assert (
        client.get(f"/api/funds/{first}/agents").json()["positions"]["dexter"]["x"]
        == 55
    )
    assert (
        client.delete(f"/api/funds/{first}/members/teammate@example.net").status_code
        == 200
    )
    client.post(
        "/login",
        data={"email": "teammate@example.net", "password": "new-teammate-pass"},
    )
    assert client.get("/api/funds").json()["funds"] == []
    assert client.get(f"/api/funds/{first}/agents").status_code == 403
    assert not app.state.sharing.can_access(first, "teammate@example.net")


def test_invalid_email_owner_protection_and_removed_invitation(hosted):
    client, _ = hosted
    fund = client.post("/api/funds", json={"name": "Test fund"}).json()["id"]
    assert (
        client.post(
            f"/api/funds/{fund}/members", json={"email": "not an email"}
        ).status_code
        == 422
    )
    assert (
        client.delete(f"/api/funds/{fund}/members/owner@example.com").status_code == 409
    )
    path = client.post(
        f"/api/funds/{fund}/members", json={"email": "unused@example.net"}
    ).json()["invitation_path"]
    assert (
        client.delete(f"/api/funds/{fund}/members/unused@example.net").status_code
        == 200
    )
    assert client.get(path).status_code == 410
    assert client.get("/join/unknown-token").status_code == 410


def test_membership_accounts_and_single_use_invites_persist(tmp_path):
    store = ShareStore(tmp_path, {"owner@example.com": "test"})
    store.create("fund", "owner@example.com")
    token = store.invite("fund", "new@example.net")
    store.join(token, "test-new-password")
    reopened = ShareStore(tmp_path, {"owner@example.com": "test"})
    assert reopened.can_access("fund", "new@example.net")
    assert reopened.authenticate("new@example.net", "test-new-password")
    assert not reopened.authenticate("new@example.net", "wrong-password")
    assert reopened.invitation(token) is None
    assert "test-new-password" not in reopened.path.read_bytes().decode(errors="ignore")


def test_revocation_closes_existing_live_stream(tmp_path):
    import asyncio
    from types import SimpleNamespace

    from backend.app.main import events

    async def run():
        store = ShareStore(
            tmp_path, {"owner@example.com": "test", "peer@example.com": "test"}
        )
        store.create("fund", "owner@example.com")
        store.invite("fund", "peer@example.com")
        runtime = AgentManager(root=tmp_path / "runtime")
        request = SimpleNamespace(
            state=SimpleNamespace(
                fund_manager=runtime, fund_id="fund", user="peer@example.com"
            ),
            app=SimpleNamespace(state=SimpleNamespace(sharing=store)),
        )
        stream = events(request)
        await anext(stream)
        store.remove("fund", "peer@example.com", "owner@example.com")
        runtime.publish()
        revoked = await anext(stream)
        assert revoked.event == "access_revoked"
        await stream.aclose()
        assert not runtime.subscribers
        await runtime.close()

    asyncio.run(run())


def test_migration_does_not_regrant_removed_or_private_funds(tmp_path):
    store = ShareStore(
        tmp_path, {"owner@example.com": "test", "peer@example.com": "test"}
    )
    records = {"legacy": {"owner": "owner@example.com"}}
    store.migrate(records)
    assert store.can_access("legacy", "peer@example.com")
    store.remove("legacy", "peer@example.com", "owner@example.com")
    records["new"] = {"owner": "owner@example.com"}
    store.migrate(records)
    assert not store.can_access("legacy", "peer@example.com")
    assert not store.can_access("new", "peer@example.com")
