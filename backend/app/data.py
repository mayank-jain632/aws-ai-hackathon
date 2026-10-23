"""Loaders for the committed snapshots under data/.

Every loader that an agent may call takes a ``cutoff`` (ISO date string) and drops rows
dated after it before returning. That is the only place the no-look-ahead rule is
enforced, so agents must go through these functions and never read data/ directly.

``prices_full`` and ``last_close`` are for the backtest and the tape fallback only;
they see the whole history and must not be passed to an agent.

All CSVs are produced by the data/fetch_*.py scripts (see data/README.md).
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def _common():
    spec = importlib.util.spec_from_file_location("desk_data_common", DATA_DIR / "common.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_c = _common()
UNIVERSE: list[str] = list(_c.UNIVERSE)
REFERENCE: str = _c.REFERENCE
ALL_TICKERS: list[str] = list(_c.ALL_TICKERS)


def _iso(cutoff: str | pd.Timestamp) -> str:
    return pd.Timestamp(cutoff).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- prices


@lru_cache(maxsize=1)
def _close_wide() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "prices" / "close.csv", index_col="date", parse_dates=["date"])
    return df.sort_index()


@lru_cache(maxsize=16)
def _ohlcv(ticker: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "prices" / f"{ticker}.csv", parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def prices(cutoff: str, tickers: list[str] | None = None) -> pd.DataFrame:
    """Daily closes, one column per ticker, DatetimeIndex, rows dated <= cutoff.

    Columns default to the universe plus SPY. Closes are split-adjusted price data
    (no dividends), so returns derived from them are price returns.
    """
    cols = tickers or ALL_TICKERS
    df = _close_wide()
    return df.loc[df.index <= pd.Timestamp(cutoff), cols].copy()


def ohlcv(ticker: str, cutoff: str) -> pd.DataFrame:
    """Daily open/high/low/close/volume for one ticker, rows dated <= cutoff."""
    df = _ohlcv(ticker)
    return df[df["date"] <= pd.Timestamp(cutoff)].copy()


def prices_full(tickers: list[str] | None = None) -> pd.DataFrame:
    """Daily closes with no cutoff. Backtest only; never hand this to an agent."""
    cols = tickers or ALL_TICKERS
    return _close_wide()[cols].copy()


def last_close() -> dict[str, dict[str, float | str]]:
    """Most recent close per ticker, for the tape fallback when the socket is down.

    Returns {ticker: {"date": "YYYY-MM-DD", "close": float, "change_pct": float}} where
    change_pct is the last day-over-day move in percent.
    """
    df = _close_wide()
    out: dict[str, dict[str, float | str]] = {}
    for t in df.columns:
        s = df[t].dropna()
        prev = float(s.iloc[-2]) if len(s) > 1 else float("nan")
        last = float(s.iloc[-1])
        out[t] = {
            "date": s.index[-1].strftime("%Y-%m-%d"),
            "close": round(last, 4),
            "change_pct": round((last / prev - 1) * 100, 4) if prev == prev else 0.0,
        }
    return out


# ---------------------------------------------------------------------- fundamentals


@lru_cache(maxsize=1)
def _fundamentals() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "sec" / "fundamentals.csv", parse_dates=["period_end", "filed"])
    return df.sort_values(["ticker", "period_end"]).reset_index(drop=True)


def fundamentals(cutoff: str, tickers: list[str] | None = None) -> pd.DataFrame:
    """Quarterly revenue, net income and total debt from SEC XBRL filings.

    A row is visible only once its 10-Q/10-K was *filed* on or before cutoff (column
    ``filed``), not merely once the quarter ended. Columns: ticker, fy, fp, period_end,
    filed, form, revenue, net_income, total_debt (USD), concept_* (the us-gaap tags used).
    """
    df = _fundamentals()
    df = df[df["filed"] <= pd.Timestamp(cutoff)]
    if tickers:
        df = df[df["ticker"].isin(tickers)]
    return df.copy()


# ----------------------------------------------------------------------------- macro


@lru_cache(maxsize=1)
def _macro() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "fred" / "macro.csv", parse_dates=["date", "available"])
    return df.sort_values(["date", "series"]).reset_index(drop=True)


def macro(cutoff: str, wide: bool = True) -> pd.DataFrame:
    """FRED series CPIAUCSL, FEDFUNDS, DGS10, UNRATE that were *published* by cutoff.

    FRED dates a monthly value by the month it describes (1st of the month), weeks
    before it is released, so this filters on the ``available`` column that
    data/fetch_fred.py derives from each series' release schedule, not on ``date``.
    At a 2023-01-01 cutoff the newest FEDFUNDS and CPI rows are November 2022.

    wide=True returns a DatetimeIndex frame (observation date) with one column per
    series, NaN where a series has no observation that day. wide=False returns the
    long table date,series,value,available.
    """
    df = _macro()
    df = df[df["available"] <= pd.Timestamp(cutoff)]
    if not wide:
        return df.copy()
    return df.pivot(index="date", columns="series", values="value").sort_index()


def fedfunds_at(cutoff: str) -> float:
    """Effective fed funds rate (annual, percent) known at cutoff: the latest FEDFUNDS
    observation published on or before cutoff. Used as the Sharpe risk-free rate."""
    df = _macro()
    s = df[(df["series"] == "FEDFUNDS") & (df["available"] <= pd.Timestamp(cutoff))]
    if s.empty:
        raise ValueError(f"no FEDFUNDS observation on or before {cutoff}")
    return float(s.sort_values("date")["value"].iloc[-1])


# ---------------------------------------------------------------------------- events


@lru_cache(maxsize=1)
def _events() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "gdelt" / "tone.csv", parse_dates=["date"])
    return df.sort_values(["date", "subject"]).reset_index(drop=True)


def events(cutoff: str, subjects: list[str] | None = None) -> pd.DataFrame:
    """GDELT daily average news tone, rows dated <= cutoff.

    Columns: date, subject, kind, tone. kind is "company" (subject = ticker) or
    "theme" (ukraine_energy, china_reopening, chip_export_controls). Tone is the GDELT
    GKG average tone, roughly -10..+10, negative means more negative coverage.
    """
    df = _events()
    df = df[df["date"] <= pd.Timestamp(cutoff)]
    if subjects:
        df = df[df["subject"].isin(subjects)]
    return df.copy()


__all__ = [
    "UNIVERSE",
    "REFERENCE",
    "ALL_TICKERS",
    "prices",
    "ohlcv",
    "prices_full",
    "last_close",
    "fundamentals",
    "macro",
    "fedfunds_at",
    "events",
]
