"""The gate on the leakage-safe engine: labels, verdict logic, and the Desk opt-in switch."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.desk import Desk, Policy, ReviewInput, StrategyInput
from backend.app.schema import Metrics
from backend.app.wf import gate, market
from backend.app.wf.interfaces import EvalResult

OPUS46 = "us.anthropic.claude-opus-4-6-v1"
HAVE_WF_DATA = (market.DEFAULT_DATA_DIR / "prices" / "SPY.csv").exists()
needs_data = pytest.mark.skipif(not HAVE_WF_DATA, reason="data/wf snapshot not present")


def metrics(total: float, drawdown: float = -0.05, sharpe: float = 1.0) -> Metrics:
    return Metrics(total_return=total, cagr=total, max_drawdown=drawdown, sharpe=sharpe)


class StubEvaluator:
    def __init__(self, portfolio: Metrics, benchmark: Metrics) -> None:
        self.portfolio, self.benchmark = portfolio, benchmark

    def evaluate(self, weights, cutoff, end) -> EvalResult:
        return EvalResult(cutoff=cutoff, end=end, portfolio=self.portfolio, benchmark=self.benchmark,
                          assumptions=["stub"])


def policy(**over) -> Policy:
    base = {"universe": ["AAPL", "MSFT"], "max_position": 0.6, "max_drawdown": 0.2, "min_sharpe": 0.5,
            "min_excess_return": 0.0, "max_order_notional": 1000, "max_daily_orders": 10}
    return Policy(**{**base, **over})


def record(cutoff="2025-10-06", end="2026-06-30", weights=None) -> dict:
    return {"cutoff": cutoff, "end": end, "weights": weights or {"AAPL": 0.5, "MSFT": 0.5}}


# --- labels ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cutoff", "model", "expected"),
    [
        ("2025-10-06", OPUS46, "model-clean"),
        ("2025-09-15", OPUS46, "contaminated"),
        ("2023-01-03", OPUS46, "contaminated"),
        ("2026-05-04", "us.openai.gpt-6.1-sol", "unknown-cutoff"),
        ("2026-05-04", None, "unknown-cutoff"),
    ],
)
def test_window_label(cutoff: str, model: str | None, expected: str) -> None:
    label, _ = gate.window_label(cutoff, model)

    assert label == expected


def test_leakage_statement_never_calls_unknown_models_clean() -> None:
    text = gate.leakage_statement("unknown-cutoff", "2026-05-04", "gpt-x", None)

    assert "NOT labelled model-clean" in text


# --- verdict logic -----------------------------------------------------------------------


@needs_data
def test_verdict_pass_and_checks() -> None:
    ev = StubEvaluator(metrics(0.12, -0.05, 1.1), metrics(0.08))

    out = gate.evaluate_with_wf("sid", record(), policy(), now="t", policy_hash="h", author_model=OPUS46,
                                evaluator=ev)

    assert out["verdict"] == "PASS" and all(out["checks"].values())
    assert out["metrics"]["portfolio"]["total_return"] == 0.12
    assert out["metrics"]["baseline"]["total_return"] == 0.08
    assert out["engine"] == "wf" and out["label"] == "model-clean" and out["policy_hash"] == "h"


@needs_data
@pytest.mark.parametrize(
    ("portfolio", "failing"),
    [
        (metrics(0.12, -0.40, 1.1), "drawdown"),
        (metrics(0.12, -0.05, 0.1), "sharpe"),
        (metrics(0.05, -0.05, 1.1), "excess_return"),
    ],
)
def test_verdict_fails_each_threshold(portfolio: Metrics, failing: str) -> None:
    ev = StubEvaluator(portfolio, metrics(0.08))

    out = gate.evaluate_with_wf("sid", record(), policy(), now="t", policy_hash="h", evaluator=ev)

    assert out["verdict"] == "FAIL" and out["checks"][failing] is False


@needs_data
def test_mandate_check_rejects_oversized_position() -> None:
    ev = StubEvaluator(metrics(0.12, -0.05, 1.1), metrics(0.08))

    out = gate.evaluate_with_wf("sid", record(weights={"AAPL": 0.9, "MSFT": 0.1}), policy(), now="t",
                                policy_hash="h", evaluator=ev)

    assert out["checks"]["mandate"] is False and out["verdict"] == "FAIL"


@needs_data
def test_refuses_a_window_beyond_the_snapshot() -> None:
    with pytest.raises(ValueError, match="refusing to silently shorten"):
        gate.evaluate_with_wf("sid", record(end="2030-01-01"), policy(), now="t", policy_hash="h",
                              evaluator=StubEvaluator(metrics(0.1), metrics(0.1)))


# --- Desk integration --------------------------------------------------------------------


def make_desk(tmp_path: Path, author_model: str | None) -> tuple[Desk, str]:
    agents = {"strat": SimpleNamespace(model=author_model)} if author_model else {}
    desk = Desk(SimpleNamespace(registry=tmp_path / "agents.json", agents=agents))
    desk.set_policy(policy(max_drawdown=0.5, min_sharpe=-9.0, min_excess_return=-1.0, max_position=0.5))
    return desk, "strat"


def register(desk: Desk, author: str, cutoff: date, end: date) -> str:
    body = StrategyInput(name="t", weights={"AAPL": 0.5, "MSFT": 0.5}, cutoff=cutoff, end=end, rationale="r",
                         memo_paths=["m.md"], changes_my_mind="x")
    return desk.register(body, author)["id"]


@needs_data
def test_desk_uses_wf_engine_when_selected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKTEST_ENGINE", "wf")
    desk, author = make_desk(tmp_path, OPUS46)
    sid = register(desk, author, date(2025, 10, 6), date(2026, 6, 30))

    out = desk.evaluate(sid)

    assert out["engine"] == "wf" and out["label"] == "model-clean"
    assert out["author_model"] == OPUS46 and out["model_training_cutoff"] == "2025-08"
    assert out["verdict"] in {"PASS", "FAIL"} and desk.state["tests"][sid] == out
    assert any(e["check"] == "backtest" for e in desk.state["events"])
    assert out["metrics"]["portfolio"].keys() == {"total_return", "cagr", "max_drawdown", "sharpe"}


@needs_data
def test_unknown_author_model_is_not_labelled_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKTEST_ENGINE", "wf")
    desk, author = make_desk(tmp_path, None)
    sid = register(desk, author, date(2025, 10, 6), date(2026, 6, 30))

    assert desk.evaluate(sid)["label"] == "unknown-cutoff"


def test_default_engine_is_wf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BACKTEST_ENGINE", raising=False)
    desk, author = make_desk(tmp_path, OPUS46)
    sid = register(desk, author, date(2023, 1, 3), date(2025, 6, 30))

    out = desk.evaluate(sid)

    assert out["engine"] == "wf" and out["label"] == "contaminated"
    assert out["verdict"] in {"PASS", "FAIL"}


@pytest.fixture
def passing_desk(tmp_path, monkeypatch):
    monkeypatch.delenv("BACKTEST_ENGINE", raising=False)
    desk, author = make_desk(tmp_path, OPUS46)
    desk.set_policy(policy(max_drawdown=1, min_sharpe=-100, min_excess_return=-1,
                           max_position=0.5, trading_allowed=True))
    sid = register(desk, author, date(2023, 1, 3), date(2024, 1, 3))
    from backend.app.desk import ReviewInput

    desk.review(ReviewInput(strategy_id=sid, verdict="APPROVE", critique="Checked frozen inputs and concentration independently."), "reviewer")
    desk.evaluate(sid)
    assert desk.state["tests"][sid]["verdict"] == "PASS"
    desk.review(ReviewInput(strategy_id=sid, verdict="APPROVE", critique="Final independent check of the actual backend evaluation.", evaluation_id=desk.state["tests"][sid]["evaluation_id"]), "reviewer")
    desk.approve(sid)
    desk.state["stop"] = False
    return desk, sid


@needs_data
def test_approval_is_bound_to_exact_evaluation_and_engine(passing_desk, monkeypatch):
    desk, sid = passing_desk
    assert desk.human_approved(sid)
    desk.execution_checks(sid)
    monkeypatch.setenv("BACKTEST_ENGINE", "legacy")
    assert not desk.test_is_current(sid)
    with pytest.raises(ValueError, match="current backend PASS"):
        desk.execution_checks(sid)
    monkeypatch.setenv("BACKTEST_ENGINE", "wf")
    desk.evaluate(sid)
    assert not desk.human_approved(sid)
    with pytest.raises(ValueError, match="final review"):
        desk.execution_checks(sid)
    desk.review(ReviewInput(strategy_id=sid, verdict="APPROVE", critique="Final independent check of the actual backend evaluation.", evaluation_id=desk.state["tests"][sid]["evaluation_id"]), "reviewer")
    desk.approve(sid)
    desk.state["tests"][sid]["metrics"]["portfolio"]["total_return"] = 999
    assert not desk.test_is_current(sid)


@needs_data
def test_historical_approval_and_result_are_preserved_but_not_executable(passing_desk):
    desk, sid = passing_desk
    test = desk.state["tests"][sid]
    for key in ("engine", "engine_version", "evaluation_id", "strategy_hash"):
        test.pop(key)
    desk.state["approved_evaluations"].clear()
    desk.save()
    reloaded = Desk(desk.manager)
    assert reloaded.state["tests"][sid] == test
    assert reloaded.state["approvals"][sid] == desk.state["approvals"][sid]
    assert not reloaded.human_approved(sid)
    with pytest.raises(ValueError, match="current backend PASS"):
        reloaded.approve(sid)


@needs_data
def test_author_model_is_frozen_and_unknown_history_stays_unknown(tmp_path, monkeypatch):
    monkeypatch.delenv("BACKTEST_ENGINE", raising=False)
    desk, author = make_desk(tmp_path, OPUS46)
    sid = register(desk, author, date(2025, 10, 6), date(2026, 6, 30))
    desk.manager.agents[author].model = "us.openai.gpt-6.1-sol"
    assert desk.evaluate(sid)["author_model"] == OPUS46
    del desk.state["strategies"][sid]["author_model"]
    out = desk.evaluate(sid)
    assert out["author_model"] is None and out["label"] == "unknown-cutoff"


@needs_data
def test_explicit_legacy_and_invalid_engine_have_no_fallback(tmp_path, monkeypatch):
    desk, author = make_desk(tmp_path, OPUS46)
    sid = register(desk, author, date(2023, 1, 3), date(2024, 1, 3))
    monkeypatch.setenv("BACKTEST_ENGINE", "legacy")
    old = desk.evaluate(sid)
    assert old["engine"] == "legacy" and old["engine_version"] == "legacy-monthly-v2"
    monkeypatch.setenv("BACKTEST_ENGINE", "typo")
    with pytest.raises(ValueError, match="no fallback"):
        desk.evaluate(sid)
    monkeypatch.setenv("BACKTEST_ENGINE", "wf")
    def unavailable(*args, **kwargs):
        raise ValueError("WF data unavailable")
    monkeypatch.setattr(gate, "evaluate_with_wf", unavailable)
    with pytest.raises(ValueError, match="WF data unavailable"):
        desk.evaluate(sid)
    assert desk.state["tests"][sid] == old
    assert not desk.test_is_current(sid)


@needs_data
def test_final_review_is_bound_to_current_evaluation_and_is_independent(passing_desk):
    desk, sid = passing_desk
    old = desk.state["tests"][sid]["evaluation_id"]
    desk.evaluate(sid)
    with pytest.raises(ValueError, match="final review"):
        desk.approve(sid)
    with pytest.raises(ValueError, match="exact current"):
        desk.review(ReviewInput(strategy_id=sid, evaluation_id=old, verdict="APPROVE", critique="Independent review of an earlier evaluation result."), "reviewer")
    current = desk.state["tests"][sid]["evaluation_id"]
    with pytest.raises(ValueError, match="own strategy"):
        desk.review(ReviewInput(strategy_id=sid, evaluation_id=current, verdict="APPROVE", critique="Claimed review by the strategy author themselves."), desk.strategy(sid)["author"])
    desk.review(ReviewInput(strategy_id=sid, evaluation_id=current, verdict="APPROVE", critique="Independent review of current metrics and leakage assumptions."), "reviewer")
    desk.approve(sid)
    assert desk.human_approved(sid)
