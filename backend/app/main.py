"""Local canvas API and the private bridge used by Dexter's agent tools."""

import asyncio
import json
import secrets
from collections.abc import AsyncIterable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.access import HostedAccess
from backend.app.agent import AgentManager


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


def manager(request: Request) -> AgentManager:
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
    try:
        yield ServerSentEvent(data=current.snapshot())
        while True:
            try:
                snapshot = await asyncio.wait_for(queue.get(), timeout=10)
            except TimeoutError:
                snapshot = current.snapshot()
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
    current = manager(request)
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "parentId": a.parent_id,
                "status": a.state["status"],
            }
            for a in current.agents.values()
            if caller.id in current.ancestors(a.id)
        ]
    }


@app.post("/api/internal/agents/{action}")
async def delegate(action: str, body: AgentTask, request: Request) -> dict:
    caller = authenticate_worker(request)
    current = manager(request)
    if not body.task.strip() or not body.name.strip():
        raise HTTPException(422, "Name and task cannot be blank")
    try:
        if action == "create":
            child = await current.create(caller.id, body.name, body.task)
        elif action == "message":
            child = get_agent(request, body.agent_id)
            if child.id == caller.id or caller.id not in current.ancestors(child.id):
                raise ValueError("An agent can delegate only to its own descendants.")
            await child.start(body.task, caller.name)
        else:
            raise HTTPException(404, "Unknown action")
        return await current.result(child)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


# The same server serves the built React app and API inside the single container.
frontend = Path(__file__).resolve().parents[2] / "frontend/dist"
if frontend.is_dir():
    app.frontend("/", directory=str(frontend))
