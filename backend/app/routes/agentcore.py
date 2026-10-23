"""AgentCore status for people: the hosted second-opinion runtime, recent invocations and trace links (D28)."""

from fastapi import APIRouter, Request

from backend.app import agentcore
from backend.app.routes.desk import human

router = APIRouter(tags=["agentcore"])


@router.get("/api/agentcore")
def agentcore_status(request: Request) -> dict:
    human(request)
    return agentcore.status()
