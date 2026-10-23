"""One hashed run specification: everything that affects a result (hub D22)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.app.wf.config import WfConfig
from backend.app.wf.interfaces import ComponentSpec

Label = Literal["model-clean", "contaminated", "unknown-cutoff"]
DEFAULT_BASELINES = (
    "equal_weight_buy_hold",
    "equal_weight_weekly",
    "spy_buy_hold",
    "momentum_12_1_top5",
    "mechanical_seed",  # needs analyst memos in TargetBook.provenance["memos"]; skipped without
)
EXCLUDED_FROM_HASH = {"name", "notes"}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class WindowSpec(_Frozen):
    first_decision: str
    last_decision: str
    mark_end: str
    dev_decisions: int = 8


class EngineSpec(_Frozen):
    start_cash: float = 1_000_000.0
    slippage_bps: float = 5.0
    volume_participation_cap: float = 0.05
    rebalance_band: float = 0.01


class LimitsSpec(_Frozen):
    """Validator limits components may read from ``ctx.cfg``."""

    max_weight: float = 0.25
    min_stop_pct: float = 0.02
    max_stop_pct: float = 0.20
    min_target_pct: float = 0.03
    max_tokens: int = 4000


class RunSpec(_Frozen):
    name: str
    window: WindowSpec
    universe: tuple[str, ...]
    reference: str = "SPY"
    decider: ComponentSpec
    execution: ComponentSpec
    evaluator: ComponentSpec | None = None
    baselines: tuple[str, ...] = DEFAULT_BASELINES
    engine: EngineSpec = Field(default_factory=EngineSpec)
    limits: LimitsSpec = Field(default_factory=LimitsSpec)
    model_id: str | None = None
    model_training_cutoff: str | None = None  # model that AUTHORS the weights; "YYYY-MM" or date
    temperature: float = 0.0
    seed: int = 0
    notes: str = ""

    def hashed_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude=EXCLUDED_FROM_HASH)

    def spec_hash(self) -> str:
        """sha256 of canonical JSON of everything that affects results (not name/notes)."""
        text = json.dumps(self.hashed_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode()).hexdigest()

    def to_wfconfig(self) -> WfConfig:
        """The WfConfig components see as ``ctx.cfg``."""
        w, e, lim = self.window, self.engine, self.limits
        return WfConfig(
            model_id=self.model_id or "unspecified",
            model_training_cutoff=self.model_training_cutoff or "unknown",
            clean_start=clean_start(self.model_training_cutoff) or "9999-12-31",
            first_decision=w.first_decision,
            last_decision=w.last_decision,
            mark_end=w.mark_end,
            dev_decisions=w.dev_decisions,
            universe=self.universe,
            reference=self.reference,
            temperature=self.temperature,
            **e.model_dump(),
            **lim.model_dump(),
        )


def clean_start(cutoff: str | None) -> str | None:
    """First decision date that is model-clean: one full month after the cutoff.

    "2025-08" (month precision, data through the end of August) -> "2025-10-01".
    "2025-08-15" (day precision) -> "2025-09-16". None/unparseable -> None.
    """
    if not cutoff:
        return None
    try:
        parts = cutoff.split("-")
        if len(parts) == 2:
            first = pd.Timestamp(f"{cutoff}-01") + pd.DateOffset(months=2)
            return first.strftime("%Y-%m-%d")
        day = pd.Timestamp(cutoff) + pd.DateOffset(months=1) + pd.Timedelta(days=1)
        return day.strftime("%Y-%m-%d")
    except ValueError:
        return None


def label_for(spec: RunSpec) -> Label:
    start = clean_start(spec.model_training_cutoff)
    if start is None:
        return "unknown-cutoff"
    return "model-clean" if spec.window.first_decision >= start else "contaminated"


def _component(ref: str | ComponentSpec, params: dict | None) -> ComponentSpec:
    return ref if isinstance(ref, ComponentSpec) else ComponentSpec(ref=ref, params=params or {})


def from_wfconfig(
    cfg: WfConfig,
    *,
    decider_ref: str | ComponentSpec,
    execution_ref: str | ComponentSpec,
    name: str = "frozen",
    decider_params: dict | None = None,
    execution_params: dict | None = None,
    evaluator: ComponentSpec | None = None,
    baselines: tuple[str, ...] = DEFAULT_BASELINES,
    notes: str = "",
) -> RunSpec:
    """The spec equivalent to an experiment defined by ``WfConfig`` (e.g. the frozen run)."""
    return RunSpec(
        name=name,
        window=WindowSpec(
            first_decision=cfg.first_decision,
            last_decision=cfg.last_decision,
            mark_end=cfg.mark_end,
            dev_decisions=cfg.dev_decisions,
        ),
        universe=cfg.universe,
        reference=cfg.reference,
        decider=_component(decider_ref, decider_params),
        execution=_component(execution_ref, execution_params),
        evaluator=evaluator,
        baselines=baselines,
        engine=EngineSpec(
            start_cash=cfg.start_cash,
            slippage_bps=cfg.slippage_bps,
            volume_participation_cap=cfg.volume_participation_cap,
            rebalance_band=cfg.rebalance_band,
        ),
        limits=LimitsSpec(
            max_weight=cfg.max_weight,
            min_stop_pct=cfg.min_stop_pct,
            max_stop_pct=cfg.max_stop_pct,
            min_target_pct=cfg.min_target_pct,
            max_tokens=cfg.max_tokens,
        ),
        model_id=cfg.model_id,
        model_training_cutoff=cfg.model_training_cutoff,
        temperature=cfg.temperature,
        notes=notes,
    )
