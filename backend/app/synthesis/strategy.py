"""Research memos + mandate + policy -> a frozen `StrategyInput`.

Deterministic seed first (`seed_from_memos`), then an optional single Bedrock call that may
tilt the seed but cannot escape the constraints: the result is always re-clamped and
renormalised in code before it reaches `Desk.register`.
"""

from __future__ import annotations

import logging
import math

from pydantic import BaseModel, Field

from backend.app.agents.base import StructuredOutputError, mock_mode, run_structured
from backend.app.agents.pm import seed_scores
from backend.app.desk import Policy, StrategyInput
from backend.app.schema import Memo
from backend.app.synthesis.schema import ResearchBundle, SeedDetail, SynthesisResult

log = logging.getLogger("synthesis.strategy")

MIN_WEIGHT = 0.02  # positions below this are dropped rather than registered as dust


class _Proposal(BaseModel):
    weights: dict[str, float] = Field(description="ticker -> fraction, long only, sums to 1")
    rationale: str = Field(max_length=3000)
    changes_my_mind: str = Field(max_length=1500)


def clamp_weights(raw: dict[str, float], max_position: float) -> tuple[dict[str, float], list[str]]:
    """Long-only, each <= max_position, sum == 1. Excess above the cap is redistributed
    pro rata to uncapped names; if everything is capped the sum stays below 1 and the
    caller decides (the desk will reject it). Returns (weights, clamped_tickers)."""
    w = {t: float(v) for t, v in raw.items() if v > 0}
    total = sum(w.values())
    if total <= 0:
        return {}, []
    w = {t: v / total for t, v in w.items()}
    clamped: set[str] = set()
    for _ in range(20):
        over = {t: v - max_position for t, v in w.items() if v > max_position + 1e-9}
        if not over:
            break
        excess = sum(over.values())
        for t in over:
            w[t] = max_position
            clamped.add(t)
        free = {t: v for t, v in w.items() if t not in clamped}
        free_total = sum(free.values())
        if free_total <= 0:
            break
        for t, v in free.items():
            w[t] += excess * v / free_total
    return {t: round(v, 6) for t, v in w.items()}, sorted(clamped)


def seed_from_memos(
    memos: list[Memo], universe: list[str], max_position: float
) -> tuple[dict[str, float], SeedDetail]:
    """1 + sum of signed convictions per ticker; names with net conviction <= -0.5 or no
    coverage are dropped; the rest renormalised and clamped."""
    scores = seed_scores(memos, universe)
    conviction = {t: round(sum(s.values()), 4) for t, s in scores.items()}
    dropped: dict[str, str] = {}
    raw: dict[str, float] = {}
    for t in universe:
        if not scores[t]:
            dropped[t] = "no analyst view"
        elif conviction[t] <= -0.5:
            dropped[t] = f"net avoid {conviction[t]:+.2f}"
        else:
            raw[t] = max(0.1, 1.0 + conviction[t])
    weights, clamped = clamp_weights(raw, max_position)
    small = [t for t, v in weights.items() if v < MIN_WEIGHT]
    for t in small:
        dropped[t] = f"below {MIN_WEIGHT:.0%} after clamping"
        weights.pop(t)
    if small:
        weights, clamped = clamp_weights(weights, max_position)
    return weights, SeedDetail(
        conviction=conviction, seed_weights=weights, dropped=dropped, clamped=clamped
    )


def _memo_text(m: Memo) -> str:
    views = "\n".join(
        f"  {v.ticker}: {v.stance} ({v.confidence:.2f}) {v.note} [{', '.join(v.sources)}]"
        for v in m.views
    )
    return f"=== {m.analyst.upper()} memo, {m.date}\n{m.headline}\n{m.body}\n{views}"


SYSTEM = """You are the strategy developer on a small desk. Five analysts have sent dated memos.
Turn them into one long-only target-weight book for a historical test starting at the cutoff.
Rules you cannot break (the backend re-checks them):
- Use only the memos and the mechanical seed provided. Everything is dated on or before the
  cutoff. No outside knowledge of what happened after the cutoff.
- Long only. Every weight is between 0 and max_position; the weights sum to exactly 1.
- Only tickers from the allowed list. Omit names you do not want.
- Prefer names where analysts agree; size down where they conflict.
- rationale: which memos drove the book and why, three to six sentences.
- changes_my_mind: concrete, checkable triggers that would change at least two positions.
You may deviate from the seed, but say why in the rationale."""


