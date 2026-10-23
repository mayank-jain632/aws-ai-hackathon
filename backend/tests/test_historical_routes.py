"""Actual authenticated tool routes -> WF replay -> persisted ledger, no brokerage."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import agent as runtime
from backend.app import paper
from backend.app.desk import PaperCriteria, ReviewInput, StrategyInput
from backend.app.funds import FundStore, Mandate
from backend.app.main import app
from backend.app.roles import allow_child, profile_for, require_tool


def test_historical_executor_real_snapshot_orders_and_read_only_dashboard(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_ENGINE", "wf")
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    monkeypatch.setattr(paper, "broker", lambda *a, **k: pytest.fail("Historical workflow called Alpaca"))
    manager = runtime.AgentManager(root=tmp_path)
    funds = FundStore(manager, root=tmp_path)
    fund = funds.create(Mandate(name="Historical execution", mode="historical", cutoff="2025-10-06"), "team")
    other = funds.create(Mandate(name="Another historical fund", mode="historical"), "team")
    board = funds.runtime(fund["id"])
    desk = board.desk
    assert not desk.state["stop"]
    desk.configure_paper_policy(PaperCriteria(
        min_sharpe=-5, min_excess_return=-1, max_order_notional=1000,
        max_daily_orders=10, rationale="Freeze numerical simulation criteria before observing evaluation.",
    ), "strategy")
    sid = desk.register(StrategyInput(
        name="Historical route test", weights={"AAPL": .2},
        cutoff="2025-10-06", end="2025-11-06", rationale="Synthetic test instruction using actual cached prices.",
        memo_paths=["test-memo.md"], changes_my_mind="Recorded evidence changes.",
    ), "strategy")["id"]
    result = desk.evaluate(sid)
    assert result["engine"] == "wf"
    desk.review(ReviewInput(
        strategy_id=sid, verdict="CHANGES_REQUESTED", evaluation_id=result["evaluation_id"],
        critique="This fixture is a route test, not an investment recommendation or clean alpha claim.",
    ), "reviewer")
    executor = runtime.LocalAgent(board, "executor", "Historical executor", "dexter", "executor")
    board.agents[executor.id] = executor
    tools = executor.snapshot()["tools"]
    assert "place_order" in tools and "submit_paper_order" not in tools
    assert not set(tools) & {"web_search", "read_file", "get_market_data", "alpaca_paper_account", "create_agent"}
    assert profile_for(executor)["children"] == []
    with pytest.raises(PermissionError):
        require_tool(executor, "web_search")
    with pytest.raises(PermissionError):
        allow_child(executor, "research")
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.setattr(app.state, "funds", funds, raising=False)
    auth = {"X-Agent-Token": board.token, "X-Agent-ID": "executor"}
    path = f"/api/funds/{fund['id']}/historical/replays"
    with TestClient(app, base_url="http://localhost") as client:
        # Avoid lifespan starting a separate store: restore the scoped fixture.
        app.state.manager, app.state.funds = manager, funds
        assert client.get(path).json() == {"replays": []}
        assert not (desk.path.parent / "historical-replay.json").exists()
        started = client.post("/api/internal/historical/start", headers=auth, json={"strategy_id": sid, "evaluation_id": result["evaluation_id"]})
        assert started.status_code == 200, started.text
        initial = started.json()
        order = {k: initial[k] for k in ["replay_id", "clock"]}
        order.update(symbol="AAPL", side="buy", notional=100, client_order_id="historical-api-order-001")
        filled = client.post("/api/internal/historical/order", headers=auth, json=order)
        assert filled.status_code == 200, filled.text
        view = filled.json()
        assert view["mode"] == "historical_simulation" and view["fills"]
        assert view["account"]["cash"] < initial["account"]["cash"]
        assert view["account"]["positions"]["AAPL"] > 0
        assert len(view["equity_curve"]) > 1
        assert client.post("/api/internal/historical/order", headers=auth, json=order).json() == view
        assert client.get(path).json() == {"replays": [view]}
        assert client.get(f"/api/funds/{other['id']}/historical/replays").json() == {"replays": []}
        assert not desk.state["orders"]
        assert client.post("/api/internal/desk/order", headers=auth, json={"strategy_id": sid, "symbol": "AAPL", "side": "buy", "notional": 100, "client_order_id": "no-broker-call-01"}).status_code == 403
        desk.state.update(stop=True, stop_source="human")
        assert client.get(path).json() == {"replays": [view]}
        assert client.post("/api/internal/historical/advance", headers=auth, json={"replay_id": view["replay_id"], "clock": view["clock"]}).status_code == 422
        assert client.get(path).json() == {"replays": [view]}
        board.context = json.dumps({"mandate": {**fund, "mode": "paper"}})
        assert client.post("/api/internal/historical/inspect", headers=auth, json={"replay_id": view["replay_id"]}).status_code == 403
