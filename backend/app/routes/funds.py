"""Fund creation, mandate management, and scoped existing canvas API."""

import json
import os
from collections.abc import AsyncIterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from backend.app.agent import AgentManager
from backend.app.fund_schedule import FundScheduler, busy
from backend.app.funds import FundStore, Mandate
from backend.app.sharing import ShareStore


@asynccontextmanager
async def lifespan(app):
    app.state.funds = FundStore(app.state.manager)
    app.state.sharing = ShareStore(
        app.state.funds.root, json.loads(os.getenv("APP_DEMO_ACCOUNTS", "{}"))
    )
    app.state.sharing.migrate(app.state.funds.records)
    app.state.fund_scheduler = FundScheduler(app.state.funds)
    app.state.fund_scheduler.start()
    try:
        yield
    finally:
        await app.state.fund_scheduler.close()
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
    current = request.app.state.sharing
    email = getattr(request.state, "user", "local")
    return {
        "funds": [
            item
            for item in store(request).list()
            if current.can_access(item["id"], email)
        ]
    }


@router.post("/api/funds", status_code=201)
async def create_fund(body: Mandate, request: Request) -> dict:
    try:
        owner = getattr(request.state, "user", "local")
        created = store(request).create(body, owner)
        request.app.state.sharing.create(created["id"], owner)
        return created
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/api/funds/{fund_id}")
def get_fund(fund_id: str, request: Request) -> dict:
    fund(request, fund_id)
    return store(request).detail(fund_id)


@router.put("/api/funds/{fund_id}/mandate")
async def update_mandate(fund_id: str, body: Mandate, request: Request) -> dict:
    runtime = fund(request, fund_id)
    if busy(runtime):
        raise HTTPException(
            409, "Wait for running agents to finish before changing the mandate"
        )
    current = store(request)
    current.records[fund_id].update(
        body.model_dump(), updated_at=datetime.now(UTC).isoformat()
    )
    current.save()
    current.runtime(fund_id)
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
        await request.app.state.fund_scheduler.disable(
            fund_id, f"Disabled: fund {body.status}"
        )
        await runtime.close()
    runtime.publish()
    return current.detail(fund_id)


class ScheduleUpdate(BaseModel):
    enabled: bool


@router.put("/api/funds/{fund_id}/schedule")
async def update_schedule(fund_id: str, body: ScheduleUpdate, request: Request) -> dict:
    from backend.app.routes.sharing import sharing

    if request.headers.get("x-agent-token"):
        raise HTTPException(403, "Only teammates can change hourly wakeups")
    _, actor = sharing(request, fund_id)
    try:
        return await request.app.state.fund_scheduler.configure(
            fund_id, body.enabled, actor
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


# Reuse the tested canvas handlers without duplicating their validation and SSE behavior.
def event_runtime(fund_id: str, request: Request) -> AgentManager:
    return fund(request, fund_id)


@router.get("/api/funds/{fund_id}/events", response_class=EventSourceResponse)
async def fund_events(
    request: Request, runtime: Annotated[AgentManager, Depends(event_runtime)]
) -> AsyncIterable[ServerSentEvent]:
    from backend.app.main import events

    request.state.fund_manager = runtime
    request.state.fund_id = request.path_params["fund_id"]
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
    if agent_id == "dexter":
        await request.app.state.fund_scheduler.disable(
            fund_id, "Disabled: Dexter stopped by a teammate"
        )
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
            "Run this fund's research-to-paper-execution workflow under its current mandate. "
            "This request supersedes earlier document-only, research-only and no-order planning tasks "
            "under the saved standing paper authorization, without overriding explicit user Stop. "
            "Read mandate.md and inspect_desk first. Then use create_agent to start "
            "research specialists for distinct evidence families, such as company "
            "fundamentals/filings and macro/market risk. Give each specialist the fund "
            "mandate, research mode, decision cutoff, a concrete task and a shared memo path. "
            "Reuse suitable existing specialists with message_agent. Obtain actual "
            "tool-backed evidence; in historical mode use only cutoff-aware evidence "
            "and disclose unavailable historical sources instead of using current data. "
            "Have specialists delegate adversarial review of their findings. Continue "
            "from their results to a strategy specialist, immutable strategy registration, "
            "independent adversarial strategy review, and an Opus 4.6 backtester bound "
            "to the approved strategy_id. Report the actual evaluation result and "
            "provenance, including FAIL or blocked outcomes. Do not stop after writing "
            "a plan or checklist. Update fund-plan.md with completed phases, evidence "
            "paths, strategy/evaluation IDs and any concrete blockers. If one phase "
            "needs repair, delegate revision or a successor strategy and continue. Research-quality "
            "findings are advisory in autonomous paper mode without required approval; record "
            "them honestly and do not demand external operator adjudication. "
            "Keep trading permission, human approval requirements and emergency stop "
            "unchanged. After the real backtest and final independent review, hand off promptly "
            "to the paper execution agent. Make paper decisions and trades autonomously "
            "without redundant confirmation when the actual saved "
            "mandate, current backend evaluation/final review, applicable human approval "
            "and emergency stop checks permit them. Never clear the emergency stop or "
            "change the mandate to force execution. "
            "Never invent prices, sources, performance, approvals, trades or fills.",
            getattr(request.state, "user", "Team").split("@")[0].title(),
        )
    except (ValueError, RuntimeError) as error:
        raise HTTPException(409, str(error)) from error
    return {"accepted": True}
