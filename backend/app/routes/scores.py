"""Read-only scores and reasoning for one fund desk (D23). Writes nothing.

Fund membership is enforced for every /api/funds/{fund_id}/... path by HostedAccess
(backend/app/access.py, sharing.can_access), the same gate as the other fund routes.
"""

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.desk import desk_for
from backend.app.routes.desk import human
from backend.app.routes.funds import fund, store
from backend.app.scores import build_scorecard

router = APIRouter(tags=["scores"])


@router.get("/api/funds/{fund_id}/scores")
def fund_scores(
    fund_id: str,
    request: Request,
    strategy_id: str | None = Query(default=None, max_length=64),
) -> dict:
    human(request)
    manager = fund(request, fund_id)
    if strategy_id and strategy_id not in desk_for(manager).state["strategies"]:
        raise HTTPException(404, "Unknown strategy_id in this fund")
    return build_scorecard(fund_id, store(request).records[fund_id], manager, strategy_id).model_dump()
