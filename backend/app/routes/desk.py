"""Role-protected tools plus human-only policy, approval and stop controls."""

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from backend.app.desk import (
    OrderInput,
    Policy,
    ReviewInput,
    StrategyInput,
    StrictModel,
    desk_for,
    digest,
)
from backend.app.paper import account_snapshot, order_status, submit
from backend.app.roles import PROFILES, require_tool, role_of

router = APIRouter(tags=["agent roles and desk"])


def current_manager(request, fund_id=None):
    from backend.app.main import manager

    if fund_id:
        try:
            return request.app.state.funds.runtime(fund_id)
        except (AttributeError, KeyError):
            raise HTTPException(404, "Fund not found") from None
    return manager(request)


def human(request):
    if request.headers.get("x-agent-token"):
        raise HTTPException(403, "Workers cannot change human policy or approvals")


def worker(request, capability):
    from backend.app.main import authenticate_worker

    agent = authenticate_worker(request)
    try:
        require_tool(agent, capability)
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    return agent, desk_for(agent.manager)


@router.get("/api/agent-roles")
def roles() -> dict:
    return {"roles": PROFILES, "max_agents": 16, "max_active_runs": 4}


@router.get("/api/desk")
@router.get("/api/funds/{fund_id}/desk")
def inspect_human(request: Request, fund_id: str | None = None) -> dict:
    human(request)
    return desk_for(current_manager(request, fund_id)).state


@router.put("/api/desk/policy")
@router.put("/api/funds/{fund_id}/desk/policy")
def set_policy(body: Policy, request: Request, fund_id: str | None = None) -> dict:
    human(request)
    desk = desk_for(current_manager(request, fund_id))
    desk.set_policy(body)
    return {"policy": desk.state["policy"], "stop": desk.state["stop"]}


class StopInput(StrictModel):
    stopped: bool
    reason: str = Field(min_length=1, max_length=1000)


@router.put("/api/desk/stop")
@router.put("/api/funds/{fund_id}/desk/stop")
def human_stop(body: StopInput, request: Request, fund_id: str | None = None) -> dict:
    human(request)
    desk = desk_for(current_manager(request, fund_id))
    with desk.lock:
        desk.state["stop"] = body.stopped
        desk.event("human_stop", body.model_dump())
    return {"stopped": body.stopped}


@router.post("/api/desk/strategies/{strategy_id}/approve")
@router.post("/api/funds/{fund_id}/desk/strategies/{strategy_id}/approve")
def approve(strategy_id: str, request: Request, fund_id: str | None = None) -> dict:
    human(request)
    desk = desk_for(current_manager(request, fund_id))
    with desk.lock:
        try:
            desk.strategy(strategy_id)
        except ValueError as error:
            raise HTTPException(404, str(error)) from error
        desk.state["approvals"][strategy_id] = digest(desk.policy().model_dump())
        desk.event("human_approval", strategy_id)
    return {"approved": strategy_id}


@router.get("/api/internal/desk/inspect")
def inspect_worker(request: Request) -> dict:
    _, desk = worker(request, "inspect_desk")
    return desk.state


@router.post("/api/internal/desk/strategy")
def register_strategy(body: StrategyInput, request: Request) -> dict:
    agent, desk = worker(request, "register_strategy")
    try:
        return desk.register(body, agent.id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/api/internal/desk/review")
def review_strategy(body: ReviewInput, request: Request) -> dict:
    agent, desk = worker(request, "review_strategy")
    try:
        return desk.review(body, agent.id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


class StrategyId(StrictModel):
    strategy_id: str


@router.post("/api/internal/desk/backtest")
def run_backtest(body: StrategyId, request: Request) -> dict:
    agent, desk = worker(request, "run_backtest")
    if (
        role_of(agent) != "orchestrator"
        and agent.state.get("strategy_id") != body.strategy_id
    ):
        raise HTTPException(403, "Evaluator is bound to a different strategy")
    try:
        return desk.evaluate(body.strategy_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/api/internal/desk/account")
def paper_account(request: Request) -> dict:
    worker(request, "alpaca_paper_account")
    try:
        return account_snapshot()
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(502, "Alpaca paper account request failed") from error


@router.get("/api/internal/desk/orders/{client_order_id}")
def paper_order_status(client_order_id: str, request: Request) -> dict:
    _, desk = worker(request, "alpaca_paper_order")
    try:
        return order_status(desk, client_order_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            502, "Alpaca paper order status request failed; do not resubmit"
        ) from error


@router.post("/api/internal/desk/order")
def paper_order(body: OrderInput, request: Request) -> dict:
    agent, desk = worker(request, "submit_paper_order")
    try:
        if role_of(agent) not in {"executor", "orchestrator"}:
            raise ValueError("Only paper executors or orchestrators can submit orders")
        return submit(desk, body)
    except ValueError as error:
        with desk.lock:
            desk.event(
                "paper_order_blocked",
                {
                    "agent": agent.id,
                    "strategy_id": body.strategy_id,
                    "reason": str(error),
                },
            )
        raise HTTPException(422, str(error)) from error


class StopReason(StrictModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/api/internal/desk/stop")
def worker_stop(body: StopReason, request: Request) -> dict:
    agent, desk = worker(request, "emergency_stop")
    with desk.lock:
        desk.state["stop"] = True
        desk.event("moderator_stop", {"agent": agent.id, **body.model_dump()})
    return {"stopped": True, "reason": body.reason}
