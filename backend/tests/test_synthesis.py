"""Synthesis layer: seed weights, significance maths, order planning, and the routes."""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import agent as runtime
from backend.app.desk import Policy, desk_for
from backend.app.main import app
from backend.app.roles import PROFILES
from backend.app.schema import Memo, View
from backend.app.synthesis import orders, significance, strategy
from backend.app.synthesis.schema import ResearchBundle

UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "XOM", "UNH", "PG", "CAT"]


def memo(analyst, views):
    return Memo(
        analyst=analyst,
        date="2023-01-01",
        headline=f"{analyst} view",
        body="test memo",
        views=[View(ticker=t, stance=s, confidence=c, note="n", sources=[]) for t, s, c in views],
    )


MEMOS = [
    memo("technical", [("XOM", "long", 0.8), ("CAT", "long", 0.7), ("AMZN", "avoid", 0.6)]),
    memo("fundamentals", [("MSFT", "long", 0.8), ("AAPL", "long", 0.7), ("AMZN", "avoid", 0.6), ("NVDA", "long", 0.6)]),
    memo("macro", [("PG", "long", 0.6), ("JPM", "neutral", 0.5)]),
]


def bundle():
    return ResearchBundle(cutoff="2023-01-01", end="2024-01-01", memos=MEMOS, memo_paths=["memos/technical.md"])


# ------------------------------------------------------------------ seed and clamping


def test_seed_drops_avoided_and_uncovered_and_clamps():
    weights, detail = strategy.seed_from_memos(MEMOS, UNIVERSE, max_position=0.2)
    assert "AMZN" in detail.dropped and detail.dropped["AMZN"].startswith("net avoid")
    assert "GOOGL" in detail.dropped and detail.dropped["GOOGL"] == "no analyst view"
    assert "UNH" in detail.dropped
    assert abs(sum(weights.values()) - 1) < 1e-6
    assert max(weights.values()) <= 0.2 + 1e-9
    assert weights["MSFT"] >= weights["JPM"]


def test_clamp_redistributes_until_feasible():
    w, clamped = strategy.clamp_weights({"A": 0.9, "B": 0.05, "C": 0.05}, 0.5)
    assert w["A"] == 0.5 and abs(sum(w.values()) - 1) < 1e-6 and clamped == ["A"]
    w, _ = strategy.clamp_weights({"A": 1.0, "B": 1.0}, 0.5)
    assert w == {"A": 0.5, "B": 0.5}


def test_synthesize_in_mock_mode_registers_valid_input(monkeypatch):
    monkeypatch.setenv("MOCK_AGENTS", "1")
    strategy.mock_mode.cache_clear()
    policy = Policy(universe=UNIVERSE, max_position=0.25, max_drawdown=0.3, min_sharpe=0, min_excess_return=-1,
                    max_order_notional=5000, max_daily_orders=20)
    mandate = {"universe": UNIVERSE, "max_position": 20, "capital": 100000}
    result = strategy.synthesize("test", bundle(), policy, mandate)
    s = result.strategy
    assert abs(sum(s["weights"].values()) - 1) < 1e-6
    assert max(s["weights"].values()) <= 0.2 + 1e-6  # mandate tighter than policy
    assert result.model_used is False and "seed" in result.model_note
    assert s["memo_paths"] == ["memos/technical.md"] and s["rationale"]


def test_synthesize_rejects_infeasible_cap():
    policy = Policy(universe=UNIVERSE[:3], max_position=0.2, max_drawdown=0.3, min_sharpe=0, min_excess_return=-1,
                    max_order_notional=5000, max_daily_orders=20)
    with pytest.raises(ValueError, match="cannot reach full investment"):
        strategy.synthesize("x", bundle(), policy, None, use_model=False)


# ------------------------------------------------------------------ significance


def test_t_test_and_bootstrap():
    x = np.array([0.02, 0.03, 0.01, 0.04, 0.02, 0.03])
    t, p = significance.t_test(x)
    assert t > 4 and p < 0.01
    lo, hi = significance.bootstrap_ci(x)
    assert lo < x.mean() < hi
    assert significance.t_test(np.array([0.0, 0.0])) == (0.0, 1.0)


def test_walk_forward_on_snapshot():
    weights = {"AAPL": 0.5, "MSFT": 0.5}
    result = significance.walk_forward("sid", weights, horizon_days=120)
    assert result.n_windows >= significance.MIN_WINDOWS
    assert 0 <= result.hit_rate_vs_spy <= 1
    assert result.ci95_excess_vs_spy[0] <= result.mean_excess_vs_spy <= result.ci95_excess_vs_spy[1]
    assert all(w.cutoff < w.end for w in result.windows)
    assert "overlap" in result.limitations
    with pytest.raises(ValueError, match="walk-forward windows"):
        significance.walk_forward("sid", weights, first_cutoff=__import__("datetime").date(2025, 1, 1), horizon_days=120)


