"""Read-only chart data for one fund. Same access gate as the scores route; writes nothing."""

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.charts import build_charts
from backend.app.desk import desk_for
from backend.app.routes.desk import human
from backend.app.routes.funds import fund, store

router = APIRouter(tags=["charts"])


@router.get("/api/funds/{fund_id}/charts")
def fund_charts(
    fund_id: str,
    request: Request,
    strategy_id: str | None = Query(default=None, max_length=64),
) -> dict:
    human(request)
    manager = fund(request, fund_id)
    if strategy_id and strategy_id not in desk_for(manager).state["strategies"]:
        raise HTTPException(404, "Unknown strategy_id in this fund")
    return build_charts(fund_id, store(request).records[fund_id], manager, strategy_id).model_dump()
