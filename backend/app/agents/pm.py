"""Portfolio manager: reconciles the five memos into long-only target weights.

`run(memos, universe, cutoff) -> list[Weight]`, weights sum to 1, every position carries
a rationale, a "changes my mind" trigger and per-analyst influence.

A deterministic score (long = +confidence, avoid = -confidence, summed over analysts)
seeds the book. In mock mode the fixture weights are served, filtered to the universe
and renormalised. With Bedrock, the model gets the memos plus the seed and returns the
final book; we then clamp, drop tickers outside the universe, and renormalise.
"""

from __future__ import annotations

import logging
from typing import get_args

from pydantic import BaseModel, Field

from backend.app.agents import base
from backend.app.agents.data_access import fixture
from backend.app.schema import Analyst, Memo, Weight

log = logging.getLogger("desk.agents")

ANALYSTS: tuple[Analyst, ...] = get_args(Analyst)

SYSTEM = """You are the PORTFOLIO MANAGER of a small research desk. Five analysts have
sent you dated notes. Build a long-only book over the given universe:
- Weights between 0 and 1 and summing to 1. A ticker may be 0 (omit it or set 0).
- Prefer positions where analysts agree; size down where they conflict; say so.
- rationale: one or two sentences, naming which analysts drove the position.
- changes_my_mind: one concrete, checkable trigger (a number, a print, a level) that
  would make you cut or add, in the style "Cut to 5% if X" / "Add if Y".
- analyst_influence: for each of technical, fundamentals, macro, sentiment, geopolitics
  a number 0..1 for how much that analyst moved this position (informal, not a sum).
Never use information after the cutoff date. No hindsight."""


class _Book(BaseModel):
    weights: list[Weight] = Field(min_length=1)


def seed_scores(memos: list[Memo], universe: list[str]) -> dict[str, dict[Analyst, float]]:
    """ticker -> analyst -> signed conviction. long=+c, avoid=-c, neutral=0."""
    out: dict[str, dict[Analyst, float]] = {t: {} for t in universe}
    for m in memos:
        for v in m.views:
            if v.ticker not in out:
                continue
            sign = {"long": 1.0, "avoid": -1.0, "neutral": 0.0}[v.stance]
            out[v.ticker][m.analyst] = sign * v.confidence
    return out


def seed_weights(scores: dict[str, dict[Analyst, float]]) -> dict[str, float]:
    """Soft long-only tilt: base 1 + sum of signed convictions, floored at 0.1 so a
    ticker nobody avoids keeps a small weight; renormalised."""
    raw = {t: max(0.1, 1.0 + sum(s.values())) for t, s in scores.items()}
    total = sum(raw.values())
    return {t: v / total for t, v in raw.items()}


def _normalise(weights: list[Weight], universe: list[str]) -> list[Weight]:
    kept = [w for w in weights if w.ticker in universe and w.weight > 0]
    seen: set[str] = set()
    uniq = []
    for w in kept:
        if w.ticker in seen:
            continue
        seen.add(w.ticker)
        uniq.append(w)
    total = sum(w.weight for w in uniq)
    if not uniq or total <= 0:
        raise ValueError("PM returned an empty book")
    for w in uniq:
        w.weight = round(w.weight / total, 4)
        w.analyst_influence = {a: float(min(1.0, max(0.0, w.analyst_influence.get(a, 0.0)))) for a in ANALYSTS}
    # fix rounding drift so the book sums to exactly 1
    drift = round(1.0 - sum(w.weight for w in uniq), 4)
    uniq[0].weight = round(uniq[0].weight + drift, 4)
    uniq.sort(key=lambda w: -w.weight)
    return uniq


def _mock_book(memos: list[Memo], universe: list[str]) -> list[Weight]:
    fx = [Weight.model_validate(w) for w in fixture()["weights"] if w["ticker"] in universe]
    if fx:
        return _normalise(fx, universe)
    # universe shares nothing with the fixture: derive a book from the seed scores
    scores = seed_scores(memos, universe)
    out = []
    for t, w in seed_weights(scores).items():
        infl = {a: abs(scores[t].get(a, 0.0)) for a in ANALYSTS}
        out.append(Weight(ticker=t, weight=w, rationale="Seeded from analyst conviction (mock PM).", changes_my_mind="Any analyst flips to avoid with confidence above 0.6.", analyst_influence=infl))
    return _normalise(out, universe)


def run(memos: list[Memo], universe: list[str], cutoff: str) -> list[Weight]:
    if base.mock_mode():
        return _mock_book(memos, universe)

    scores = seed_scores(memos, universe)
    seed = seed_weights(scores)
    notes = "\n\n".join(
        f"=== {m.analyst.upper()} note, {m.date}\n{m.headline}\n{m.body}\n"
        + "\n".join(f"  {v.ticker}: {v.stance} ({v.confidence:.2f}) {v.note} [{', '.join(v.sources)}]" for v in m.views)
        for m in memos
    )
    user_prompt = (
        f"Cutoff: {cutoff}. Universe: {', '.join(universe)}.\n\n{notes}\n\n"
        "Seed weights from a mechanical conviction score (you may deviate):\n"
        + "\n".join(f"  {t}: {w:.3f}" for t, w in seed.items())
        + "\n\nReturn the final book."
    )
    try:
        book = base.run_structured(SYSTEM, user_prompt, _Book)
        return _normalise(book.weights, universe)
    except Exception as exc:
        log.error("PM Bedrock call failed (%s); serving mock book", exc)
        return _mock_book(memos, universe)
