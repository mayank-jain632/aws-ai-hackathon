"""Stage 2 (walk-forward backtest): memos -> TradePlan. Stateless, long-only, strict.

`run(llm, cfg, as_of, memos, universe, closes_context) -> TradePlan`. The model proposes;
`validate_plan` is a deterministic pure function that clamps and records soft violations.
"""

from __future__ import annotations

import logging

from backend.app.agents.pm import seed_scores, seed_weights
from backend.app.schema import Memo
from backend.app.wf.config import WfConfig
from backend.app.wf.schemas import TickerPlan, TradePlan

log = logging.getLogger("wf.strategy")

SYSTEM = """You are the PORTFOLIO STRATEGIST of a small research desk. Five analysts have sent
dated notes. Build one long-only plan over the given universe for the coming week.
- Use ONLY the memos and the price context provided. Everything is dated on or before the
  decision date. Never use anything after the decision date and no hindsight.
- Long-only. Each target_weight is between 0 and {max_weight}; the weights sum to at most 1,
  the remainder is cash. Omit tickers you do not want to hold.
- Prefer positions where analysts agree; size down where they conflict. Abstaining analysts
  (confidence 0) carry no information.
- For each position: a one or two sentence rationale citing which analysts drove it,
  memo_sources (source ids taken from the memos' views), a concrete checkable
  changes_my_mind trigger, stop_pct (stop distance below the decision close, between
  {min_stop} and {max_stop}), optional target_pct (profit target above the close, at least
  {min_target}), horizon_weeks, and conviction 0..1.
- strategy_name: a short label. summary: two sentences on the overall stance.
- decision_date must equal the decision date given.
- A mechanical seed built from analyst conviction is provided as a starting point; you may
  deviate from it."""


def build_system(cfg: WfConfig) -> str:
    return SYSTEM.format(
        max_weight=cfg.max_weight,
        min_stop=cfg.min_stop_pct,
        max_stop=cfg.max_stop_pct,
        min_target=cfg.min_target_pct,
    )


def _memo_text(m: Memo) -> str:
    views = "\n".join(
        f"  {v.ticker}: {v.stance} ({v.confidence:.2f}) {v.note} [{', '.join(v.sources)}]"
        for v in m.views
    )
    return f"=== {m.analyst.upper()} note, {m.date}\n{m.headline}\n{m.body}\n{views}"


def _closes_text(closes_context: dict[str, dict]) -> str:
    lines = []
    for t, c in sorted(closes_context.items()):
        lines.append(
            f"  {t}: close {c.get('last_close')} on {c.get('last_date')}, 1w return {c.get('ret_1w')}, ATR14 {c.get('atr14')}"
        )
    return "\n".join(lines)


def build_prompt(
    as_of: str, memos: list[Memo], universe: list[str], closes_context: dict[str, dict]
) -> str:
    seed = seed_weights(seed_scores(memos, universe))
    return (
        f"Decision date: {as_of} (after the close). Universe: {', '.join(universe)}.\n\n"
        + "\n\n".join(_memo_text(m) for m in memos)
        + "\n\nLatest prices (as of the decision date):\n"
        + _closes_text(closes_context)
        + "\n\nMechanical seed weights (you may deviate):\n"
        + "\n".join(f"  {t}: {w:.3f}" for t, w in seed.items())
        + "\n\nReturn the trade plan."
    )


def validate_plan(
    plan: TradePlan, cfg: WfConfig, universe: list[str]
) -> tuple[TradePlan, list[str]]:
    """Pure. Returns (clean plan, soft-violation notes). Never raises on soft violations."""
    notes: list[str] = []
    seen: set[str] = set()
    kept: list[TickerPlan] = []
    for p in plan.plans:
        if p.ticker not in universe:
            notes.append(f"dropped unknown ticker {p.ticker}")
            continue
        if p.ticker in seen:
            notes.append(f"dropped duplicate ticker {p.ticker}")
            continue
        seen.add(p.ticker)
        weight = min(p.target_weight, cfg.max_weight)
        if weight < p.target_weight:
            notes.append(
                f"clamped {p.ticker} weight {p.target_weight:.4f} -> {weight:.4f}"
            )
        stop = min(max(p.stop_pct, cfg.min_stop_pct), cfg.max_stop_pct)
        if stop != p.stop_pct:
            notes.append(f"clamped {p.ticker} stop_pct {p.stop_pct} -> {stop}")
        target = (
            p.target_pct
            if p.target_pct is not None and p.target_pct >= cfg.min_target_pct
            else None
        )
        if p.target_pct is not None and target is None:
            notes.append(f"dropped {p.ticker} target_pct {p.target_pct} below minimum")
        kept.append(
            p.model_copy(
                update={"target_weight": weight, "stop_pct": stop, "target_pct": target}
            )
        )
    total = sum(p.target_weight for p in kept)
    if total > 1.0:
        notes.append(f"scaled weights from sum {total:.4f} to 1.0")
        kept = [
            p.model_copy(update={"target_weight": p.target_weight / total})
            for p in kept
        ]
    return plan.model_copy(update={"plans": kept}), notes


def run_with_notes(
    llm,
    cfg: WfConfig,
    as_of: str,
    memos: list[Memo],
    universe: list[str],
    closes_context: dict[str, dict],
) -> tuple[TradePlan, list[str]]:
    """Returns (validated plan, validation notes). Raises if the model fails (no fallback book)."""
    raw = llm.structured(
        build_system(cfg),
        build_prompt(as_of, memos, universe, closes_context),
        TradePlan,
    )
    raw = raw.model_copy(update={"decision_date": as_of})
    return validate_plan(raw, cfg, universe)


def run(
    llm,
    cfg: WfConfig,
    as_of: str,
    memos: list[Memo],
    universe: list[str],
    closes_context: dict[str, dict],
) -> TradePlan:
    plan, notes = run_with_notes(llm, cfg, as_of, memos, universe, closes_context)
    for n in notes:
        log.info("%s plan: %s", as_of, n)
    return plan
