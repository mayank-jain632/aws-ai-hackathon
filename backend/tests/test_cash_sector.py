"""Fund cash/sector constraints through frozen strategy, WF and paper submission."""
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app import paper
from backend.app.desk import Desk, OrderInput, Policy, StrategyInput, check_allocation
from backend.app.synthesis.orders import plan_orders

MANDATE = {"capital": 95000, "min_cash": 5, "max_sector": 40, "max_position": 20,
           "max_drawdown": 15, "universe": ["AAPL", "MSFT", "NVDA", "JPM", "PG", "CAT"],
           "mode": "paper", "trading_allowed": True, "approval_required": False,
           "rebalance": "monthly", "exclusions": []}
WEIGHTS = {"AAPL": .15, "MSFT": .15, "JPM": .2, "PG": .2, "CAT": .2}


def policy():
    return Policy(universe=MANDATE["universe"], max_position=.2, max_drawdown=.15,
                  min_sharpe=-5, min_excess_return=-1, max_order_notional=20000,
                  max_daily_orders=10, trading_allowed=True, approval_required=False)


def snapshot(positions=None, cash=100000):
    return {"account": {"status": "ACTIVE", "trading_blocked": False, "account_blocked": False,
                        "equity": "100000", "cash": str(cash)},
            "positions": [{"symbol": k, "market_value": str(v), "qty": "1"} for k, v in (positions or {}).items()],
            "open_orders": []}


def strategy(weights=None):
    return StrategyInput(name="Cash-reserving allocation", weights=weights or WEIGHTS,
                         cutoff="2025-10-06", end="2026-06-30", rationale="Dated inputs",
                         memo_paths=["memo.md"], changes_my_mind="Evidence changes")


def test_registration_preserves_cash_and_rejects_mandate_breaches(tmp_path):
    desk = Desk(SimpleNamespace(registry=tmp_path / "agents.json", context=json.dumps({"mandate": MANDATE})))
    desk.set_policy(policy())
    registered = desk.register(strategy(), "author")
    assert sum(registered["weights"].values()) == pytest.approx(.9)
    with pytest.raises(ValueError, match="cash reserve"):
        desk.register(strategy({"AAPL": .2, "MSFT": .2, "JPM": .2, "PG": .2, "CAT": .2}), "author")
    with pytest.raises(ValueError, match="sector"):
        desk.register(strategy({"AAPL": .2, "MSFT": .2, "NVDA": .1, "JPM": .2}), "author")
    with pytest.raises(ValidationError):
        strategy({"AAPL": .7, "MSFT": .4})
    with pytest.raises(ValueError, match="Unknown sector"):
        check_allocation({"UNKNOWN": .1}, MANDATE)


def test_plan_reserves_cash_and_sector_capacity_without_counting_sell_proceeds():
    result = plan_orders("strategy", WEIGHTS, snapshot(), policy(), MANDATE, "batch")
    assert result.ready
    assert sum(o.notional for o in result.orders) == pytest.approx(85500)
    assert result.capital - sum(o.notional for o in result.orders) >= 4750
    # Existing technology exposure consumes the same sector budget for later buys.
    result = plan_orders("strategy", WEIGHTS, snapshot({"NVDA": 38000}, cash=62000), policy(), MANDATE, "next")
    assert not any(o.side == "buy" and o.symbol in {"AAPL", "MSFT"} for o in result.orders)
    # Cash is genuinely reserved even when book targets require further buying.
    result = plan_orders("strategy", WEIGHTS, snapshot(cash=5000), policy(), MANDATE, "lowcash")
    assert sum(o.notional for o in result.orders if o.side == "buy") <= 250


@pytest.mark.parametrize("positions,cash,reason", [
    ({}, 4800, "cash reserve"),
    ({"NVDA": 37950}, 62050, "sector"),
    ({"UNKNOWN": 10}, 99990, "Unknown sector"),
])
def test_submit_rechecks_actual_projected_constraints_before_broker(monkeypatch, positions, cash, reason):
    desk = SimpleNamespace(lock=paper.threading.RLock(), manager=SimpleNamespace(context=json.dumps({"mandate": MANDATE})),
                           state={"orders": {}}, execution_checks=lambda _: (policy(), {"weights": WEIGHTS}))
    monkeypatch.setattr(paper, "account_snapshot", lambda: snapshot(positions, cash))
    monkeypatch.setattr(paper.watchdog_gate, "enforce", lambda *args: None)
    monkeypatch.setattr(paper, "broker", lambda *args: pytest.fail("Constraint breach reached broker"))
    order = OrderInput(strategy_id="strategy", symbol="AAPL", side="buy", notional=100, client_order_id="cash-sector-001")
    with pytest.raises(ValueError, match=reason):
        paper.submit(desk, order)
    assert desk.state["orders"] == {}


def test_allowed_projected_order_reaches_paper_adapter(monkeypatch):
    events = []
    desk = SimpleNamespace(lock=paper.threading.RLock(), manager=SimpleNamespace(context=json.dumps({"mandate": MANDATE})),
                           state={"orders": {}}, execution_checks=lambda _: (policy(), {"weights": WEIGHTS}),
                           event=lambda *args: events.append(args))
    monkeypatch.setattr(paper, "account_snapshot", snapshot)
    monkeypatch.setattr(paper.watchdog_gate, "enforce", lambda *args: None)
    calls = []
    def broker(method, path, body):
        calls.append((method, path, body))
        return {"id": "stub-receipt", "status": "accepted"}
    monkeypatch.setattr(paper, "broker", broker)
    order = OrderInput(strategy_id="strategy", symbol="AAPL", side="buy", notional=100, client_order_id="cash-sector-002")
    assert paper.submit(desk, order)["status"] == "accepted"
    assert len(calls) == 1 and events


def test_wf_gate_preserves_cash_weights(monkeypatch):
    from backend.app.wf import gate
    from backend.app.wf.adapters.evaluators import WfEvaluator
    seen = []
    original = WfEvaluator.evaluate
    def capture(self, weights, cutoff, end):
        seen.append((self.normalize, sum(weights.values())))
        return original(self, weights, cutoff, end)
    monkeypatch.setattr(WfEvaluator, "evaluate", capture)
    record = strategy().model_dump(mode="json")
    result = gate.evaluate_with_wf("cash-strategy", record, policy(), now="2026-10-23", policy_hash="hash")
    assert seen == [(False, pytest.approx(.9))]
    fully_invested = WfEvaluator(normalize=True).evaluate(record["weights"], record["cutoff"], record["end"])
    assert result["metrics"]["portfolio"]["total_return"] != pytest.approx(fully_invested.portfolio.total_return)


def test_legacy_refuses_to_normalize_away_frozen_cash(tmp_path, monkeypatch):
    desk = Desk(SimpleNamespace(registry=tmp_path / "agents.json"))
    desk.set_policy(policy())
    sid = desk.register(strategy(), "author")["id"]
    monkeypatch.setenv("BACKTEST_ENGINE", "legacy")
    with pytest.raises(ValueError, match="Cash allocations require the WF"):
        desk.evaluate(sid)
