"""Walk-forward significance for a frozen target-weight book.

Runs the existing Desk engine (`backend.app.backtest.backtest`) from every monthly cutoff
in a range for a fixed horizon, and summarises how often and by how much the book beat
SPY and equal weight. Pure numbers in, pure numbers out; no model call.

Caveat baked into the result: consecutive windows overlap, so the excess returns are not
independent and the t-statistic overstates confidence. It is a robustness check on the
allocation, not a claim about a live rebalancing process.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from backend.app import backtest, data
from backend.app.schema import Weight
from backend.app.synthesis.schema import Significance, WindowResult

DEFAULT_HORIZON_DAYS = 182
MIN_WINDOWS = 6


def monthly_cutoffs(start: date, last: date) -> list[date]:
    out, y, m = [], start.year, start.month
    while date(y, m, 1) <= last:
        out.append(date(y, m, 1))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _normal_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def t_test(x: np.ndarray) -> tuple[float, float]:
    """One-sample t vs 0 with a normal tail approximation (no scipy dependency)."""
    n = len(x)
    if n < 2:
        return 0.0, 1.0
    sd = float(x.std(ddof=1))
    if sd == 0:
        return 0.0, 1.0
    t = float(x.mean() / (sd / math.sqrt(n)))
    return t, 2 * _normal_sf(abs(t))


def bootstrap_ci(x: np.ndarray, n_boot: int = 2000, seed: int = 7) -> tuple[float, float]:
    if len(x) < 2:
        v = float(x[0]) if len(x) else 0.0
        return v, v
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def walk_forward(
    strategy_id: str,
    weights: dict[str, float],
    first_cutoff: date | None = None,
    last_cutoff: date | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    closes: pd.DataFrame | None = None,
) -> Significance:
    universe = list(weights)
    if closes is None:
        closes = data.prices_full(universe + [data.REFERENCE])
    available_start = closes.index.min().date()
    available_end = closes.index.max().date()
    # need one year of history before the first cutoff so the earliest window is not degenerate
    first = first_cutoff or max(available_start + timedelta(days=365), date(available_start.year + 1, 1, 1))
    last = last_cutoff or (available_end - timedelta(days=horizon_days))
    cutoffs = [c for c in monthly_cutoffs(first, last) if c + timedelta(days=horizon_days) <= available_end]
    if len(cutoffs) < MIN_WINDOWS:
        raise ValueError(
            f"only {len(cutoffs)} walk-forward windows between {first} and {last}; need {MIN_WINDOWS}"
        )

    book = [Weight(ticker=t, weight=w, rationale="", changes_my_mind="", analyst_influence={}) for t, w in weights.items()]
    windows: list[WindowResult] = []
    for c in cutoffs:
        end = c + timedelta(days=horizon_days)
        equity, m = backtest.backtest(
            book, c.isoformat(), end.isoformat(), baseline="spy", universe=universe, closes=closes
        )
        p, s, e = equity.portfolio[-1] - 1, equity.spy[-1] - 1, equity.equal_weight[-1] - 1
        windows.append(
            WindowResult(
                cutoff=c.isoformat(),
                end=end.isoformat(),
                portfolio=round(p, 6),
                spy=round(s, 6),
                equal_weight=round(e, 6),
                excess_vs_spy=round(p - s, 6),
                excess_vs_equal=round(p - e, 6),
                max_drawdown=round(m.portfolio.max_drawdown, 6),
            )
        )

    ex_spy = np.array([w.excess_vs_spy for w in windows])
    ex_eq = np.array([w.excess_vs_equal for w in windows])
    t, p_value = t_test(ex_spy)
    lo, hi = bootstrap_ci(ex_spy)
    return Significance(
        strategy_id=strategy_id,
        horizon_days=horizon_days,
        n_windows=len(windows),
        hit_rate_vs_spy=round(float((ex_spy > 0).mean()), 4),
        hit_rate_vs_equal=round(float((ex_eq > 0).mean()), 4),
        mean_excess_vs_spy=round(float(ex_spy.mean()), 6),
        mean_excess_vs_equal=round(float(ex_eq.mean()), 6),
        t_stat_vs_spy=round(t, 4),
        p_value_vs_spy=round(p_value, 4),
        ci95_excess_vs_spy=(round(lo, 6), round(hi, 6)),
        worst_drawdown=round(min(w.max_drawdown for w in windows), 6),
        windows=windows,
        limitations=(
            f"{len(windows)} overlapping {horizon_days}-day windows from monthly cutoffs; the same frozen "
            "weights are held in every window, so this measures robustness of the allocation, not of a "
            "rebalancing process. Overlap inflates the t-statistic. Price returns only: no dividends, no costs. "
            "The model may remember this period; see the masked-ticker audit."
        ),
    )
