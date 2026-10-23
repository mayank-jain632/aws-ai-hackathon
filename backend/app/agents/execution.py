"""Stage 3 (walk-forward backtest): HOW to enter each planned name. Stateless.

The model picks entry style, limit offset in ATRs and a gap-skip threshold per ticker. It
never chooses quantities, weights, stops or targets. `validate_execution` clamps ranges
and defaults any omitted planned ticker to market_open.
"""

from __future__ import annotations

import logging

from backend.app.wf.config import WfConfig
from backend.app.wf.schemas import ExecutionPlan, OrderDraft, TradePlan

log = logging.getLogger("wf.execution")

DEFAULT_LIMIT_ATR = 0.5
MAX_LIMIT_ATR = 3.0
MAX_GAP = 0.2

SYSTEM = """You are the EXECUTION TRADER on a small desk. A trade plan has been set; you decide only
HOW to enter each planned ticker next session. You do not choose quantities, weights, stops
or targets. All data is dated on or before the decision date; use only it, no hindsight.
Per ticker choose:
- entry: "market_open" (trade at the next open), "limit" (buy only at or below a limit set
  limit_offset_atr ATRs under the decision close, 0..3), or "skip" (do not trade this week).
- skip_if_gap_pct: cancel the entry if the next open is more than this fraction above the
  decision close (0..0.2), e.g. 0.03. Use null for no gap rule.
- note: one short line of reasoning.
Use limit entries for extended or volatile names (large recent move, high ATR relative to
price); market_open for names you want filled; skip only if execution risk clearly outweighs
the plan. Include every planned ticker exactly once. decision_date must equal the decision date."""


def _context_text(plan: TradePlan, ctx: dict[str, dict]) -> str:
    lines = []
    for p in plan.plans:
        c = ctx.get(p.ticker, {})
        lines.append(
            f"  {p.ticker}: target_weight {p.target_weight:.3f}, last close {c.get('last_close')}, "
            f"ATR14 {c.get('atr14')}, avg volume20 {c.get('avg_volume20')}, "
            f"avg gap {c.get('avg_gap_pct')}, 1w return {c.get('ret_1w')}"
        )
    return "\n".join(lines)


def build_prompt(as_of: str, plan: TradePlan, ctx: dict[str, dict]) -> str:
    return (
        f"Decision date: {as_of} (after the close). Orders go live at the next open.\n"
        f"Plan summary: {plan.summary}\n\nPlanned positions and execution context:\n"
        f"{_context_text(plan, ctx)}\n\nReturn the execution plan."
    )


def validate_execution(
    ep: ExecutionPlan, plan: TradePlan, as_of: str
) -> tuple[ExecutionPlan, list[str]]:
    """Pure. Keeps one draft per planned ticker, clamps ranges, defaults omissions to market_open."""
    notes: list[str] = []
    planned = [p.ticker for p in plan.plans]
    by_ticker: dict[str, OrderDraft] = {}
    for d in ep.orders:
        if d.ticker not in planned:
            notes.append(f"dropped execution draft for unplanned {d.ticker}")
        elif d.ticker not in by_ticker:
            by_ticker[d.ticker] = _clamp(d)
    out: list[OrderDraft] = []
    for t in planned:
        if t in by_ticker:
            out.append(by_ticker[t])
        else:
            notes.append(f"defaulted {t} to market_open")
            out.append(
                OrderDraft(
                    ticker=t, entry="market_open", note="default: omitted by model"
                )
            )
    return ExecutionPlan(decision_date=as_of, orders=out, notes=ep.notes), notes


def _clamp(d: OrderDraft) -> OrderDraft:
    offset = d.limit_offset_atr
    if d.entry == "limit":
        offset = (
            DEFAULT_LIMIT_ATR
            if offset is None
            else min(max(offset, 0.0), MAX_LIMIT_ATR)
        )
    else:
        offset = None
    gap = (
        None if d.skip_if_gap_pct is None else min(max(d.skip_if_gap_pct, 0.0), MAX_GAP)
    )
    return d.model_copy(update={"limit_offset_atr": offset, "skip_if_gap_pct": gap})


def run(
    llm, cfg: WfConfig, as_of: str, plan: TradePlan, exec_context: dict[str, dict]
) -> ExecutionPlan:
    if not plan.plans:
        return ExecutionPlan(decision_date=as_of, orders=[], notes="empty plan")
    raw = llm.structured(SYSTEM, build_prompt(as_of, plan, exec_context), ExecutionPlan)
    clean, notes = validate_execution(raw, plan, as_of)
    for n in notes:
        log.info("%s execution: %s", as_of, n)
    return clean
