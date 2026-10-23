"""Human model selection for idle agents; evaluators remain pinned."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.models import CATALOG
from backend.app.routes.desk import current_manager, human

router = APIRouter(tags=["agent models"])


class ModelSelection(BaseModel):
    model: str = Field(min_length=1, max_length=100)


@router.get("/api/agent-models")
def catalog() -> dict:
    return CATALOG


@router.put("/api/agents/{agent_id}/model")
@router.put("/api/funds/{fund_id}/agents/{agent_id}/model")
async def change_model(
    agent_id: str, body: ModelSelection, request: Request, fund_id: str | None = None
) -> dict:
    human(request)
    agent = current_manager(request, fund_id).agents.get(agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    try:
        await agent.set_model(body.model)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return agent.snapshot()
