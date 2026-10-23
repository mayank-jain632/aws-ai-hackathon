"""Read-only scores and reasoning for one fund desk (D23). Writes nothing."""

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.desk import desk_for
from backend.app.routes.desk import current_manager, human
from backend.app.scores import build_scorecard

router = APIRouter(tags=["scores"])


@router.get("/api/funds/{fund_id}/scores")
def fund_scores(
    fund_id: str,
    request: Request,
    strategy_id: str | None = Query(default=None, max_length=64),
) -> dict:
    human(request)
    manager = current_manager(request, fund_id)
    if strategy_id and strategy_id not in desk_for(manager).state["strategies"]:
        raise HTTPException(404, "Unknown strategy_id in this fund")
    fund = request.app.state.funds.records[fund_id]
    return build_scorecard(fund_id, fund, manager, strategy_id).model_dump()
