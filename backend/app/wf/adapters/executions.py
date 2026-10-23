"""Execution policies: `TargetBook` + holdings -> `DecisionOrders` (hub D22).

TargetWeightExecution     deterministic baseline, long-only market-at-next-open to the book's weights
LlmExecutionPolicy        the frozen-run LLM execution stage (limits, gap skips) behind the contract
SynthesisPlannerExecution lane 4's deterministic order planner (`plan_orders`), replayed through the engine

How Alpaca "market / day / notional" orders map to our fills (SynthesisPlannerExecution)
---------------------------------------------------------------------------------------
The planner emits dollar-notional market/day orders sized from the account snapshot. Here each
order becomes an `OrderIntent` whose target weight is (current value +/- notional) / equity,
entry ``market_open``: the engine fills it at the NEXT session's open plus slippage, sells before
buys, with the engine's volume cap. Where they differ:
  * Alpaca submits during the live session; a replay fills at the next open, so the fill price is
    the open, not the decision close the notional was sized on (a small drift in shares bought).
  * Notional orders on Alpaca buy fractional shares (as the engine does) but only for fractionable
    symbols; the replay assumes all are.
  * The planner limits buys to CASH ON HAND (sell proceeds are not assumed settled), so a rebalance
    that needs sale proceeds is trimmed to the cash available. The engine itself would reuse sale
    proceeds, but the intents carry the planner's (already trimmed) sizes, so the replay follows the planner.
  * A day order that does not fill is lost on Alpaca; the engine expires unfilled entries at the
    next decision. A volume-capped remainder lapses (no overnight partial fill carry-over).
  * Protective stops are not part of the planner: no stop/target prices are set (the engine keeps
    stops from earlier decisions only for names this decision does not mention).
  * A blocked or not-ready plan trades nothing: empty intents plus ``blocked`` reasons.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from backend.app.agents import execution
from backend.app.wf import orders, pipeline
from backend.app.wf.adapters.lazy import load_attr
from backend.app.wf.config import WfConfig
from backend.app.wf.interfaces import DecisionContext, TargetBook
from backend.app.wf.llm import Llm
from backend.app.wf.registry import register_execution
from backend.app.wf.schemas import DecisionOrders, OrderIntent, TickerPlan, TradePlan

log = logging.getLogger("wf.adapters.executions")
_DEFAULTS = WfConfig()
PX_DP = 4
PLANNER_MODULE, PLANNER_FN = "backend.app.synthesis.orders", "plan_orders"
POLICY_MODULE, POLICY_CLS = "backend.app.desk", "Policy"
# Policy defaults used when the planner adapter builds `desk.Policy` itself: no extra caps beyond
# the book (the strategy already clamps weights), trading allowed, no approval step in a replay.
POLICY_DEFAULTS: dict[str, Any] = {
    "max_position": 1.0,
    "max_drawdown": 1.0,
    "min_sharpe": -100.0,
    "min_excess_return": -1.0,
    "max_order_notional": 1e12,
    "max_daily_orders": 100,
    "trading_allowed": True,
    "approval_required": False,
}


def _px(x: float) -> float:
    return round(x, PX_DP)


def _check_universe(book: TargetBook, universe) -> None:
    unknown = sorted(set(book.weights) - set(universe))
    if unknown:
        raise ValueError(f"book has tickers outside the universe: {unknown}")


@register_execution("target_weight_execution")
class TargetWeightExecution:
    """Market orders at the next open to the book's weights; universe names absent from the book
    go to 0. ``use_stops=True`` adds stop/target prices = decision close x (1 -/+ pct) from the book."""

    name = "target_weight_execution"
    version = "1"

    def __init__(self, use_stops: bool = False) -> None:
        self.use_stops = bool(use_stops)

    def _intent(self, ctx: DecisionContext, book: TargetBook, ticker: str) -> OrderIntent:
        weight = book.weights.get(ticker, 0.0)
        stop = book.stop_pct.get(ticker) if self.use_stops and weight > 0 else None
        if stop is None:
            return OrderIntent(ticker=ticker, target_weight=weight, entry="market_open")
        close = ctx.pit.last_close(ticker)
        tgt = book.target_pct.get(ticker)
        return OrderIntent(
            ticker=ticker,
            target_weight=weight,
            entry="market_open",
            stop_price=_px(close * (1 - stop)),
            target_price=_px(close * (1 + tgt)) if tgt else None,
        )

    def plan(self, ctx: DecisionContext, book: TargetBook) -> DecisionOrders:
        _check_universe(book, ctx.universe)
        intents = [self._intent(ctx, book, t) for t in ctx.universe]
        return DecisionOrders(date=ctx.as_of, intents=intents, contaminated=ctx.contaminated)


def _book_to_plan(ctx: DecisionContext, book: TargetBook) -> TradePlan:
    """The strategy's own `TradePlan` when the book carries it, else one rebuilt from the book
    (stops default to ``cfg.max_stop_pct``, the loosest allowed)."""
    stored = book.provenance.get("plan")
    if stored:
        return TradePlan.model_validate(stored)
    plans = [
        TickerPlan(
            ticker=t,
            target_weight=w,
            stop_pct=book.stop_pct.get(t, ctx.cfg.max_stop_pct),
            target_pct=book.target_pct.get(t),
            rationale="from target book",
            changes_my_mind="n/a",
        )
        for t, w in sorted(book.weights.items())
        if w > 0
    ]
    return TradePlan(decision_date=ctx.as_of, strategy_name=book.rationale[:60] or "book", summary=book.rationale, plans=plans)


@register_execution("llm_execution")
class LlmExecutionPolicy:
    """Wraps `agents.execution.run` + `orders.to_decision_orders` (same prompts and cache keys as
    the frozen run). Params: model_id, temperature, max_tokens, or a ready ``llm``."""

    name = "llm_execution"
    version = "1"

    def __init__(
        self,
        model_id: str = _DEFAULTS.model_id,
        temperature: float | None = _DEFAULTS.temperature,
        max_tokens: int = _DEFAULTS.max_tokens,
        llm: Any = None,
    ) -> None:
        self.llm = llm or Llm(model_id, temperature=temperature, max_tokens=max_tokens)

    def _exec_plan(self, ctx: DecisionContext, plan: TradePlan, ectx: dict):
        if ctx.masker is None:
            return execution.run(self.llm, ctx.cfg, ctx.as_of, plan, ectx)
        to_code, to_ticker = pipeline._code_maps(ctx.masker, ctx.universe)
        mctx = {to_code[t]: c for t, c in ectx.items() if t in to_code}
        mexec = execution.run(self.llm, ctx.cfg, ctx.as_of, pipeline._unmask_plan(plan, to_code), mctx)
        return pipeline._unmask_exec(mexec, to_ticker)

    def plan(self, ctx: DecisionContext, book: TargetBook) -> DecisionOrders:
        _check_universe(book, ctx.universe)
        trade_plan = _book_to_plan(ctx, book)
        ectx = ctx.pit.execution_context(list(ctx.universe))
        exec_plan = self._exec_plan(ctx, trade_plan, ectx)
        return orders.to_decision_orders(
            ctx.as_of, trade_plan, exec_plan, ectx, ctx.cfg, ctx.contaminated, ctx.universe
        )


@register_execution("synthesis_planner")
class SynthesisPlannerExecution:
    """Lane 4's `plan_orders` as an execution policy. See the module docstring for the Alpaca mapping.

    Params: ``strategy_id`` ("wf"), ``run_tag`` ("wf"; the date is appended per decision),
    ``mandate`` (None = capital is equity, no extra limits; else the planner's keys capital,
    max_position percent, max_sector, min_cash, exclusions, rebalance), ``policy`` (a ready
    `desk.Policy`; default built from `POLICY_DEFAULTS` over the context universe, overridable via
    ``policy_params``), ``planner`` (injectable; default lazily imported `plan_orders`).
    """

    name = "synthesis_planner"
    version = "1"

    def __init__(
        self,
        strategy_id: str = "wf",
        run_tag: str = "wf",
        mandate: dict | None = None,
        policy: Any = None,
        policy_params: dict | None = None,
        planner: Callable[..., Any] | None = None,
    ) -> None:
        self.strategy_id, self.run_tag, self.mandate = strategy_id, run_tag, mandate
        self._policy, self._planner = policy, planner
        self.policy_params = {**POLICY_DEFAULTS, **(policy_params or {})}

    def _make_policy(self, ctx: DecisionContext) -> Any:
        if self._policy is not None:
            return self._policy
        cls = load_attr(POLICY_MODULE, POLICY_CLS)
        return cls(universe=list(ctx.universe), **self.policy_params)

    @staticmethod
    def _blocked(ctx: DecisionContext, reasons: list[str]) -> DecisionOrders:
        return DecisionOrders(
            date=ctx.as_of, intents=[], contaminated=ctx.contaminated, blocked=reasons or ["plan not ready"]
        )

    def plan(self, ctx: DecisionContext, book: TargetBook) -> DecisionOrders:
        _check_universe(book, ctx.universe)
        planner = self._planner or load_attr(PLANNER_MODULE, PLANNER_FN)
        result = planner(
            self.strategy_id,
            dict(book.weights),
            ctx.portfolio.as_broker_snapshot(),
            self._make_policy(ctx),
            self.mandate,
            f"{self.run_tag}-{ctx.as_of}",
        )
        if result.blocked or not result.ready or ctx.portfolio.equity <= 0:
            return self._blocked(ctx, list(result.blocked))
        for sym, why in dict(result.skipped).items():
            log.info("%s planner skipped %s: %s", ctx.as_of, sym, why)
        intents = [self._intent(o, ctx.portfolio.equity) for o in result.orders]
        return DecisionOrders(date=ctx.as_of, intents=intents, contaminated=ctx.contaminated)

    @staticmethod
    def _intent(order: Any, equity: float) -> OrderIntent:
        sign = 1.0 if order.side == "buy" else -1.0
        weight = (order.current_value + sign * order.notional) / equity
        return OrderIntent(ticker=order.symbol, target_weight=min(max(weight, 0.0), 1.0), entry="market_open")
