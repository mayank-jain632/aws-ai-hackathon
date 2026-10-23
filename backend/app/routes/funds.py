"""Fund creation, mandate management, and scoped existing canvas API."""

from collections.abc import AsyncIterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from backend.app.agent import AgentManager
from backend.app.funds import FundStore, Mandate


@asynccontextmanager
async def lifespan(app):
    app.state.funds = FundStore(app.state.manager)
    yield
    await app.state.funds.close()


router = APIRouter(lifespan=lifespan)


def store(request):
    return request.app.state.funds


def fund(request, fund_id):
    try:
        return store(request).runtime(fund_id)
    except KeyError:
        raise HTTPException(404, "Fund not found") from None


@router.get("/api/funds")
def list_funds(request: Request) -> dict:
    return {"funds": store(request).list()}


@router.post("/api/funds", status_code=201)
async def create_fund(body: Mandate, request: Request) -> dict:
    try:
        return store(request).create(body, getattr(request.state, "user", "Local team"))
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/api/funds/{fund_id}")
def get_fund(fund_id: str, request: Request) -> dict:
    fund(request, fund_id)
    return store(request).detail(fund_id)


@router.put("/api/funds/{fund_id}/mandate")
async def update_mandate(fund_id: str, body: Mandate, request: Request) -> dict:
    runtime = fund(request, fund_id)
    if any(a.state["status"] == "running" for a in runtime.agents.values()):
        raise HTTPException(
            409, "Wait for running agents to finish before changing the mandate"
        )
    current = store(request)
    current.records[fund_id].update(
        body.model_dump(), updated_at=datetime.now(UTC).isoformat()
    )
    current.save()
    current.runtime(fund_id)
    (runtime.root / "workspace" / "mandate.md").write_text(
        "# Fund mandate\n\n" + runtime.context + "\n"
    )
    runtime.publish()
    return current.detail(fund_id)


class StatusUpdate(BaseModel):
    status: Literal["active", "paused", "archived"]


@router.patch("/api/funds/{fund_id}/status")
async def change_status(fund_id: str, body: StatusUpdate, request: Request) -> dict:
    runtime = fund(request, fund_id)
    current = store(request)
    current.records[fund_id]["status"] = body.status
    current.records[fund_id]["updated_at"] = datetime.now(UTC).isoformat()
    current.save()
    runtime.paused = body.status != "active"
    if runtime.paused:
        await runtime.close()
    runtime.publish()
    return current.detail(fund_id)


# Reuse the tested canvas handlers without duplicating their validation and SSE behavior.
def event_runtime(fund_id: str, request: Request) -> AgentManager:
    return fund(request, fund_id)


@router.get("/api/funds/{fund_id}/events", response_class=EventSourceResponse)
async def fund_events(
    request: Request, runtime: Annotated[AgentManager, Depends(event_runtime)]
) -> AsyncIterable[ServerSentEvent]:
    from backend.app.main import events

    request.state.fund_manager = runtime
    async for event in events(request):
        yield event


@router.get("/api/funds/{fund_id}/agents")
def fund_agents(fund_id: str, request: Request) -> dict:
    return fund(request, fund_id).snapshot()


@router.post("/api/funds/{fund_id}/agents/{agent_id}/messages", status_code=202)
async def message(fund_id: str, agent_id: str, request: Request):
    from backend.app.main import MessageRequest, send_message

    request.state.fund_manager = fund(request, fund_id)
    try:
        body = MessageRequest.model_validate(await request.json())
    except ValueError:
        raise HTTPException(422, "Enter a message of 1 to 12000 characters") from None
    return await send_message(agent_id, body, request)


@router.post("/api/funds/{fund_id}/agents/{agent_id}/stop")
async def stop(fund_id: str, agent_id: str, request: Request):
    from backend.app.main import stop_agent

    request.state.fund_manager = fund(request, fund_id)
    return await stop_agent(agent_id, request)


@router.get("/api/funds/{fund_id}/agents/{agent_id}/file")
def file(
    fund_id: str,
    agent_id: str,
    path: Annotated[str, Query(min_length=1)],
    request: Request,
):
    from backend.app.main import read_file

    request.state.fund_manager = fund(request, fund_id)
    return read_file(agent_id, path, request)


@router.patch("/api/funds/{fund_id}/board/layout")
async def layout(fund_id: str, request: Request):
    from backend.app.main import LayoutUpdate, update_layout

    request.state.fund_manager = fund(request, fund_id)
    try:
        body = LayoutUpdate.model_validate(await request.json())
    except ValueError:
        raise HTTPException(422, "Provide a valid agent position or reset") from None
    return await update_layout(body, request)


@router.post("/api/funds/{fund_id}/plan", status_code=202)
async def plan(fund_id: str, request: Request) -> dict:
    runtime = fund(request, fund_id)
    try:
        await runtime.agents["dexter"].start(
            "Review this fund mandate. Write fund-plan.md with the objective, portfolio constraints, proposed research tasks, and a cautious next-step checklist. Write research-checklist.md listing the real data and tools required before any strategy, backtest, or trade can be claimed. Use only the provided mandate and existing files. Do not invent prices, sources, performance, or executions. Do not create subagents for this initial planning step. Read back your plan and report what you created.",
            getattr(request.state, "user", "Team").split("@")[0].title(),
        )
    except (ValueError, RuntimeError) as error:
        raise HTTPException(409, str(error)) from error
    return {"accepted": True}
