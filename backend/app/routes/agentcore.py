"""AgentCore status for people: the hosted second-opinion runtime, recent invocations and trace links (D28).

Invocations name a fund's flagged orders, so each person sees only the funds they can access,
through the same membership check as `GET /api/funds`.
"""

from fastapi import APIRouter, Request

from backend.app import agentcore
from backend.app.routes.desk import human

router = APIRouter(tags=["agentcore"])


@router.get("/api/agentcore")
def agentcore_status(request: Request) -> dict:
    human(request)
    sharing = getattr(request.app.state, "sharing", None)
    email = getattr(request.state, "user", "local")
    return agentcore.status(can_see=(lambda fund_id: sharing.can_access(fund_id, email)) if sharing else None)
