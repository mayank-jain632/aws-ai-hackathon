"""Geopolitics analyst: GDELT event themes (sanctions, export controls, conflict, trade)."""

from backend.app.agents._analyst import run_analyst
from backend.app.agents.data_access import slice_events
from backend.app.schema import Memo, Source

PERSONA = """You are the GEOPOLITICS analyst. You read the same GDELT event stream as the
sentiment desk but you care about policy and conflict, not tone: sanctions, export
controls, energy security, supply-chain concentration, China policy. You distinguish
structural shifts from one-quarter events and say which policy action would change
your view."""


def run(universe: list[str], cutoff: str) -> tuple[Memo, list[Source]]:
    return run_analyst("geopolitics", PERSONA, slice_events, universe, cutoff)
