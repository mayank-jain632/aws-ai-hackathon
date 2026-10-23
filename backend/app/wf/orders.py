"""Pure conversion of stage outputs into engine orders. No LLM, no I/O."""

from __future__ import annotations

from collections.abc import Sequence

from backend.app.wf.config import WfConfig
from backend.app.wf.schemas import (
    DecisionOrders,
    ExecutionPlan,
    OrderDraft,
    OrderIntent,
    TradePlan,
)

PRICE_DP = 4


def _px(x: float) -> float:
    return round(x, PRICE_DP)


def _exit(ticker: str) -> OrderIntent:
    return OrderIntent(ticker=ticker, target_weight=0.0, entry="market_open")


def _limit_price(draft: OrderDraft, close: float, atr: float | None) -> float | None:
    if draft.entry != "limit":
        return None
    offset = (draft.limit_offset_atr or 0.0) * (atr or 0.0)
    return _px(close - offset)


def _intent(plan_item, draft: OrderDraft, ctx: dict) -> OrderIntent:
    close = ctx.get("last_close")
    if draft.entry == "skip":
        return OrderIntent(
            ticker=plan_item.ticker, target_weight=plan_item.target_weight, entry="skip"
        )
    if close is None:
        # no price context: cannot derive protective prices, trade at the open without them
        return OrderIntent(
            ticker=plan_item.ticker,
            target_weight=plan_item.target_weight,
            entry="market_open",
            skip_if_gap_pct=draft.skip_if_gap_pct,
        )
    return OrderIntent(
        ticker=plan_item.ticker,
        target_weight=plan_item.target_weight,
        entry=draft.entry,
        limit_price=_limit_price(draft, close, ctx.get("atr14")),
        skip_if_gap_pct=draft.skip_if_gap_pct,
        stop_price=_px(close * (1 - plan_item.stop_pct)),
        target_price=_px(close * (1 + plan_item.target_pct))
        if plan_item.target_pct
        else None,
    )


def to_decision_orders(
    as_of: str,
    plan: TradePlan,
    exec_plan: ExecutionPlan,
    exec_context: dict[str, dict],
    cfg: WfConfig,
    contaminated: bool,
    universe: Sequence[str] | None = None,
) -> DecisionOrders:
    drafts = {d.ticker: d for d in exec_plan.orders}
    intents: list[OrderIntent] = []
    planned: set[str] = set()
    for p in plan.plans:
        planned.add(p.ticker)
        draft = drafts.get(p.ticker, OrderDraft(ticker=p.ticker))
        intents.append(_intent(p, draft, exec_context.get(p.ticker, {})))
    intents.extend(_exit(t) for t in (universe or cfg.universe) if t not in planned)
    return DecisionOrders(date=as_of, intents=intents, contaminated=contaminated)


def weights_only_orders(
    as_of: str,
    plan: TradePlan,
    cfg: WfConfig,
    contaminated: bool = False,
    universe: Sequence[str] | None = None,
) -> DecisionOrders:
    """Naive executor for ablations: market_open everything, no stops, no targets."""
    intents = [
        OrderIntent(ticker=p.ticker, target_weight=p.target_weight, entry="market_open")
        for p in plan.plans
    ]
    planned = {p.ticker for p in plan.plans}
    intents.extend(_exit(t) for t in (universe or cfg.universe) if t not in planned)
    return DecisionOrders(date=as_of, intents=intents, contaminated=contaminated)
