"""Human fund sharing, using the same persistent membership as login/API access."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class Invite(BaseModel):
    email: str = Field(min_length=3, max_length=254)


def sharing(request, fund_id):
    if request.headers.get("x-agent-token"):
        raise HTTPException(403, "Agents cannot change fund sharing")
    if fund_id not in request.app.state.funds.records:
        raise HTTPException(404, "Fund not found")
    current = request.app.state.sharing
    email = getattr(request.state, "user", "local")
    if not current.can_access(fund_id, email):
        raise HTTPException(403, "You do not have access to this fund")
    return current, email


@router.get("/api/funds/{fund_id}/members")
def members(fund_id: str, request: Request) -> dict:
    current, email = sharing(request, fund_id)
    return {"members": current.members(fund_id), "you": email}


@router.post("/api/funds/{fund_id}/members")
def invite(fund_id: str, body: Invite, request: Request) -> dict:
    current, _ = sharing(request, fund_id)
    try:
        token = current.invite(fund_id, body.email)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "members": current.members(fund_id),
        "invitation_path": f"/join/{token}" if token else None,
    }


@router.delete("/api/funds/{fund_id}/members/{email}")
def remove(fund_id: str, email: str, request: Request) -> dict:
    current, actor = sharing(request, fund_id)
    try:
        current.remove(fund_id, email.lower(), actor)
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    request.app.state.funds.runtime(fund_id).publish()
    return {"members": current.members(fund_id), "you": actor}
