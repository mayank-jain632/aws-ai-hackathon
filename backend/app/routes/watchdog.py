"""Watchdog routes: firm-wide stop, status, dry-run review, and agent-facing tools."""

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from backend.app.desk import StrictModel, desk_for
from backend.app.paper import account_snapshot
from backend.app.routes.desk import current_manager, human, worker
from backend.app.watchdog import SWITCH, feedback, gate, halt_reason, store
from backend.app.watchdog.models import WatchOrder, WatchPortfolio
from backend.app.watchdog.rules import review_order

router = APIRouter(tags=["watchdog"])


def status(desk) -> dict:
    return {
        "halt": SWITCH.state(),
        "halted_reason": halt_reason(desk),
        "feedback": feedback.entries(desk, 50),
        "events": store.read_jsonl(store.private_dir(desk) / feedback.EVENTS, 50),
        "lessons": feedback.lessons(desk),
    }


@router.get("/api/watchdog")
@router.get("/api/funds/{fund_id}/watchdog")
def watchdog_status(request: Request, fund_id: str | None = None) -> dict:
    human(request)
    return status(desk_for(current_manager(request, fund_id)))


class HaltInput(StrictModel):
    halted: bool
    reason: str = Field(min_length=1, max_length=1000)


@router.put("/api/watchdog/halt")
def set_halt(body: HaltInput, request: Request) -> dict:
    """Firm-wide stop across every fund. Workers cannot reach this route."""
    human(request)
    who = getattr(request.state, "user", "local person")
    if body.halted:
        return SWITCH.trip(body.reason, who)
    return SWITCH.reset(body.reason, who)


class ReviewInput(StrictModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    notional: float
    strategy_id: str | None = None
    qty: float | None = None
    price: float | None = None
    portfolio: WatchPortfolio | None = None


@router.post("/api/watchdog/review")
@router.post("/api/funds/{fund_id}/watchdog/review")
def dry_run(body: ReviewInput, request: Request, fund_id: str | None = None) -> dict:
    """Review a proposed order against the fund's mandate without sending anything."""
    human(request)
    desk = desk_for(current_manager(request, fund_id))
    try:
        policy = desk.policy()
        if body.portfolio is not None:
            portfolio = body.portfolio
            if body.strategy_id and portfolio.backtest_verdict is None:
                test = desk.state["tests"].get(body.strategy_id, {})
                portfolio = portfolio.model_copy(update={"backtest_verdict": test.get("verdict")})
        else:
            portfolio = gate.portfolio_for(desk, body.strategy_id, account_snapshot())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(502, "Alpaca paper account request failed") from error
    order = WatchOrder(**body.model_dump(exclude={"portfolio"}), client_order_id="dry-run")
    verdict = review_order(order, gate.mandate_for(desk, policy), portfolio, halt=halt_reason(desk))
    return verdict.model_dump()


@router.get("/api/internal/watchdog/lessons")
def lessons_for_agent(request: Request) -> dict:
    _, desk = worker(request, "watchdog_lessons")
    return {"lessons": feedback.lessons(desk), "halted_reason": halt_reason(desk)}
