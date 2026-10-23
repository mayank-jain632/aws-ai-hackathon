"""Fundamentals analyst: SEC filings only (revenue, margins, cash flow, balance sheet)."""

from backend.app.agents._analyst import run_analyst
from backend.app.agents.data_access import slice_fundamentals
from backend.app.schema import Memo, Source

PERSONA = """You are the FUNDAMENTALS analyst. You read 10-K and 10-Q filings: revenue
growth, segment mix, margins, operating cash flow, capex, leverage. You pay for durable
earnings power and refuse to pay for cash-flow compression. Quote the numbers. Say which
line item would change your view."""


def run(universe: list[str], cutoff: str) -> tuple[Memo, list[Source]]:
    return run_analyst("fundamentals", PERSONA, slice_fundamentals, universe, cutoff)
