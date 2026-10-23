"""Trading-calendar helpers derived from a price index (no external holiday table)."""

from __future__ import annotations

import pandas as pd


def decision_dates(index: pd.DatetimeIndex, first: str, last: str) -> list[str]:
    """Last trading day of each ISO week, for weeks whose last session lies in [first, last].

    The week is judged on the FULL index, so a Friday holiday yields Thursday, and a window
    that cuts a week in the middle does not invent a decision on the cut.
    """
    idx = pd.DatetimeIndex(index).sort_values().unique()
    if len(idx) == 0:
        return []
    iso = idx.isocalendar()
    key = iso["year"].astype(str).str.cat(iso["week"].astype(str).str.zfill(2), sep="-")
    week_last = pd.Series(idx, index=idx).groupby(key.to_numpy()).max()
    lo, hi = pd.Timestamp(first), pd.Timestamp(last)
    picked = sorted(d for d in week_last if lo <= d <= hi)
    return [d.strftime("%Y-%m-%d") for d in picked]


def next_session(index: pd.DatetimeIndex, date: str) -> str | None:
    """First session strictly after ``date`` (None when the index ends first)."""
    idx = pd.DatetimeIndex(index).sort_values()
    pos = idx.searchsorted(pd.Timestamp(date), side="right")
    return idx[pos].strftime("%Y-%m-%d") if pos < len(idx) else None
