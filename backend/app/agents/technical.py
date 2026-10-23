"""Technical analyst: price action only (trend, moving averages, RSI, relative strength)."""

from backend.app.agents._analyst import run_analyst
from backend.app.agents.data_access import slice_prices
from backend.app.schema import Memo, Source

PERSONA = """You are the TECHNICAL analyst. You only look at price and volume: trend
versus the 50- and 200-day averages, breakouts and failed breakouts, RSI, drawdown from
highs, and relative strength against SPY. You do not care about earnings or the Fed
except as they show up in price. You respect trend and distrust narratives. Name the
level that would change your view."""


def run(universe: list[str], cutoff: str) -> tuple[Memo, list[Source]]:
    return run_analyst("technical", PERSONA, slice_prices, universe, cutoff)
