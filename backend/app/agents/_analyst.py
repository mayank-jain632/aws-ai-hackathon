"""Shared analyst runner. Each concrete analyst module supplies a persona prompt and a
data slice; this module does the Bedrock call (or the mock path), enforces the
look-ahead guard, and shapes the result into a `Memo`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel, Field

from backend.app.agents import base
from backend.app.agents.data_access import fixture
from backend.app.schema import Analyst, Memo, Source, View

log = logging.getLogger("desk.agents")

Slicer = Callable[[str, list[str]], tuple[str, list[Source]]]

HOUSE_STYLE = """You are an analyst on a small research desk writing a dated, signed note
for a portfolio manager. Rules:
- Use ONLY the evidence provided. Everything is dated on or before the cutoff; never
  reference anything that happened after the cutoff. No hindsight.
- Headline: one line, specific, no clickbait.
- Body: 3 to 5 sentences, first person, concrete numbers from the evidence, a clear
  view on where you have conviction and where you do not.
- Views: one per ticker you have an opinion on (cover at least four tickers from the
  universe). stance is long / neutral / avoid; confidence 0..1; note is one short
  sentence; sources lists the ids of the evidence you actually used for that ticker.
- Only cite source ids that appear in the evidence."""


class _MemoDraft(BaseModel):
    headline: str
    body: str
    views: list[View] = Field(min_length=1)


def run_analyst(analyst: Analyst, persona: str, slicer: Slicer, universe: list[str], cutoff: str) -> tuple[Memo, list[Source]]:
    digest, sources = slicer(cutoff, universe)
    base.assert_no_lookahead(sources, cutoff)

    if base.mock_mode() or not sources:
        memo = _mock_memo(analyst, universe, cutoff, sources)
        return memo, _cited(memo, sources)

    evidence = "\n".join(f"[{s.id}] {s.date} | {s.title}\n    {s.excerpt}" for s in sources)
    user_prompt = (
        f"Cutoff date: {cutoff}. Universe: {', '.join(universe)}.\n\n"
        f"Evidence (your only inputs):\n{evidence}\n\n"
        f"Raw data digest:\n{digest[:6000]}\n\n"
        f"Write your {analyst} note dated {cutoff}."
    )
    try:
        draft = base.run_structured(HOUSE_STYLE + "\n\n" + persona, user_prompt, _MemoDraft)
    except Exception as exc:  # noqa: BLE001 deliberate fallback to fixture/mock
        log.error("%s analyst Bedrock call failed (%s); serving mock memo", analyst, exc)
        memo = _mock_memo(analyst, universe, cutoff, sources)
        return memo, _cited(memo, sources)

    valid_ids = {s.id for s in sources}
    views = []
    for v in draft.views:
        if v.ticker not in universe:
            continue
        v.sources = [sid for sid in v.sources if sid in valid_ids]
        views.append(v)
    if not views:
        views = _mock_memo(analyst, universe, cutoff, sources).views
    memo = Memo(analyst=analyst, date=cutoff, headline=draft.headline.strip(), body=draft.body.strip(), views=views)
    return memo, _cited(memo, sources)


def _cited(memo: Memo, sources: list[Source]) -> list[Source]:
    ids = {sid for v in memo.views for sid in v.sources}
    return [s for s in sources if s.id in ids]


def _mock_memo(analyst: Analyst, universe: list[str], cutoff: str, sources: list[Source]) -> Memo:
    """Fixture memo for this analyst, re-dated to the cutoff, restricted to the universe
    and to sources that survived the cutoff filter."""
    valid_ids = {s.id for s in sources}
    raw = next(m for m in fixture()["memos"] if m["analyst"] == analyst)
    views = []
    for v in raw["views"]:
        if v["ticker"] not in universe:
            continue
        kept = [sid for sid in v["sources"] if sid in valid_ids]
        if kept:
            views.append(View(**{**v, "sources": kept}))
    if not views:
        views = [View(ticker=universe[0], stance="neutral", confidence=0.3, note="No usable evidence before the cutoff.", sources=[])]
    return Memo(analyst=analyst, date=cutoff, headline=raw["headline"], body=raw["body"], views=views)
