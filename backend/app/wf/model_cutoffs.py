"""Documented training cutoffs of the Bedrock models agents can run on (hub D22 item 3).

A historical result is only "model-clean" if its first decision is after the cutoff of the
model that AUTHORED the weights. This table is that fact in one place. Values:

  * Opus 4.6, Haiku 4.5, Sonnet 4.6, Opus 4.8: the training-data cutoffs supplied by the team
    lead for this event (not independently verified). AWS's model card lists Opus 4.6's reliable
    knowledge cutoff as May 2025; we use the later training-data cutoff, which is the stricter test.
  * Our closed-book probe agreed for Opus 4.6: it recalled monthly Fed-rate, SPY and NVDA facts
    through Aug 2025 and abstained or erred afterwards (see `model_cutoff_report.md`, local).
  * Anything not listed (GPT-5.x, GPT-6.1 Sol, Opus 5.5, ...) is UNKNOWN. Unknown never counts as clean.
"""

from __future__ import annotations

TRAINING_CUTOFFS: dict[str, str] = {
    "claude-haiku-4-5": "2025-07",
    "claude-opus-4-6": "2025-08",
    "claude-sonnet-4-6": "2026-01",
    "claude-opus-4-8": "2026-01",
}


def training_cutoff(model_id: str | None) -> str | None:
    """Documented training cutoff (YYYY-MM) for a Bedrock model or profile id, else None."""
    if not model_id:
        return None
    for key, cutoff in TRAINING_CUTOFFS.items():
        if key in model_id:
            return cutoff
    return None
