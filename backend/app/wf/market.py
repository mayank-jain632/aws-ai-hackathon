"""ENGINE-ONLY market data accessors for the walk-forward backtest.

Agents, stages and the PIT layer must never import this module: it exposes the whole
price history including the future. backend/tests/wf/test_import_lint.py enforces that.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "wf"
BAR_COLUMNS = ["open", "high", "low", "close", "volume"]


def load_bars(data_dir: Path | None = None, tickers: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Daily OHLCV per ticker: DatetimeIndex ascending, columns open high low close volume."""
    root = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    prices = root / "prices"
    names = list(tickers) if tickers is not None else sorted(p.stem for p in prices.glob("*.csv"))
    out: dict[str, pd.DataFrame] = {}
    for t in names:
        path = prices / f"{t}.csv"
        if not path.exists():
            raise FileNotFoundError(f"no price file for {t}: {path}")
        df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
        out[t] = df[BAR_COLUMNS].astype(float)
    return out


def rf_annual_pct(index: pd.DatetimeIndex, data_dir: Path | None = None) -> pd.Series:
    """Fed funds rate (annual percent) known on each date, forward-filled by `available`."""
    root = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    macro = pd.read_csv(root / "fred" / "macro.csv", parse_dates=["date", "available"])
    ff = macro[macro["series"] == "FEDFUNDS"].sort_values("available")
    known = pd.Series(ff["value"].to_numpy(), index=pd.DatetimeIndex(ff["available"]))
    known = known[~known.index.duplicated(keep="last")]
    return known.reindex(pd.DatetimeIndex(index), method="ffill").rename("rf_annual_pct")
