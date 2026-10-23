from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

from backend.app.wf.adapters.deciders import (
    EqualWeightDecider,
    FrozenWeightsDecider,
    OpusPipelineDecider,
)
from backend.app.wf.adapters.evaluators import ReferenceEvaluator, WfEvaluator
from backend.app.wf.adapters.executions import (
    LlmExecutionPolicy,
    SynthesisPlannerExecution,
    TargetWeightExecution,
)
from backend.app.wf.conformance import (
    assert_conforms,
    check_decider,
    check_evaluator,
    check_execution,
    lint_violations,
)
from backend.app.wf.interfaces import TargetBook
from backend.tests.wf._adapter_fakes import (
    AB,
    SYN_DATES,
    ab_llm,
    fake_plan,
    make_syn_pit,
    planned,
    syn_closes,
    syn_dir,
)


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return syn_dir(tmp_path)


def _decider(d, data_dir):
    return check_decider(d, make_syn_pit, SYN_DATES, AB, data_dir=data_dir)


def _book_factory(ctx) -> TargetBook:
    return TargetBook(decision_date=ctx.as_of, weights={"AAA": 0.3, "BBB": 0.2}, stop_pct={"AAA": 0.05})


def _execution(p, data_dir):
    return check_execution(p, make_syn_pit, SYN_DATES, AB, _book_factory, data_dir=data_dir)


# ---------------------------------------------------------------- built-ins conform


@pytest.mark.parametrize(
    "make",
    [
        lambda: OpusPipelineDecider(llm=ab_llm()),
        lambda: EqualWeightDecider(),
        lambda: FrozenWeightsDecider({"AAA": 0.5, "BBB": 0.5}),
    ],
)
def test_builtin_deciders_conform(make, data_dir) -> None:
    assert_conforms(_decider(make(), data_dir))


def test_builtin_execution_policies_conform(data_dir) -> None:
    def planner(strategy_id, weights, snapshot, policy, mandate, run_tag):
        eq = snapshot["account"]["equity"]
        return fake_plan([planned("BBB", "buy", 0.2 * eq, 0.0)])

    for policy in (
        TargetWeightExecution(),
        TargetWeightExecution(use_stops=True),
        LlmExecutionPolicy(llm=ab_llm()),
        SynthesisPlannerExecution(policy=object(), planner=planner),
    ):
        assert_conforms(_execution(policy, data_dir))


# ------------------------------------------------------------ deliberately bad ones


class _Base:
    version = "0"
    stateless = True

    def decide(self, ctx):  # pragma: no cover
        raise NotImplementedError


class BackdoorDecider(_Base):
    """Reads the whole price history through the bound view's private PitData."""

    name = "backdoor"

    def decide(self, ctx) -> TargetBook:
        last = float(ctx.pit.pit._prices["AAA"]["close"].iloc[-1])
        return TargetBook(decision_date=ctx.as_of, weights={"AAA": 0.5 if last > 5000 else 0.4})


class NondeterministicDecider(_Base):
    name = "coin_flip"

    def decide(self, ctx) -> TargetBook:
        return TargetBook(decision_date=ctx.as_of, weights={"AAA": random.random() * 0.5})


class NegativeWeightDecider(_Base):
    name = "short"

    def decide(self, ctx) -> TargetBook:
        return TargetBook(decision_date=ctx.as_of, weights={"AAA": -0.2, "BBB": 0.5})


def _failed(report) -> set[str]:
    return {c.name for c in report.failures}


def test_backdoor_future_read_is_caught(data_dir) -> None:
    rep = _decider(BackdoorDecider(), data_dir)
    assert "future_poison" in _failed(rep)
    with pytest.raises(AssertionError, match="future_poison"):
        assert_conforms(rep)


def test_nondeterminism_is_caught(data_dir) -> None:
    assert "determinism" in _failed(_decider(NondeterministicDecider(), data_dir))


def test_negative_weights_are_caught(data_dir) -> None:
    assert "schema" in _failed(_decider(NegativeWeightDecider(), data_dir))


def test_importing_wf_market_is_caught(data_dir, tmp_path: Path) -> None:
    src = tmp_path / "cheater_mod.py"
    src.write_text(
        "from backend.app.wf.market import load_bars\n"
        "from backend.app.wf.interfaces import TargetBook\n\n"
        "class Cheater:\n    name = 'cheater'\n    version = '0'\n    stateless = True\n\n"
        "    def decide(self, ctx):\n"
        "        return TargetBook(decision_date=ctx.as_of, weights={'AAA': 0.5})\n"
    )
    spec = importlib.util.spec_from_file_location("cheater_mod", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cheater_mod"] = mod
    spec.loader.exec_module(mod)
    try:
        assert _failed(_decider(mod.Cheater(), data_dir)) == {"import_lint"}
    finally:
        del sys.modules["cheater_mod"]


def test_lint_rules() -> None:
    assert lint_violations("from backend.app.data import last_close\nimport backend.app.wf.market") != []
    assert lint_violations("x = d.prices_full()") != []
    assert lint_violations("from backend.app.wf.pit import PitData") == []


class OverspendPolicy:
    name = "overspend"
    version = "0"

    def plan(self, ctx, book):
        from backend.app.wf.schemas import DecisionOrders, OrderIntent

        intents = [OrderIntent(ticker=t, target_weight=0.9) for t in ctx.universe]
        return DecisionOrders(date=ctx.as_of, intents=intents)


def test_overspending_policy_is_caught(data_dir) -> None:
    failed = _failed(_execution(OverspendPolicy(), data_dir))
    assert {"schema", "no_oversell_no_overspend"} <= failed


# ---------------------------------------------------------------------- evaluators

CUT, END = "2024-01-02", "2024-12-20"
W = {"AAA": 0.6, "BBB": 0.4}


def test_builtin_evaluators_conform(data_dir) -> None:
    wf = WfEvaluator(costs_bps=0.0, data_dir=data_dir, universe=AB)
    assert_conforms(check_evaluator(
        wf, W, CUT, END, data_dir=data_dir, make_evaluator=lambda d: WfEvaluator(0.0, d, AB)))
    ref = ReferenceEvaluator(universe=AB, closes=syn_closes(data_dir), rf_annual_pct=4.0)
    assert_conforms(check_evaluator(
        ref, W, CUT, END, data_dir=data_dir,
        make_evaluator=lambda d: ReferenceEvaluator(universe=AB, closes=syn_closes(d), rf_annual_pct=4.0)))


def test_evaluator_peeking_past_end_is_caught(data_dir) -> None:
    class Peeker(WfEvaluator):
        name = "peeker"

        def evaluate(self, weights, cutoff, end):
            return super().evaluate(weights, cutoff, "2024-12-31")  # ignores `end`

    rep = check_evaluator(
        Peeker(0.0, data_dir, AB), W, CUT, END, data_dir=data_dir,
        make_evaluator=lambda d: Peeker(0.0, d, AB))
    assert {"future_poison_after_end", "output_sanity"} & _failed(rep)


def test_evaluator_accepting_unknown_ticker_is_caught(data_dir) -> None:
    class Lax:
        name = "lax"
        version = "0"

        def evaluate(self, weights, cutoff, end):
            return WfEvaluator(0.0, data_dir, AB).evaluate({k: v for k, v in weights.items() if k in AB}, cutoff, end)

    assert "rejects_unknown_ticker" in _failed(check_evaluator(Lax(), W, CUT, END))
