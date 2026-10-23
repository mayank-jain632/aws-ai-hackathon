"""Stage 1 for the walk-forward backtest: the five analysts, strict (no mock, no fixture).

An analyst with no evidence, or whose call fails after retries, ABSTAINS: a memo with one
neutral, confidence-0 view per universe ticker. Nothing is ever fabricated.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol, get_args

from backend.app.agents._analyst import HOUSE_STYLE, _MemoDraft
from backend.app.agents.base import assert_no_lookahead
from backend.app.agents.fundamentals import PERSONA as FUNDAMENTALS
from backend.app.agents.geopolitics import PERSONA as GEOPOLITICS
from backend.app.agents.macro import PERSONA as MACRO
from backend.app.agents.sentiment import PERSONA as SENTIMENT
from backend.app.agents.technical import PERSONA as TECHNICAL
from backend.app.schema import Analyst, Memo, Source, View

log = logging.getLogger("wf.analysts")

PERSONAS: dict[str, str] = {
    "technical": TECHNICAL,
    "fundamentals": FUNDAMENTALS,
    "macro": MACRO,
    "sentiment": SENTIMENT,
    "geopolitics": GEOPOLITICS,
}
ANALYSTS: tuple[str, ...] = get_args(Analyst)
DIGEST_CHARS = 6000

SYSTEM_SUFFIX = (
    "\n\nAll evidence you are given is dated on or before the decision date. Use only that "
    "evidence and nothing else you may know; do not reference anything after the decision date."
)


class Masker(Protocol):
    def encode(self, text: str) -> str: ...
    def decode_ticker(self, code: str) -> str: ...


def abstain_memo(analyst: str, as_of: str, universe: list[str], reason: str) -> Memo:
    views = [
        View(
            ticker=t,
            stance="neutral",
            confidence=0.0,
            note=f"Abstained: {reason}",
            sources=[],
        )
        for t in universe
    ]
    return Memo(
        analyst=analyst,
        date=as_of,
        headline=f"{analyst} abstained",
        body=f"Abstained: {reason}",
        views=views,
    )


def build_prompt(
    analyst: str,
    as_of: str,
    universe: list[str],
    digest: str,
    sources: list[Source],
    enc,
) -> str:
    evidence = "\n".join(
        f"[{s.id}] {s.date} | {enc(s.title)}\n    {enc(s.excerpt)}" for s in sources
    )
    return (
        f"Decision date (cutoff): {as_of}. Universe: {', '.join(universe)}.\n\n"
        f"Evidence (your only inputs, all dated on or before {as_of}):\n{evidence}\n\n"
        f"Raw data digest:\n{enc(digest)[:DIGEST_CHARS]}\n\n"
        f"Write your {analyst} note dated {as_of}."
    )


def _clean_views(
    draft: _MemoDraft, universe: set[str], valid_ids: set[str], decode
) -> list[View]:
    views: dict[str, View] = {}
    for v in draft.views:
        ticker = decode(v.ticker)
        if ticker not in universe or ticker in views:
            continue
        kept = [sid for sid in v.sources if sid in valid_ids]
        views[ticker] = v.model_copy(update={"ticker": ticker, "sources": kept})
    return list(views.values())


def _identity_masker_fns(masker: Masker | None, universe: list[str]):
    if masker is None:
        return (lambda s: s), (lambda t: t), list(universe)
    codes = [masker.encode(t) for t in universe]
    reverse = dict(zip(codes, universe, strict=True))

    def decode(code: str) -> str:
        if code in reverse:
            return reverse[code]
        try:
            return masker.decode_ticker(code)
        except Exception:  # noqa: BLE001 unknown code: filtered out by the universe check
            return code

    return masker.encode, decode, codes


def run_analyst_strict(
    pit: Any,
    llm: Any,
    analyst: str,
    as_of: str,
    universe: list[str],
    masker: Masker | None = None,
) -> tuple[Memo, list[Source], bool]:
    """Returns (memo, cited sources, abstained)."""
    try:
        digest, sources = pit.evidence(analyst, as_of, universe)
    except Exception as exc:  # noqa: BLE001 abstain, never fabricate
        log.error("%s evidence failed (%s); abstaining", analyst, exc)
        return abstain_memo(analyst, as_of, universe, "evidence unavailable"), [], True
    assert_no_lookahead(sources, as_of)
    if not sources:
        return (
            abstain_memo(analyst, as_of, universe, "no evidence before the cutoff"),
            [],
            True,
        )

    enc, decode, codes = _identity_masker_fns(masker, universe)
    system = HOUSE_STYLE + "\n\n" + PERSONAS[analyst] + SYSTEM_SUFFIX
    try:
        draft = llm.structured(
            system,
            build_prompt(analyst, as_of, codes, digest, sources, enc),
            _MemoDraft,
        )
    except Exception as exc:  # noqa: BLE001 abstain, never fabricate
        log.error("%s analyst failed (%s); abstaining", analyst, exc)
        return abstain_memo(analyst, as_of, universe, "model call failed"), [], True

    views = _clean_views(draft, set(universe), {s.id for s in sources}, decode)
    if not views:
        return abstain_memo(analyst, as_of, universe, "no usable view"), [], True
    memo = Memo(
        analyst=analyst,
        date=as_of,
        headline=draft.headline.strip(),
        body=draft.body.strip(),
        views=views,
    )
    cited = {sid for v in views for sid in v.sources}
    return memo, [s for s in sources if s.id in cited], False


def run_research(
    pit: Any, llm: Any, as_of: str, universe: list[str], masker: Masker | None = None
) -> tuple[list[Memo], list[Source], list[str]]:
    """Run the five analysts in parallel. Returns (memos, sources, abstained analyst names)."""
    with ThreadPoolExecutor(max_workers=len(ANALYSTS)) as pool:
        futures = [
            pool.submit(run_analyst_strict, pit, llm, a, as_of, list(universe), masker)
            for a in ANALYSTS
        ]
        results = [f.result() for f in futures]
    memos = [r[0] for r in results]
    by_id: dict[str, Source] = {}
    for _, srcs, _ in results:
        for s in srcs:
            by_id.setdefault(s.id, s)
    abstained = [a for a, r in zip(ANALYSTS, results, strict=True) if r[2]]
    return memos, list(by_id.values()), abstained