# ------------------------------------------------------------------ order planner


def policy():
    return Policy(universe=UNIVERSE, max_position=0.3, max_drawdown=0.3, min_sharpe=0, min_excess_return=-1,
                  max_order_notional=4000, max_daily_orders=3)


def snapshot(cash=10000, equity=12000, positions=None, open_orders=None):
    return {
        "paper": True,
        "account": {"status": "ACTIVE", "cash": cash, "equity": equity, "trading_blocked": False, "account_blocked": False},
        "positions": positions or [],
        "open_orders": open_orders or [],
    }


def test_plan_sells_first_and_caps_notional():
    weights = {"AAPL": 0.5, "MSFT": 0.5}
    snap = snapshot(cash=3000, equity=12000, positions=[{"symbol": "XOM", "market_value": 9000}])
    plan = orders.plan_orders("sid", weights, snap, policy(), None, "run1")
    assert plan.ready
    assert plan.orders[0].symbol == "XOM" and plan.orders[0].side == "sell"
    assert plan.orders[0].notional == 4000 and "capped" in plan.orders[0].note
    buys = [o for o in plan.orders if o.side == "buy"]
    assert sum(o.notional for o in buys) <= 3000 + 1e-6
    assert all(o.client_order_id.startswith("run1-") for o in plan.orders)
    assert len(plan.orders) <= 3


def test_plan_respects_mandate_capital_and_blocks_open_orders():
    weights = {"AAPL": 1.0}
    mandate = {"capital": 5000, "max_position": 50}
    plan = orders.plan_orders("sid", weights, snapshot(cash=10000, equity=20000), policy(), mandate, "r")
    assert plan.capital == 5000
    assert plan.orders[0].target_value == 1500  # min(1.0, 0.3 policy, 0.5 mandate) * 5000
    blocked = orders.plan_orders("sid", weights, snapshot(open_orders=[{"id": 1}]), policy(), None, "r")
    assert not blocked.ready and "open orders" in blocked.blocked[0]


def test_plan_nothing_to_trade():
    plan = orders.plan_orders("sid", {"AAPL": 1.0}, snapshot(cash=0, equity=3000, positions=[{"symbol": "AAPL", "market_value": 3000}]),
                              Policy(universe=UNIVERSE, max_position=1, max_drawdown=1, min_sharpe=0, min_excess_return=-1,
                                     max_order_notional=1e6, max_daily_orders=10), None, "r")
    assert not plan.ready and plan.blocked == ["nothing to trade: holdings already match the strategy"]


# ------------------------------------------------------------------ routes


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    monkeypatch.setattr(runtime, "LOCAL", tmp_path / ".local/agent")
    monkeypatch.setenv("MOCK_AGENTS", "1")
    strategy.mock_mode.cache_clear()
    manager = runtime.AgentManager()
    for role in PROFILES:
        if role != "orchestrator":
            manager.agents[role] = runtime.LocalAgent(manager, role, role, "dexter", role)
    manager.token = "TOKEN"
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.delattr(app.state, "funds", raising=False)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    client = TestClient(app, base_url="http://localhost")
    yield manager, client
    client.close()


def headers(role):
    return {"X-Agent-Token": "TOKEN", "X-Agent-ID": role}


def test_synthesize_route_registers_and_records(board, monkeypatch):
    manager, client = board
    assert client.put("/api/desk/policy", json=policy().model_dump()).status_code == 200
    body = {"name": "desk book", "bundle": json.loads(bundle().model_dump_json()), "use_model": False}
    denied = client.post("/api/internal/desk/synthesize", headers=headers("research"), json=body)
    assert denied.status_code == 403
    ok = client.post("/api/internal/desk/synthesize", headers=headers("strategy"), json=body)
    assert ok.status_code == 200, ok.text
    sid = ok.json()["strategy"]["id"]
    desk = desk_for(manager)
    assert sid in desk.state["strategies"]
    assert ok.json()["seed"]["dropped"]["AMZN"].startswith("net avoid")
    runs = client.get("/api/desk/runs").json()["runs"]
    assert runs[-1]["kind"] == "synthesis" and runs[-1]["strategy_id"] == sid
    sig = client.get(f"/api/desk/strategies/{sid}/significance?horizon_days=120")
    assert sig.status_code == 200, sig.text
    assert sig.json()["n_windows"] >= significance.MIN_WINDOWS
    assert client.get("/api/desk/runs").json()["runs"][-1]["kind"] == "significance"


