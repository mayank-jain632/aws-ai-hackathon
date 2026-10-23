"""Local canvas API and the private bridge used by Dexter's agent tools."""

import asyncio
import json
import secrets
from collections.abc import AsyncIterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.access import HostedAccess
from backend.app.agent import AgentManager
from backend.app.roles import Role, allow_child, require_tool
from backend.app.routes.agentcore import router as agentcore_router
from backend.app.routes.charts import router as charts_router
from backend.app.routes.desk import router as desk_router
from backend.app.routes.funds import router as funds_router
from backend.app.routes.historical import router as historical_router
from backend.app.routes.models import router as models_router
from backend.app.routes.scores import router as scores_router
from backend.app.routes.sharing import router as sharing_router
from backend.app.routes.synthesis import router as synthesis_router
from backend.app.routes.watchdog import router as watchdog_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.manager = AgentManager()
    yield
    await app.state.manager.close()


app = FastAPI(title="Local agent canvas", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "127.0.0.1",
        "localhost",
        "*.cloudfront.net",
        "*.compute-1.amazonaws.com",
    ],
)
app.add_middleware(HostedAccess)


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)


class AgentTask(BaseModel):
    name: str = Field(default="Researcher", min_length=1, max_length=60)
    task: str = Field(min_length=1, max_length=12000)
    agent_id: str = Field(default="", max_length=60)
    role: Role = "research"
    strategy_id: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=100)
    wait_for_result: bool = True


def manager(request: Request) -> AgentManager:
    if hasattr(request.state, "fund_manager"):
        return request.state.fund_manager
    if request.headers.get("x-agent-token") and hasattr(request.app.state, "funds"):
        return request.app.state.funds.by_token(request.headers["x-agent-token"])
    return request.app.state.manager


def get_agent(request: Request, agent_id: str):
    current = manager(request).agents.get(agent_id)
    if not current:
        raise HTTPException(404, "Agent not found")
    return current


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


class BoardPosition(BaseModel):
    x: float = Field(ge=-100000, le=100000, allow_inf_nan=False)
    y: float = Field(ge=-100000, le=100000, allow_inf_nan=False)


class LayoutUpdate(BaseModel):
    agent_id: str = Field(default="", max_length=60)
    position: BoardPosition | None = None
    reset: bool = False


@app.get("/api/me")
def me(request: Request) -> dict:
    return {
        "email": getattr(request.state, "user", "local"),
        "hosted": bool(getattr(request.state, "user", "")),
    }


@app.patch("/api/board/layout")
async def update_layout(body: LayoutUpdate, request: Request) -> dict:
    current = manager(request)
    if body.reset:
        current.layout = {}
    elif body.position:
        get_agent(request, body.agent_id)
        current.layout[body.agent_id] = body.position.model_dump()
    else:
        raise HTTPException(422, "Provide an agent position or reset")
    temporary = current.layout_file.with_suffix(".tmp")
    temporary.write_text(json.dumps(current.layout))
    temporary.replace(current.layout_file)
    current.publish()
    return {"positions": current.layout}


@app.get("/api/agents")
def get_agents(request: Request) -> dict:
    return manager(request).snapshot()


