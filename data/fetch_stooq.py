"""Daily OHLCV for the universe plus SPY.

Primary source: Stooq daily CSV, https://stooq.com/q/d/l/?s=aapl.us&i=d (no key).
As of 2026-10-23 Stooq serves a JavaScript proof-of-work page to non-browser clients
instead of the CSV. This script detects that and falls back to the Yahoo Finance chart
endpoint, which returns the same daily bars and also needs no key:
https://query1.finance.yahoo.com/v8/finance/chart/AAPL?period1=..&period2=..&interval=1d

Output: data/prices/<TICKER>.csv with columns date,open,high,low,close,volume
(one row per trading day, ascending), plus data/prices/close.csv, a wide table of
closes with one column per ticker. Closes are split-adjusted but not dividend-adjusted
on both sources, so the backtest is a price-return backtest.

Run:  python data/fetch_stooq.py
"""

from __future__ import annotations

import datetime as dt
import io
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ALL_TICKERS, DATA_DIR, END, START  # noqa: E402

OUT = DATA_DIR / "prices"
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def from_stooq(ticker: str) -> pd.DataFrame | None:
    url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
    r = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
    if r.status_code != 200 or not r.text.startswith("Date,"):
        return None  # challenge page, rate limit, or unknown symbol
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.lower() for c in df.columns]
    return df[["date", "open", "high", "low", "close", "volume"]]


def from_yahoo(ticker: str) -> pd.DataFrame | None:
    p1 = int(dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime(2025, 7, 2, tzinfo=dt.timezone.utc).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit"
    )
    r = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
    if r.status_code != 200:
        return None
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(res["timestamp"], unit="s", utc=True)
            .tz_convert("America/New_York")
            .strftime("%Y-%m-%d"),
            "open": q["open"],
            "high": q["high"],
            "low": q["low"],
            "close": q["close"],
            "volume": q["volume"],
        }
    )
    return df.dropna(subset=["close"])


def fetch(ticker: str) -> tuple[pd.DataFrame, str]:
    df = from_stooq(ticker)
    if df is not None:
        return df, "stooq"
    df = from_yahoo(ticker)
    if df is None:
        raise RuntimeError(f"no price data for {ticker}")
    return df, "yahoo"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    closes = {}
    for t in ALL_TICKERS:
        df, src = fetch(t)
        df = df[(df["date"] >= START) & (df["date"] <= END)].sort_values("date")
        df = df.round({"open": 4, "high": 4, "low": 4, "close": 4})
        df["volume"] = df["volume"].astype("Int64")
        df.to_csv(OUT / f"{t}.csv", index=False)
        closes[t] = df.set_index("date")["close"]
        print(f"{t:5s} {src:6s} {df['date'].iloc[0]} .. {df['date'].iloc[-1]}  {len(df)} rows")
        time.sleep(0.5)
    wide = pd.DataFrame(closes).sort_index()
    wide.index.name = "date"
    wide.to_csv(OUT / "close.csv")
    print(f"wrote {OUT / 'close.csv'} {wide.shape}")


if __name__ == "__main__":
    main()
