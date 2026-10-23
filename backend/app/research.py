"""Bounded, dated access to existing snapshots. Never read CSVs from agent code."""

import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app import data

SourceName = Literal["prices", "ohlcv", "fundamentals", "macro", "events", "tone"]

SOURCES = {
    "prices": {"provider": "Yahoo Finance snapshot", "url": "https://finance.yahoo.com/", "availability": "date", "warning": "Split-adjusted prices; excludes dividends."},
    "ohlcv": {"provider": "Yahoo Finance snapshot", "url": "https://finance.yahoo.com/", "availability": "date", "warning": "Daily bars from the committed snapshot."},
    "fundamentals": {"provider": "SEC XBRL companyfacts", "url": "https://www.sec.gov/edgar/search/", "availability": "filed", "warning": "Filtered by filing date, not quarter end; snapshot may contain later revisions."},
    "macro": {"provider": "FRED", "url": "https://fred.stlouisfed.org/", "availability": "available", "warning": "Release dates are approximated; observations are not historical vintages and may be revised."},
    "events": {"provider": "Hand-curated event sample", "url": None, "availability": "date", "warning": "UNVERIFIED hand-written headlines and tone scores. Not verified GDELT evidence."},
    "tone": {"provider": "GDELT DOC API", "url": "https://api.gdeltproject.org/api/v2/doc/doc", "availability": "date", "warning": "Optional snapshot; empty when the fetch was rate-limited. Never substitute curated scores."},
}


class ResearchContext(BaseModel):
    mode: Literal["historical", "live"]
    cutoff: date | None = None

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "historical" and self.cutoff is None:
            raise ValueError("Historical research requires an explicit cutoff date")
        if self.mode == "live" and self.cutoff is not None:
            raise ValueError("Live research cannot claim a historical cutoff")
        if self.cutoff and self.cutoff > date.today():
            raise ValueError("Cutoff cannot be in the future")
        return self


class ResearchQuery(ResearchContext):
    source: SourceName
    tickers: list[str] = Field(default_factory=list, max_length=11)
    subjects: list[str] = Field(default_factory=list, max_length=20)
    series: list[str] = Field(default_factory=list, max_length=4)
    start: date | None = None
    limit: int = Field(default=40, ge=1, le=200)


def query_snapshot(query: ResearchQuery) -> dict:
    cutoff = (query.cutoff or date.today()).isoformat()
    tickers = list(dict.fromkeys(t.upper() for t in query.tickers))
    if set(tickers) - set(data.ALL_TICKERS):
        raise ValueError(f"Unsupported ticker; available: {', '.join(data.ALL_TICKERS)}")
    if query.start and query.start.isoformat() > cutoff:
        raise ValueError("Start must be on or before cutoff")
    if query.source == "prices":
        frame = data.prices(cutoff, tickers or None).reset_index()
    elif query.source == "ohlcv":
        if len(tickers) != 1:
            raise ValueError("OHLCV requires exactly one supported ticker")
        frame = data.ohlcv(tickers[0], cutoff)
    elif query.source == "fundamentals":
        frame = data.fundamentals(cutoff, tickers or None)
    elif query.source == "macro":
        frame = data.macro(cutoff, wide=False)
        if query.series:
            if set(query.series) - {"CPIAUCSL", "DGS10", "FEDFUNDS", "UNRATE"}:
                raise ValueError("Unsupported FRED series")
            frame = frame[frame["series"].isin(query.series)]
    else:
        subjects = query.subjects or tickers or None
        frame = getattr(data, query.source)(cutoff, subjects)
    availability = SOURCES[query.source]["availability"]
    frame = frame.sort_values(availability, kind="stable")
    if query.start:
        frame = frame[frame[availability] >= query.start.isoformat()]
    count = len(frame)
    frame = frame.tail(query.limit)
    rows = json.loads(frame.to_json(orient="records", date_format="iso"))
    return {
        "source": query.source, **SOURCES[query.source], "mode": query.mode,
        "cutoff": cutoff, "snapshot": True, "matching_rows": count,
        "returned_rows": len(rows), "truncated": count > query.limit,
        "latest_available": str(frame[availability].max())[:10] if count else None,
        "rows": rows,
    }


def claim_context(caller, manager, context: ResearchContext) -> None:
    """Lock conversations and active ancestors to one mode and historical cutoff.

    Persisting this prevents prior live results or a later cutoff leaking into a
    historical follow-up. Descendants inherit restrictions through their ancestors.
    """
    requested = context.model_dump(mode="json")
    lineage = [manager.agents[i] for i in manager.ancestors(caller.id)]
    for agent in lineage:
        existing = agent.state.get("research_context")
        if existing and existing != requested:
            raise ValueError("Research context conflicts with this conversation or an ancestor. Use a separate agent tree for live research or a different cutoff.")
    for agent in lineage:
        agent.state["research_context"] = requested
        agent.publish()