@app.post("/api/agents/{agent_id}/messages", status_code=202)
async def send_message(agent_id: str, body: MessageRequest, request: Request) -> dict:
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Enter a message")
    try:
        await get_agent(request, agent_id).start(
            text, getattr(request.state, "user", "You").split("@")[0].title()
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    return {"accepted": True}


@app.post("/api/agents/{agent_id}/stop")
async def stop_agent(agent_id: str, request: Request) -> dict:
    get_agent(request, agent_id)
    await manager(request).stop(agent_id)
    return manager(request).snapshot()


@app.get("/api/events", response_class=EventSourceResponse)
async def events(request: Request) -> AsyncIterable[ServerSentEvent]:
    current = manager(request)
    queue = asyncio.Queue(maxsize=8)
    current.subscribers.add(queue)
    current.publish()

    def permitted():
        sharing = getattr(request.app.state, "sharing", None)
        fund_id = getattr(request.state, "fund_id", "general")
        email = getattr(request.state, "user", "local")
        return not sharing or sharing.can_access(fund_id, email)

    try:
        if not permitted():
            yield ServerSentEvent(event="access_revoked", data={})
            return
        yield ServerSentEvent(data=current.snapshot())
        while True:
            try:
                snapshot = await asyncio.wait_for(queue.get(), timeout=10)
            except TimeoutError:
                snapshot = current.snapshot()
            if not permitted():
                yield ServerSentEvent(event="access_revoked", data={})
                break
            yield ServerSentEvent(data=snapshot)
    finally:
        current.subscribers.discard(queue)
        current.publish()


@app.get("/api/agents/{agent_id}/file")
def read_file(
    agent_id: str, path: Annotated[str, Query(min_length=1)], request: Request
) -> dict:
    workspace = get_agent(request, agent_id).workspace.resolve()
    target = (workspace / path).resolve()
    if (
        not target.is_relative_to(workspace)
        or ".dexter" in target.relative_to(workspace).parts
    ):
        raise HTTPException(403, "File is outside this agent's workspace")
    if not target.is_file():
        raise HTTPException(404, "File not found")
    if target.stat().st_size > 256_000:
        raise HTTPException(413, "File is too large to preview")
    try:
        return {"path": path, "content": target.read_text()}
    except UnicodeDecodeError as error:
        raise HTTPException(415, "Only text files can be previewed") from error


def authenticate_worker(request: Request):
    token = request.headers.get("x-agent-token", "")
    if not secrets.compare_digest(token, manager(request).token):
        raise HTTPException(403, "Invalid agent control token")
    return get_agent(request, request.headers.get("x-agent-id", ""))


@app.get("/api/internal/agents")
def list_workers(request: Request) -> dict:
    caller = authenticate_worker(request)
    try:
        require_tool(caller, "list_agents")
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    current = manager(request)
    return {
        "agents": [
            a.graph_node(blind=caller.role == "backtester")
            for a in current.agents.values()
            if (caller.id == "dexter" and caller.role == "orchestrator") or caller.id in current.ancestors(a.id)
        ]
    }


def swarm_worker(request, tool):
    caller = authenticate_worker(request)
    try:
        require_tool(caller, tool)
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    return caller, manager(request)


@app.get("/api/internal/agents/{agent_id}/thread")
def read_worker_thread(
    agent_id: str, request: Request,
    cursor: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
    max_chars: Annotated[int, Query(ge=200, le=16000)] = 8000,
    include_activity: bool = False,
) -> dict:
    _, current = swarm_worker(request, "read_agent_thread")
    if agent_id not in current.agents:
        raise HTTPException(404, "Agent not found in this fund")
    return current.read_thread(agent_id, cursor=cursor, limit=limit, max_chars=max_chars, include_activity=include_activity)


class AgentProgress(BaseModel):
    phase: str = Field(min_length=1, max_length=200)
    status: str = Field(pattern="^(working|blocked|complete)$")
    blocker: str | None = Field(default=None, max_length=1000)
    artifacts: list[Annotated[str, Field(min_length=1, max_length=180)]] = Field(default_factory=list, max_length=10)


@app.post("/api/internal/agents/progress")
def report_worker_progress(body: AgentProgress, request: Request) -> dict:
    caller, current = swarm_worker(request, "report_agent_progress")
    if not current.worker_alive(caller):
        raise HTTPException(409, "Progress requires an active worker")
    if body.status == "blocked" and not (body.blocker or "").strip():
        raise HTTPException(422, "Blocked progress requires a concrete blocker")
    caller.state["workflow"] = {**body.model_dump(), "reported_at": datetime.now(UTC).isoformat()}
    caller.publish()
    return {"reported": caller.state["workflow"], "lifecycle": caller.lifecycle(), "note": "Self-reported progress; does not change gates or prove completion"}


class AgentResult(BaseModel):
    agent_id: str = Field(min_length=1, max_length=60)
    path: str | None = Field(default=None, max_length=4096)
    offset: int = Field(default=0, ge=0, le=100000000)
    limit: int = Field(default=12000, ge=1, le=16000)


@app.post("/api/internal/agents/result")
def read_worker_result(body: AgentResult, request: Request) -> dict:
    _, current = swarm_worker(request, "read_tool_result")
    if body.agent_id not in current.agents or current.agents[body.agent_id].role == "backtester":
        raise HTTPException(404, "Readable tool-result agent not found in this fund")
    try:
        return current.read_tool_result(body.agent_id, body.path, body.offset, body.limit)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


class AgentWait(BaseModel):
    seconds: float = Field(ge=0.01, le=3600, allow_inf_nan=False)
    agent_ids: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(default_factory=list)


@app.post("/api/internal/agents/wait")
async def wait_worker(body: AgentWait, request: Request) -> dict:
    caller, current = swarm_worker(request, "wait")
    try:
        return await current.wait_for_agents(caller, body.seconds, body.agent_ids)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/api/internal/agents/{action}")
async def delegate(action: str, body: AgentTask, request: Request) -> dict:
    caller = authenticate_worker(request)
    current = manager(request)
    if not body.task.strip() or not body.name.strip():
        raise HTTPException(422, "Name and task cannot be blank")
    try:
        if action not in {"create", "message"}:
            raise HTTPException(404, "Unknown action")
        require_tool(caller, "create_agent" if action == "create" else "message_agent")
        async with current.delegating(caller):
            if action == "create":
                child = await current.create(
                    caller.id,
                    body.name,
                    body.task,
                    body.role,
                    body.strategy_id,
                    body.model,
                )
            else:
                child = get_agent(request, body.agent_id)
                if child.id == caller.id or caller.id not in current.ancestors(
                    child.id
                ):
                    raise ValueError(
                        "An agent can delegate only to its own descendants."
                    )
                allow_child(caller, child.role)
                if caller.role == "backtester" and child.state.get(
                    "strategy_id"
                ) != caller.state.get("strategy_id"):
                    raise PermissionError(
                        "Blind delegates must evaluate the parent's frozen strategy"
                    )
                await child.start(body.task, caller.name)
            if not body.wait_for_result:
                return {"id": child.id, "name": "Historical evaluator" if caller.role == "backtester" else child.name, "status": child.state["status"], "background": True}
            result = await current.result(child)
            if caller.role == "backtester":
                result["files"] = []
                result["name"] = "Historical evaluator"
            return result
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


app.include_router(funds_router)
app.include_router(desk_router)
app.include_router(models_router)
app.include_router(sharing_router)
app.include_router(watchdog_router)
app.include_router(scores_router)
app.include_router(charts_router)
app.include_router(synthesis_router)
app.include_router(historical_router)
app.include_router(agentcore_router)

# The same server serves the built React app and API inside the single container.
frontend = Path(__file__).resolve().parents[2] / "frontend/dist"
if frontend.is_dir():
    app.frontend("/", directory=str(frontend))
