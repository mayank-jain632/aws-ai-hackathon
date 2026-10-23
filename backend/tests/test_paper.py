"""Verify actual order path with a broker stub, including retry and gate boundaries."""

from types import SimpleNamespace

import httpx
import pytest

from backend.app import paper
from backend.app.desk import (
    OrderInput,
    Policy,
    ReviewInput,
    StrategyInput,
    desk_for,
)


@pytest.fixture
def approved(tmp_path):
    manager = SimpleNamespace(registry=tmp_path / "agents.json", paused=False)
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
    desk.review(ReviewInput(strategy_id=sid, verdict="APPROVE", critique="Final independent check of the actual backend evaluation.", evaluation_id=desk.state["tests"][sid]["evaluation_id"]), "reviewer")
    desk.approve(sid)
    desk.state["stop"] = False
    desk.save()
    return desk, OrderInput(
        strategy_id=sid,
        symbol="AAPL",
        side="buy",
        notional=100,
        client_order_id="stable-order-001",
    )


def healthy_account():
    return {
        "account": {
            "status": "ACTIVE",
            "trading_blocked": False,
            "account_blocked": False,
            "equity": "10000",
            "cash": "10000",
        },
        "positions": [],
        "open_orders": [],
    }


def test_submit_and_idempotent_retry(approved, monkeypatch):
    desk, order = approved
    monkeypatch.setattr(paper, "account_snapshot", healthy_account)
    calls = []

    def fake_broker(method, path, body):
        calls.append((method, path, body))
        return {"id": "broker-order-1", "status": "accepted", "filled_qty": "0"}

    monkeypatch.setattr(paper, "broker", fake_broker)
    result = paper.submit(desk, order)
    assert result["status"] == "accepted" and result["filled_qty"] == "0"
    assert paper.submit(desk, order) == result
    assert len(calls) == 1
    assert calls[0][1] == "/v2/orders"
    assert calls[0][2]["notional"] == "100.00"
    assert calls[0][2]["client_order_id"] == order.client_order_id
    with pytest.raises(ValueError, match="different request"):
        paper.submit(desk, order.model_copy(update={"notional": 101}))


def test_gates_fail_before_broker(approved, monkeypatch):
    desk, order = approved
    monkeypatch.setattr(
        paper, "account_snapshot", lambda: pytest.fail("Broker must not be called")
    )
    desk.state["stop"] = True
    with pytest.raises(ValueError, match="stop"):
        paper.submit(desk, order)
    desk.state["stop"] = False
    desk.state["tests"][order.strategy_id]["verdict"] = "FAIL"
    with pytest.raises(ValueError, match="PASS"):
        paper.submit(desk, order)
    desk.state["tests"][order.strategy_id]["verdict"] = "PASS"
    desk.state["policy"]["trading_allowed"] = False
    with pytest.raises(ValueError, match="does not allow"):
        paper.submit(desk, order)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ({"open_orders": [{"symbol": "AAPL"}]}, "existing paper orders"),
        (
            {"positions": [{"symbol": "AAPL", "qty": "100", "market_value": "4990"}]},
            "position size",
        ),
        (
            {"positions": [{"symbol": "AAPL", "qty": "-1", "market_value": "-100"}]},
            "long-only",
        ),
    ],
)
def test_projected_exposure_and_pending_orders(approved, monkeypatch, mutation, reason):
    desk, order = approved
    monkeypatch.setattr(paper, "account_snapshot", lambda: healthy_account() | mutation)
    monkeypatch.setattr(paper, "broker", lambda *args: pytest.fail("Do not submit"))
    with pytest.raises(ValueError, match=reason):
        paper.submit(desk, order)


def test_unknown_submission_never_automatically_resubmits(approved, monkeypatch):
    desk, order = approved
    monkeypatch.setattr(paper, "account_snapshot", healthy_account)
    calls = []

    def timeout(*args):
        calls.append(args)
        raise httpx.ReadTimeout("Response unavailable")

    monkeypatch.setattr(paper, "broker", timeout)
    result = paper.submit(desk, order)
    assert result["status"] == "unknown"
    assert paper.submit(desk, order)["status"] == "unknown"
    assert len(calls) == 1
    restored = desk_for(SimpleNamespace(registry=desk.manager.registry))
    assert restored.state["orders"][order.client_order_id]["status"] == "unknown"


def test_paper_host_and_auth_headers(monkeypatch, tmp_path):
    monkeypatch.setattr(paper, "ROOT", tmp_path)
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "paper-secret")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    original_client = httpx.Client

    def check(request):
        assert request.url.host == "paper-api.alpaca.markets"
        assert request.headers["APCA-API-KEY-ID"] == "paper-key"
        assert request.headers["APCA-API-SECRET-KEY"] == "paper-secret"
        return httpx.Response(200, json={"status": "ACTIVE"})

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs, transport=httpx.MockTransport(check)
        ),
    )
    assert paper.broker("GET", "/v2/account")["status"] == "ACTIVE"


def test_missing_credentials_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(paper, "ROOT", tmp_path)
    for key in [
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "APCA_API_KEY_ID",
        "APCA_API_SECRET_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="not configured"):
        paper.account_snapshot()
