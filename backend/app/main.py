"""Local API entrypoint.

Routes:
  GET  /api/health
  POST /api/run   RunRequest -> RunResponse. Five analysts run concurrently, the PM
                  reconciles them, the backtest runs forward from the cutoff. Results
                  are cached on disk under backend/.cache/ keyed by cutoff (+ a short
                  hash when the universe or baseline differ from the fixture defaults).

Run from the repo root:  uv run fastapi dev --host 127.0.0.1 --port 8000
Set MOCK_AGENTS=1 to serve fixture memos and weights without Bedrock.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.agents import fundamentals, geopolitics, macro, pm, sentiment, technical
from backend.app.agents.base import assert_no_lookahead, mock_mode
from backend.app.agents.data_access import fixture
from backend.app.schema import Equity, Memo, RunMetrics, RunRequest, RunResponse, Source, Weight

log = logging.getLogger("desk.api")

app = FastAPI(title="AWS hackathon API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"
ANALYSTS = (technical, fundamentals, macro, sentiment, geopolitics)

try:  # Lane B's backtest; stubbed from the fixture until it lands
    from backend.app.backtest import backtest as _real_backtest  # type: ignore
except Exception:
    _real_backtest = None


class HealthResponse(BaseModel):
    status: str


@app.get("/api/health", tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


# --- Lane B: last close for the tape fallback -------------------------------------
# {"AAPL": {"date": "2025-06-30", "close": 205.17, "change_pct": 2.03}, ...}
# Full history, not cutoff-filtered: it feeds the header tape only, never an agent.
@app.get("/api/last-close", tags=["data"])
def last_close() -> dict[str, dict[str, float | str]]:
    from backend.app.data import last_close as _last_close

    return _last_close()


# ---------------------------------------------------------------- /api/run


def _cache_path(req: RunRequest) -> Path:
    fx = fixture()
    default = req.universe == fx["universe"] and req.baseline == fx["baseline"]
    if default:
        return CACHE_DIR / f"run_{req.cutoff}.json"
    key = hashlib.sha1(json.dumps([req.universe, req.baseline]).encode()).hexdigest()[:8]
    return CACHE_DIR / f"run_{req.cutoff}_{key}.json"


def _fixture_backtest(weights: list[Weight], cutoff: str) -> tuple[Equity, RunMetrics]:
    """Fixture equity sliced from the cutoff forward and rebased to 1.0. Metrics are
    the fixture's; they are placeholders until backend/app/backtest.py exists."""
    fx = fixture()
    eq = fx["equity"]
    idx = next((i for i, d in enumerate(eq["dates"]) if d >= cutoff), 0)
    if idx >= len(eq["dates"]) - 1:
        idx = 0  # cutoff beyond the fixture window: show the whole curve
    sliced = {}
    for key in ("portfolio", "equal_weight", "spy"):
        base = eq[key][idx] or 1.0
        sliced[key] = [round(v / base, 6) for v in eq[key][idx:]]
    equity = Equity(dates=eq["dates"][idx:], **sliced)
    return equity, RunMetrics.model_validate(fx["metrics"])


def _backtest(weights: list[Weight], cutoff: str) -> tuple[Equity, RunMetrics]:
    if _real_backtest is not None:
        try:
            return _real_backtest(weights, cutoff)
        except Exception as exc:
            log.warning("backend.app.backtest failed (%s); using fixture equity", exc)
    return _fixture_backtest(weights, cutoff)


async def _run_pipeline(req: RunRequest) -> RunResponse:
    results = await asyncio.gather(*(asyncio.to_thread(a.run, req.universe, req.cutoff) for a in ANALYSTS))
    memos: list[Memo] = [r[0] for r in results]
    sources: dict[str, Source] = {}
    for _, cited in results:
        for s in cited:
            sources[s.id] = s
    all_sources = list(sources.values())
    assert_no_lookahead(all_sources, req.cutoff)

    weights = await asyncio.to_thread(pm.run, memos, req.universe, req.cutoff)
    equity, metrics = await asyncio.to_thread(_backtest, weights, req.cutoff)
    return RunResponse(
        universe=req.universe,
        cutoff=req.cutoff,
        baseline=req.baseline,
        sources=all_sources,
        memos=memos,
        weights=weights,
        equity=equity,
        metrics=metrics,
    )


@app.post("/api/run", tags=["run"])
async def run(req: RunRequest, refresh: bool = Query(False, description="Ignore the cache")) -> RunResponse:
    if not req.universe:
        raise HTTPException(400, "universe is empty")
    if len(req.cutoff) != 10:
        raise HTTPException(400, "cutoff must be an ISO date, YYYY-MM-DD")
    path = _cache_path(req)
    if path.exists() and not refresh:
        try:
            return RunResponse.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("cache %s unreadable (%s); recomputing", path.name, exc)
    try:
        resp = await _run_pipeline(req)
    except AssertionError as exc:  # look-ahead guard tripped
        raise HTTPException(500, str(exc)) from exc
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(resp.model_dump_json(indent=1), encoding="utf-8")
    log.info("run %s cached at %s (mock=%s)", req.cutoff, path.name, mock_mode())
    return resp
