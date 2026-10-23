"""Synthesis layer routes: research bundle -> frozen strategy, significance, order plan.

Worker routes reuse the desk's role checks (`strategy` role for synthesis, `executor`
role for order planning). Human routes reuse the desk's human boundary. Nothing here
approves, evaluates or submits; it feeds the existing gates.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.desk import StrictModel, desk_for
from backend.app.paper import account_snapshot
from backend.app.roles import role_of
from backend.app.routes.desk import current_manager, human, worker
from backend.app.synthesis import significance, strategy
from backend.app.synthesis.orders import plan_orders
from backend.app.synthesis.schema import (
    OrderPlan,
    Significance,
    SynthesisRequest,
    SynthesisResult,
)

router = APIRouter(tags=["synthesis"])


def _mandate(manager) -> dict | None:
    context = json.loads(getattr(manager, "context", "") or "{}")
    return context.get("mandate")


def _runs_path(desk) -> Path:
    return Path(desk.path).with_name("synthesis.json")


def _record(desk, kind: str, payload: dict) -> dict:
    """Append a run record beside desk.json. Links research -> strategy -> evaluation -> orders."""
    path = _runs_path(desk)
    runs = json.loads(path.read_text()) if path.exists() else []
    entry = {"id": uuid4().hex[:12], "time": datetime.now(UTC).isoformat(), "kind": kind, **payload}
    runs.append(entry)
    runs = runs[-200:]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(runs, indent=2))
    tmp.replace(path)
    return entry


# ------------------------------------------------------------------ worker: strategy role


@router.post("/api/internal/desk/synthesize")
def synthesize(body: SynthesisRequest, request: Request) -> dict:
    """Strategy role only. Builds and registers a frozen strategy from a research bundle."""
    agent, desk = worker(request, "register_strategy")
    try:
        policy = desk.policy()
        result: SynthesisResult = strategy.synthesize(
            body.name, body.bundle, policy, _mandate(agent.manager), use_model=body.use_model
        )
        from backend.app.desk import StrategyInput

        registered = desk.register(StrategyInput(**result.strategy), agent.id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    _record(
        desk,
        "synthesis",
        {
            "agent": agent.id,
            "strategy_id": registered["id"],
            "memos": [m.analyst for m in body.bundle.memos],
            "memo_paths": body.bundle.memo_paths,
            "seed": result.seed.model_dump(),
            "model_used": result.model_used,
            "model_note": result.model_note,
        },
    )
    return {
        "strategy": registered,
        "seed": result.seed.model_dump(),
        "model_used": result.model_used,
        "model_note": result.model_note,
        "next": "create an adversarial reviewer for this strategy_id; a backtester needs its APPROVE",
    }


# ------------------------------------------------------------------ worker: executor role


class PlanInput(StrictModel):
    strategy_id: str


@router.post("/api/internal/desk/plan-orders")
def plan_paper_orders(body: PlanInput, request: Request) -> dict:
    """Executor role only. Deterministic order list for a strategy that passed every gate."""
    agent, desk = worker(request, "submit_paper_order")
    if role_of(agent) != "executor":
        raise HTTPException(403, "Only paper executors can plan orders")
    try:
        policy, record = desk.execution_checks(body.strategy_id)
        snapshot = account_snapshot()
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(502, "Alpaca paper account request failed") from error
    plan: OrderPlan = plan_orders(
        body.strategy_id, record["weights"], snapshot, policy, _mandate(agent.manager), run_tag=uuid4().hex[:10]
    )
    _record(desk, "order_plan", {"agent": agent.id, **plan.model_dump()})
    return plan.model_dump()


# ------------------------------------------------------------------ human views


@router.get("/api/desk/strategies/{strategy_id}/significance")
@router.get("/api/funds/{fund_id}/desk/strategies/{strategy_id}/significance")
def strategy_significance(
    strategy_id: str,
    request: Request,
    fund_id: str | None = None,
    horizon_days: int = Query(significance.DEFAULT_HORIZON_DAYS, ge=30, le=730),
) -> dict:
    human(request)
    desk = desk_for(current_manager(request, fund_id))
    try:
        record = desk.strategy(strategy_id)
        result: Significance = significance.walk_forward(strategy_id, record["weights"], horizon_days=horizon_days)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    _record(desk, "significance", {"strategy_id": strategy_id, **{k: v for k, v in result.model_dump().items() if k != "windows"}})
    return result.model_dump()


@router.get("/api/desk/runs")
@router.get("/api/funds/{fund_id}/desk/runs")
def runs(request: Request, fund_id: str | None = None) -> dict:
    human(request)
    desk = desk_for(current_manager(request, fund_id))
    path = _runs_path(desk)
    return {"runs": json.loads(path.read_text()) if path.exists() else []}
