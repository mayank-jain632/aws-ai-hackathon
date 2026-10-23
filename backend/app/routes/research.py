"""Private research bridge for authenticated canvas workers."""

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from backend.app.research import (
    SOURCES,
    ResearchContext,
    ResearchQuery,
    claim_context,
    query_snapshot,
)

router = APIRouter(prefix="/api/internal/research", tags=["research"])


def caller(request: Request):
    # Imported lazily to avoid a main/router import cycle; uses the same worker auth
    # and manager lookup as delegation, including fund scoping when installed.
    from backend.app.main import authenticate_worker

    return authenticate_worker(request)


@router.get("/sources")
def sources(request: Request) -> dict:
    caller(request)
    from backend.app import data

    return {"sources": SOURCES, "tickers": data.ALL_TICKERS, "fred_series": ["CPIAUCSL", "DGS10", "FEDFUNDS", "UNRATE"]}


@router.post("/context")
async def context(body: ResearchContext, request: Request) -> dict:
    agent = caller(request)
    try:
        claim_context(agent, agent.manager, body)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return body.model_dump(mode="json")


@router.post("/query")
async def query(body: ResearchQuery, request: Request) -> dict:
    agent = caller(request)
    try:
        claim_context(agent, agent.manager, ResearchContext(mode=body.mode, cutoff=body.cutoff))
        return await run_in_threadpool(query_snapshot, body)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