def test_plan_orders_route_requires_gates(board, monkeypatch):
    manager, client = board
    client.put("/api/desk/policy", json=policy().model_dump())
    body = {"name": "b", "bundle": json.loads(bundle().model_dump_json()), "use_model": False}
    sid = client.post("/api/internal/desk/synthesize", headers=headers("strategy"), json=body).json()["strategy"]["id"]
    blocked = client.post("/api/internal/desk/plan-orders", headers=headers("executor"), json={"strategy_id": sid})
    assert blocked.status_code == 422 and "stop" in blocked.text.lower()
    monkeypatch.setattr("backend.app.routes.synthesis.account_snapshot", lambda: snapshot(cash=5000, equity=5000))
    desk = desk_for(manager)
    desk.state["stop"] = False
    desk.state["policy"]["trading_allowed"] = True
    desk.state["policy"]["approval_required"] = False
    desk.evaluate(sid)
    desk.state["tests"][sid]["verdict"] = "PASS"
    client.post("/api/internal/desk/review", headers=headers("adversarial"),
                json={"strategy_id": sid, "verdict": "APPROVE", "critique": "independent check of concentration and evidence", "evaluation_id": desk.state["tests"][sid]["evaluation_id"]})
    plan = client.post("/api/internal/desk/plan-orders", headers=headers("executor"), json={"strategy_id": sid})
    assert plan.status_code == 200, plan.text
    assert plan.json()["ready"] and all(o["side"] == "buy" for o in plan.json()["orders"])
    assert sum(o["notional"] for o in plan.json()["orders"]) <= 5000 + 1e-6
    persisted = client.get("/api/desk/runs").json()["runs"][-1]
    assert persisted["kind"] == "order_plan"
    assert persisted["orders"] == plan.json()["orders"]
    assert persisted["ready"] is True
    assert not desk.state["orders"]  # Prepared intent is not a broker submission.


def test_execute_plan_submits_in_order_and_halts_on_block(board, monkeypatch):
    from backend.app import paper

    manager, client = board
    client.put("/api/desk/policy", json=policy().model_dump())
    body = {"name": "b", "bundle": json.loads(bundle().model_dump_json()), "use_model": False}
    sid = client.post("/api/internal/desk/synthesize", headers=headers("strategy"), json=body).json()["strategy"]["id"]
    desk = desk_for(manager)
    desk.state["stop"] = False
    desk.state["policy"]["trading_allowed"] = True
    desk.state["policy"]["approval_required"] = False
    desk.evaluate(sid)
    desk.state["tests"][sid]["verdict"] = "PASS"
    client.post("/api/internal/desk/review", headers=headers("adversarial"),
                json={"strategy_id": sid, "verdict": "APPROVE", "critique": "independent check of concentration and evidence", "evaluation_id": desk.state["tests"][sid]["evaluation_id"]})
    snap = snapshot(cash=5000, equity=5000)
    monkeypatch.setattr("backend.app.routes.synthesis.account_snapshot", lambda: snap)
    monkeypatch.setattr(paper, "account_snapshot", lambda: snap)
    calls = []

    def fake_broker(method, path, body=None):
        calls.append(body["client_order_id"])
        snap["open_orders"].append({"id": body["client_order_id"]})  # broker now has an open order
        return {"id": f"brk-{len(calls)}", "status": "accepted", "filled_qty": "0"}

    monkeypatch.setattr(paper, "broker", fake_broker)
    plan = client.post("/api/internal/desk/plan-orders", headers=headers("executor"), json={"strategy_id": sid}).json()
    assert plan["ready"] and len(plan["orders"]) >= 2
    orders = [{"strategy_id": sid, "symbol": o["symbol"], "side": o["side"], "notional": o["notional"], "client_order_id": o["client_order_id"]} for o in plan["orders"]]
    denied = client.post("/api/internal/desk/execute-plan", headers=headers("strategy"), json={"strategy_id": sid, "orders": orders})
    assert denied.status_code == 403
    result = client.post("/api/internal/desk/execute-plan", headers=headers("executor"), json={"strategy_id": sid, "orders": orders}).json()
    # first order accepted, second blocked because the broker now reports an open order
    assert result["outcome"] == "blocked" and len(result["submitted"]) == 1
    assert result["submitted"][0]["status"] == "accepted" and calls == [orders[0]["client_order_id"]]
    assert "open" in result["halted_reason"].lower() or "existing" in result["halted_reason"].lower()
    assert result["remaining_client_order_ids"] == [o["client_order_id"] for o in orders[2:]]
    assert client.get("/api/desk/runs").json()["runs"][-1]["kind"] == "execution"
