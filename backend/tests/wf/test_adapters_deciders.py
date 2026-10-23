from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.app.wf.adapters.deciders import (
    EqualWeightDecider,
    FrozenWeightsDecider,
    OpusPipelineDecider,
    SeedDecider,
)
from backend.app.wf.adapters.executions import LlmExecutionPolicy
from backend.app.wf.adapters.lazy import ComponentUnavailable
from backend.app.wf.adapters.pit_view import BoundPit, DatedPit
from backend.app.wf.config import WfConfig
from backend.app.wf.interfaces import Decider, PortfolioSnapshot
from backend.app.wf.llm import CACHE_DIR, Llm
from backend.app.wf.pit import PitData
from backend.app.wf.schemas import DecisionRecord
from backend.tests.wf._adapter_fakes import CLEAN_DATE, fake_ctx, stub_llm
from backend.tests.wf.conftest_helpers import FakePit

ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / "reports" / "wf" / "final" / "decisions"


def test_opus_pipeline_builds_book_from_validated_plan() -> None:
    book = OpusPipelineDecider(llm=stub_llm()).decide(fake_ctx())
    assert book.weights == {"AAPL": 0.25}  # 0.5 clamped to cfg.max_weight by the validator
    assert book.stop_pct == {"AAPL": 0.05} and book.target_pct == {"AAPL": 0.1}
    assert book.rationale == "sum"
    json.dumps(book.provenance)  # JSON-safe
    assert {"memos", "sources", "plan"} <= set(book.provenance)
    assert isinstance(OpusPipelineDecider(llm=stub_llm()), Decider)


def test_opus_pipeline_refuses_contaminated_dates() -> None:
    with pytest.raises(ValueError, match="clean_start"):
        OpusPipelineDecider(llm=stub_llm()).decide(fake_ctx("2024-01-05"))


def test_seed_decider_uses_injected_seed_fn() -> None:
    seen = {}

    def seed_fn(memos, universe, max_position):
        seen.update(n=len(memos), universe=universe, mp=max_position)
        return {"AAPL": 0.6, "MSFT": 0.4}, {"conviction": {"AAPL": 1.0}}

    book = SeedDecider(max_position=0.6, llm=stub_llm(), seed_fn=seed_fn).decide(fake_ctx())
    assert book.weights == {"AAPL": 0.6, "MSFT": 0.4}
    assert seen == {"n": 5, "universe": ["AAPL", "MSFT", "NVDA"], "mp": 0.6}
    assert book.provenance["seed"] == {"conviction": {"AAPL": 1.0}}


def test_seed_decider_names_missing_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "backend.app.synthesis.strategy", None)  # force ImportError
    with pytest.raises(ComponentUnavailable, match="backend.app.synthesis.strategy"):
        SeedDecider(llm=stub_llm()).decide(fake_ctx())


def test_frozen_and_equal_weight() -> None:
    ctx = fake_ctx()
    assert FrozenWeightsDecider({"AAPL": 0.5}).decide(ctx).weights == {"AAPL": 0.5}
    eq = EqualWeightDecider().decide(ctx)
    assert eq.weights == {t: pytest.approx(1 / 3) for t in ctx.universe}
    with pytest.raises(ValueError, match="outside the universe"):
        FrozenWeightsDecider({"ZZZ": 0.5}).decide(ctx)
    with pytest.raises(ValueError, match="frozen dates"):
        FrozenWeightsDecider({"AAPL": 0.5}, dates=["2025-01-01"]).decide(ctx)


def test_bound_pit_delegates_and_dated_pit_refuses_other_dates() -> None:
    view = BoundPit(FakePit(), CLEAN_DATE)
    assert view.last_close("AAPL") == 100.0
    assert view.execution_context(["AAPL"])["AAPL"]["last_close"] == 100.0
    assert view.evidence("macro", ["AAPL"])[0] == "digest macro"
    with pytest.raises(ValueError, match="bound to"):
        DatedPit(view).last_close("2030-01-01", "AAPL")


class _NoNetwork:
    def converse(self, **_):
        raise AssertionError("network touched: frozen reply was not cached")


def _frozen_dates(n: int = 3) -> list[str]:
    return sorted(p.stem for p in FROZEN.glob("*.json"))[-n:]


needs_frozen = pytest.mark.skipif(
    not FROZEN.exists() or not CACHE_DIR.exists() or not (ROOT / "data" / "wf" / "prices").exists(),
    reason="frozen run decisions or LLM cache absent",
)


@needs_frozen
def test_frozen_run_replays_from_cache_without_network() -> None:
    pit, llm = PitData(), Llm("us.anthropic.claude-opus-4-6-v1", client=_NoNetwork())
    decider, execution = OpusPipelineDecider(llm=llm), LlmExecutionPolicy(llm=llm)
    for d in _frozen_dates():
        rec = DecisionRecord.model_validate_json((FROZEN / f"{d}.json").read_text())
        ctx = fake_ctx(d, WfConfig().universe, PortfolioSnapshot(d, 1e6, 1e6), pit)
        book = decider.decide(ctx)
        assert book.weights == {p.ticker: p.target_weight for p in rec.plan.plans}
        assert book.stop_pct == {p.ticker: p.stop_pct for p in rec.plan.plans}
        assert execution.plan(ctx, book) == rec.orders
    assert llm.calls == 0

