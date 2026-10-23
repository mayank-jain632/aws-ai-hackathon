"""Deciders: research + strategy -> `TargetBook` (hub D22).

OpusPipelineDecider   the frozen-run pipeline (five analysts, strategy) behind the Decider contract
SeedDecider           same research, then the synthesis lane's deterministic `seed_from_memos`
FrozenWeightsDecider  fixed weights from params (the blind backtester's input shape)
EqualWeightDecider    1/N over the universe

All are stateless: output depends only on ``ctx.as_of`` / ``ctx.pit`` and cached LLM replies.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar

from backend.app.agents import strategy
from backend.app.schema import Memo
from backend.app.wf import analysts, pipeline
from backend.app.wf.adapters.lazy import load_attr
from backend.app.wf.adapters.pit_view import DatedPit
from backend.app.wf.config import WfConfig
from backend.app.wf.interfaces import DecisionContext, TargetBook
from backend.app.wf.llm import Llm
from backend.app.wf.registry import register_decider
from backend.app.wf.schemas import TradePlan

log = logging.getLogger("wf.adapters.deciders")
_DEFAULTS = WfConfig()
SEED_MODULE, SEED_FN = "backend.app.synthesis.strategy", "seed_from_memos"


def _guard(ctx: DecisionContext) -> None:
    if ctx.as_of < ctx.cfg.clean_start and not ctx.contaminated:
        raise pipeline.ContaminatedDateError(
            f"{ctx.as_of} is before clean_start {ctx.cfg.clean_start}; mark the context contaminated"
        )


def _research(ctx: DecisionContext, llm: Any):
    return analysts.run_research(DatedPit(ctx.pit), llm, ctx.as_of, list(ctx.universe), ctx.masker)


def _research_provenance(memos, sources, abstained) -> dict[str, Any]:
    return {
        "memos": [m.model_dump(mode="json") for m in memos],
        "sources": [s.model_dump(mode="json") for s in sources],
        "abstained_analysts": list(abstained),
    }


def _plan_stage(llm: Any, ctx: DecisionContext, memos: list[Memo], ectx: dict) -> tuple[TradePlan, list[str]]:
    """Strategy stage exactly as `pipeline._plan_and_execute` runs it, minus the execution call."""
    uni = list(ctx.universe)
    if ctx.masker is None:
        return strategy.run_with_notes(llm, ctx.cfg, ctx.as_of, memos, uni, ectx)
    to_code, to_ticker = pipeline._code_maps(ctx.masker, uni)
    mctx = {to_code[t]: c for t, c in ectx.items() if t in to_code}
    mplan, notes = strategy.run_with_notes(
        llm, ctx.cfg, ctx.as_of, pipeline._mask_memos(memos, to_code), list(to_code.values()), mctx
    )
    return pipeline._unmask_plan(mplan, to_ticker), notes


@register_decider("opus_pipeline")
class OpusPipelineDecider:
    """Name ``opus_pipeline``. Params: model_id, temperature, max_tokens (defaults = `WfConfig`),
    or a ready ``llm``. Prompts and cache keys are unchanged, so frozen-run dates replay from disk."""

    name = "opus_pipeline"
    version = "1"
    stateless: ClassVar[bool] = True

    def __init__(
        self,
        model_id: str = _DEFAULTS.model_id,
        temperature: float | None = _DEFAULTS.temperature,
        max_tokens: int = _DEFAULTS.max_tokens,
        llm: Any = None,
    ) -> None:
        self.llm = llm or Llm(model_id, temperature=temperature, max_tokens=max_tokens)

    def decide(self, ctx: DecisionContext) -> TargetBook:
        _guard(ctx)
        memos, sources, abstained = _research(ctx, self.llm)
        ectx = ctx.pit.execution_context(list(ctx.universe))
        plan, notes = _plan_stage(self.llm, ctx, memos, ectx)
        prov = _research_provenance(memos, sources, abstained)
        prov["plan"] = plan.model_dump(mode="json")
        return TargetBook(
            decision_date=ctx.as_of,
            weights={p.ticker: p.target_weight for p in plan.plans},
            stop_pct={p.ticker: p.stop_pct for p in plan.plans},
            target_pct={p.ticker: p.target_pct for p in plan.plans if p.target_pct is not None},
            rationale=plan.summary,
            notes=list(notes),
            provenance=prov,
        )


@register_decider("synthesis_seed")
class SeedDecider:
    """Name ``synthesis_seed``. Param ``max_position`` (default `WfConfig.max_weight`); the seed
    function is lazily `backend.app.synthesis.strategy.seed_from_memos` unless ``seed_fn`` is injected."""

    name = "synthesis_seed"
    version = "1"
    stateless: ClassVar[bool] = True

    def __init__(
        self,
        max_position: float = _DEFAULTS.max_weight,
        model_id: str = _DEFAULTS.model_id,
        temperature: float | None = _DEFAULTS.temperature,
        max_tokens: int = _DEFAULTS.max_tokens,
        llm: Any = None,
        seed_fn: Callable[..., tuple[dict[str, float], Any]] | None = None,
    ) -> None:
        self.max_position = max_position
        self.llm = llm or Llm(model_id, temperature=temperature, max_tokens=max_tokens)
        self._seed_fn = seed_fn

    def decide(self, ctx: DecisionContext) -> TargetBook:
        _guard(ctx)
        seed_fn = self._seed_fn or load_attr(SEED_MODULE, SEED_FN)
        memos, sources, abstained = _research(ctx, self.llm)
        weights, detail = seed_fn(memos, list(ctx.universe), self.max_position)
        prov = _research_provenance(memos, sources, abstained)
        prov["seed"] = detail.model_dump(mode="json") if hasattr(detail, "model_dump") else detail
        return TargetBook(
            decision_date=ctx.as_of,
            weights={t: float(w) for t, w in weights.items()},
            rationale="deterministic conviction seed from analyst memos",
            provenance=prov,
        )


@register_decider("frozen_weights")
class FrozenWeightsDecider:
    """Name ``frozen_weights``. Params: ``weights`` {ticker: w}, optional ``dates``. With ``dates``
    set, any other decision date raises (a frozen book has no opinion off-schedule)."""

    name = "frozen_weights"
    version = "1"
    stateless: ClassVar[bool] = True

    def __init__(self, weights: Mapping[str, float], dates: Sequence[str] | None = None) -> None:
        self.weights = {str(t): float(w) for t, w in weights.items()}
        self.dates = None if dates is None else frozenset(dates)

    def decide(self, ctx: DecisionContext) -> TargetBook:
        if self.dates is not None and ctx.as_of not in self.dates:
            raise ValueError(f"{ctx.as_of} is not one of the frozen dates")
        unknown = sorted(set(self.weights) - set(ctx.universe))
        if unknown:
            raise ValueError(f"frozen weights outside the universe: {unknown}")
        return TargetBook(decision_date=ctx.as_of, weights=dict(self.weights), rationale="frozen weights")


@register_decider("equal_weight")
class EqualWeightDecider:
    """Name ``equal_weight``: 1/N over the universe, no stops."""

    name = "equal_weight"
    version = "1"
    stateless: ClassVar[bool] = True

    def decide(self, ctx: DecisionContext) -> TargetBook:
        n = len(ctx.universe)
        return TargetBook(
            decision_date=ctx.as_of, weights={t: 1.0 / n for t in ctx.universe}, rationale="equal weight"
        )
