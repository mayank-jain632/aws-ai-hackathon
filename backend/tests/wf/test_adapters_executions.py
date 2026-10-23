from __future__ import annotations

import pytest

from backend.app.wf.adapters.executions import (
    LlmExecutionPolicy,
    SynthesisPlannerExecution,
    TargetWeightExecution,
)
from backend.app.wf.adapters.lazy import ComponentUnavailable
from backend.app.wf.interfaces import ExecutionPolicy, PortfolioSnapshot, TargetBook
from backend.tests.wf._adapter_fakes import (
    CLEAN_DATE,
    fake_ctx,
    fake_plan,
    planned,
    stub_llm,
)


def _book(**kw) -> TargetBook:
    base = {"decision_date": CLEAN_DATE, "weights": {"AAPL": 0.3, "MSFT": 0.2},
            "stop_pct": {"AAPL": 0.05}, "target_pct": {"AAPL": 0.1}}
    return TargetBook(**{**base, **kw})


def test_target_weight_execution_zeroes_absent_names_and_has_no_stops() -> None:
    orders = TargetWeightExecution().plan(fake_ctx(), _book())
    got = {i.ticker: i for i in orders.intents}
    assert {t: i.target_weight for t, i in got.items()} == {"AAPL": 0.3, "MSFT": 0.2, "NVDA": 0.0}
    assert all(i.entry == "market_open" and i.stop_price is None for i in got.values())


def test_target_weight_execution_stops_from_last_close() -> None:
    orders = TargetWeightExecution(use_stops=True).plan(fake_ctx(), _book())
    aapl = next(i for i in orders.intents if i.ticker == "AAPL")
    assert (aapl.stop_price, aapl.target_price) == (95.0, 110.0)  # FakePit close is 100
    assert next(i for i in orders.intents if i.ticker == "MSFT").stop_price is None


def test_target_weight_execution_rejects_unknown_ticker() -> None:
    with pytest.raises(ValueError, match="outside the universe"):
        TargetWeightExecution().plan(fake_ctx(), _book(weights={"ZZZ": 0.1}))


def test_llm_execution_wraps_stage_and_exits_unplanned_names() -> None:
    policy = LlmExecutionPolicy(llm=stub_llm())
    assert isinstance(policy, ExecutionPolicy)
    orders = policy.plan(fake_ctx(), _book(weights={"AAPL": 0.25}))
    got = {i.ticker: i for i in orders.intents}
    assert got["AAPL"].entry == "limit" and got["AAPL"].stop_price == 95.0  # stub: limit 0.5 ATR, stop 5%
    assert got["MSFT"].target_weight == 0.0 and got["NVDA"].target_weight == 0.0


HELD = PortfolioSnapshot(CLEAN_DATE, 1_000_000.0, 700_000.0, {"AAPL": 300_000.0}, {"AAPL": 3000.0})
POLICY = object()


def _planner(plan, calls=None):
    def fn(strategy_id, weights, snapshot, policy, mandate, run_tag):
        if calls is not None:
            calls.append((strategy_id, weights, snapshot, policy, mandate, run_tag))
        return plan

    return fn


def test_planner_converts_hand_computed_example() -> None:
    plan = fake_plan([planned("AAPL", "sell", 100_000, 300_000), planned("MSFT", "buy", 300_000, 0)])
    calls: list = []
    exe = SynthesisPlannerExecution(policy=POLICY, planner=_planner(plan, calls), mandate={"capital": 1e6})
    ctx = fake_ctx(portfolio=HELD)
    orders = exe.plan(ctx, _book(weights={"AAPL": 0.2, "MSFT": 0.3}))
    assert {i.ticker: i.target_weight for i in orders.intents} == {"AAPL": pytest.approx(0.2), "MSFT": pytest.approx(0.3)}
    assert all(i.entry == "market_open" and i.stop_price is None for i in orders.intents)
    assert orders.blocked == []
    _, weights, snap, policy, mandate, tag = calls[0]
    assert weights == {"AAPL": 0.2, "MSFT": 0.3} and policy is POLICY and mandate == {"capital": 1e6}
    assert snap["account"]["equity"] == 1_000_000.0 and snap["positions"][0]["symbol"] == "AAPL"
    assert tag == f"wf-{CLEAN_DATE}"


@pytest.mark.parametrize(
    "plan",
    [fake_plan(blocked=["paper account is not active"], ready=False), fake_plan([planned("MSFT", "buy", 1, 0)], ready=False)],
)
def test_blocked_or_not_ready_plan_yields_empty_intents_and_reasons(plan) -> None:
    exe = SynthesisPlannerExecution(policy=POLICY, planner=_planner(plan))
    orders = exe.plan(fake_ctx(portfolio=HELD), _book())
    assert orders.intents == [] and orders.blocked


def test_partial_plan_mentions_only_planned_names() -> None:
    plan = fake_plan([planned("MSFT", "buy", 50_000, 0)], skipped={"AAPL": "within 5 of target"})
    orders = SynthesisPlannerExecution(policy=POLICY, planner=_planner(plan)).plan(fake_ctx(portfolio=HELD), _book())
    assert [i.ticker for i in orders.intents] == ["MSFT"]


def test_planner_missing_module_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "backend.app.synthesis.orders", None)
    with pytest.raises(ComponentUnavailable, match="backend.app.synthesis.orders"):
        SynthesisPlannerExecution(policy=POLICY).plan(fake_ctx(portfolio=HELD), _book())


def test_real_planner_contract() -> None:
    pytest.importorskip("backend.app.synthesis.orders")
    pytest.importorskip("backend.app.desk")
    exe = SynthesisPlannerExecution()
    ctx = fake_ctx(universe=("AAPL", "MSFT"), portfolio=HELD)
    orders = exe.plan(ctx, _book(weights={"AAPL": 0.2, "MSFT": 0.3}))
    got = {i.ticker: i.target_weight for i in orders.intents}
    assert got == {"AAPL": pytest.approx(0.2), "MSFT": pytest.approx(0.3)}
