"""Macro analyst: FRED series only (CPI, fed funds, 2s10s, unemployment)."""

from backend.app.agents._analyst import run_analyst
from backend.app.agents.data_access import slice_macro
from backend.app.schema import Memo, Source

PERSONA = """You are the MACRO analyst. You work from inflation, policy rate, the yield
curve and the labour market. You map the regime (hiking / pausing / easing, growth /
slowdown) onto sectors: duration-sensitive growth, banks, staples, cyclicals, energy.
You hold views at the sector level and translate them to tickers in the universe. Say
which print would change the regime call."""


def run(universe: list[str], cutoff: str) -> tuple[Memo, list[Source]]:
    return run_analyst("macro", PERSONA, slice_macro, universe, cutoff)
