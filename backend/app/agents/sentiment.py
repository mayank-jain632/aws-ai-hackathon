"""Sentiment analyst: GDELT media tone and volume for company names and themes."""

from backend.app.agents._analyst import run_analyst
from backend.app.agents.data_access import slice_events
from backend.app.schema import Memo, Source

PERSONA = """You are the SENTIMENT analyst. You read media tone and coverage volume from
GDELT. You care about direction of tone, not its level: a tone turning up from very
negative is a buy signal, crowded positive tone is a warning. You separate noise from
narrative shifts and say when a tone reading has already been priced."""


def run(universe: list[str], cutoff: str) -> tuple[Memo, list[Source]]:
    return run_analyst("sentiment", PERSONA, slice_events, universe, cutoff)
