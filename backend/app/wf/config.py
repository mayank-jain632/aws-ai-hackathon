"""Frozen experiment definition for the leakage-safe walk-forward backtest (see hub D15).

Every number that defines the experiment lives here so a run manifest can hash it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WfConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Model clock: Claude Opus 4.6 has a documented training cutoff of 2025-08. The first
    # decision is the first month after that plus one buffer month (2025-10).
    model_id: str = "us.anthropic.claude-opus-4-6-v1"
    model_training_cutoff: str = "2025-08"
    clean_start: str = "2025-10-01"  # decisions before this are CONTAMINATED
    first_decision: str = "2025-10-03"  # a Friday close
    last_decision: str = "2026-10-16"  # a Friday close
    mark_end: str = "2026-10-22"  # last complete data day
    dev_decisions: int = 8  # first N decisions are the dev window; the rest are the frozen test

    universe: tuple[str, ...] = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "XOM", "UNH", "PG", "CAT")
    reference: str = "SPY"

    # Engine (daily bars, long-only).
    start_cash: float = 1_000_000.0
    slippage_bps: float = 5.0  # applied against us on every fill
    volume_participation_cap: float = 0.05  # max share of a day's volume per order
    rebalance_band: float = 0.01  # ignore target-weight changes smaller than this (fraction of equity)

    # Strategy validator limits.
    max_weight: float = 0.25
    min_stop_pct: float = 0.02
    max_stop_pct: float = 0.20
    min_target_pct: float = 0.03

    temperature: float = 0.0
    max_tokens: int = 4000
