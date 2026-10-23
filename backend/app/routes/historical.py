"""Fund-authenticated historical replay tools; no brokerage operations."""
import json

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from backend.app.desk import StrictModel, desk_for
from backend.app.roles import role_of
from backend.app.routes.desk import current_manager, human, worker

router = APIRouter(tags=["historical execution"])


def replay(desk):
    from backend.app.historical_execution import HistoricalReplay
    return HistoricalReplay(desk)


def historical_desk(request, tool, *, mutate=False, strategy_id=None):
    agent, desk = worker(request, tool)
    mandate = json.loads(agent.manager.context or "{}").get("mandate", {})
    if mandate.get("mode") != "historical":
        raise HTTPException(422, "Historical replay requires a historical fund; never changes its mode")
    if role_of(agent) not in {"orchestrator", "executor"}:
        raise HTTPException(403, "Only historical executors or orchestrators may run this simulation")
    if mutate:
        if strategy_id is None:
            if not replay(desk).path.exists():
                raise HTTPException(422, "No historical replay has been started in this fund")
            strategy_id = json.loads(replay(desk).path.read_text())["strategy_id"]
        if desk.state["stop"] or agent.manager.paused:
            raise HTTPException(422, "Historical simulation stop or fund pause is active")
        try:
            policy = desk.policy()
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        if not mandate.get("trading_allowed") or not policy.trading_allowed:
            raise HTTPException(422, "Saved mandate does not allow simulated trading")
        if strategy_id:
            try:
                desk.require_final_review(strategy_id)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            if (policy.approval_required or mandate.get("approval_required", True)) and not desk.human_approved(strategy_id):
                raise HTTPException(422, "Saved mandate requires strategy approval")
    return desk


def call(action):
    try:
        return action()
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(422, str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(502, "Historical data unavailable; no live fallback") from error


class StartInput(StrictModel):
    strategy_id: str = Field(min_length=1)
    evaluation_id: str = Field(min_length=1)


class ReplayInput(StrictModel):
    replay_id: str = Field(min_length=1)


class AdvanceInput(ReplayInput):
    clock: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class HistoricalOrder(AdvanceInput):
    symbol: str = Field(min_length=1)
    side: str = Field(pattern=r"^(buy|sell)$")
    notional: float = Field(gt=0, allow_inf_nan=False)
    client_order_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,48}$")


@router.get("/api/funds/{fund_id}/historical/replays")
def read_replays(fund_id: str, request: Request) -> dict:
    human(request)
    current = call(lambda: replay(desk_for(current_manager(request, fund_id))).current())
    return {"replays": [current] if current else []}


@router.post("/api/internal/historical/start")
def start(body: StartInput, request: Request) -> dict:
    desk = historical_desk(request, "start_historical_replay", mutate=True, strategy_id=body.strategy_id)
    return call(lambda: replay(desk).start(body.strategy_id, body.evaluation_id))


@router.post("/api/internal/historical/inspect")
def inspect(body: ReplayInput, request: Request) -> dict:
    desk = historical_desk(request, "inspect_historical_replay")
    return call(lambda: replay(desk).inspect(body.replay_id))


@router.post("/api/internal/historical/order")
def place_order(body: HistoricalOrder, request: Request) -> dict:
    desk = historical_desk(request, "place_order", mutate=True)
    return call(lambda: replay(desk).place_order(**body.model_dump()))


@router.post("/api/internal/historical/advance")
def advance(body: AdvanceInput, request: Request) -> dict:
    desk = historical_desk(request, "advance_historical_replay", mutate=True)
    return call(lambda: replay(desk).advance(**body.model_dump()))