def refine_with_model(
    bundle: ResearchBundle, seed: dict[str, float], allowed: list[str], max_position: float
) -> _Proposal:
    user = (
        f"Cutoff: {bundle.cutoff}. Test end: {bundle.end}. max_position: {max_position}.\n"
        f"Allowed tickers: {', '.join(allowed)}\n"
        f"Mechanical seed (1 + signed conviction, clamped): {seed}\n"
        + (f"Research notes: {bundle.notes}\n" if bundle.notes else "")
        + "\n".join(_memo_text(m) for m in bundle.memos)
        + "\n\nReturn the book."
    )
    return run_structured(SYSTEM, user, _Proposal)


def synthesize(
    name: str,
    bundle: ResearchBundle,
    policy: Policy,
    mandate: dict | None,
    use_model: bool = True,
) -> SynthesisResult:
    """Build the frozen strategy input. Raises ValueError when the constraints leave no book."""
    allowed = [t for t in policy.universe if not mandate or t in mandate.get("universe", policy.universe)]
    max_position = policy.max_position
    if mandate and mandate.get("max_position"):
        max_position = min(max_position, float(mandate["max_position"]) / 100)
    if not allowed:
        raise ValueError("Mandate universe and desk policy universe do not overlap")
    if max_position * len(allowed) < 1 - 1e-9:
        raise ValueError(
            f"max_position {max_position:.2f} over {len(allowed)} names cannot reach full investment"
        )

    seed, detail = seed_from_memos(bundle.memos, allowed, max_position)
    if not seed:
        raise ValueError("Every allowed ticker was dropped by the research views")

    weights, rationale, trigger, model_used, note = seed, "", "", False, ""
    if use_model and not mock_mode():
        try:
            proposal = refine_with_model(bundle, seed, allowed, max_position)
            proposed = {t: v for t, v in proposal.weights.items() if t in allowed and t not in detail.dropped}
            clamped, _ = clamp_weights(proposed, max_position)
            if clamped and math.isclose(sum(clamped.values()), 1, abs_tol=1e-6):
                weights, rationale, trigger, model_used = clamped, proposal.rationale, proposal.changes_my_mind, True
            else:
                note = "model book could not satisfy the constraints; seed kept"
        except StructuredOutputError as exc:
            note = f"model output invalid ({str(exc)[:120]}); seed kept"
        except Exception as exc:  # noqa: BLE001 deliberate fallback: the seed is always valid
            note = f"model call failed ({type(exc).__name__}); seed kept"
            log.warning("synthesis model call failed: %s", exc)
    elif use_model:
        note = "mock mode: seed kept"

    if not rationale:
        drivers = ", ".join(f"{t} {detail.conviction[t]:+.2f}" for t in sorted(weights, key=lambda t: -weights[t]))
        rationale = (
            f"Mechanical book from {len(bundle.memos)} dated memos: weight is proportional to 1 plus the "
            f"sum of signed analyst convictions, net-avoid names dropped, capped at {max_position:.0%} per name. "
            f"Net conviction by position: {drivers}."
        )
    if not trigger:
        trigger = (
            "Re-run synthesis if any analyst flips a held name to avoid with confidence above 0.6, "
            "or if two analysts move a dropped name to long."
        )

    # fix rounding so the desk's sum check passes
    drift = round(1.0 - sum(weights.values()), 6)
    top = max(weights, key=weights.get)
    weights[top] = round(weights[top] + drift, 6)

    strategy = StrategyInput(
        name=name,
        weights=weights,
        cutoff=bundle.cutoff,
        end=bundle.end,
        rationale=rationale,
        memo_paths=bundle.memo_paths,
        changes_my_mind=trigger,
    )
    return SynthesisResult(
        strategy=strategy.model_dump(mode="json"), seed=detail, model_used=model_used, model_note=note
    )
