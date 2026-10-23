"""FRED macro series via the public CSV download (no key).

https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS

Series: CPIAUCSL (CPI, monthly, index), FEDFUNDS (effective fed funds rate, monthly,
percent), DGS10 (10y Treasury yield, daily, percent), UNRATE (unemployment rate, monthly,
percent).

Output: data/fred/<SERIES>.csv with columns date,value,available and
data/fred/macro.csv, a long table with columns date,series,value,available.

`date` is FRED's observation date: for a monthly series it is the first day of the
month the value describes, which is BEFORE the value was published. `available` is a
conservative publication date that backend/app/data.py filters on (the no-look-ahead
rule), per series:
    FEDFUNDS  first business day of the next month   -> date + 1 month + 3 days
    UNRATE    first Friday of the next month          -> date + 1 month + 7 days
    CPIAUCSL  around the 10th-15th of the next month  -> date + 1 month + 15 days
    DGS10     same day (daily series)                 -> date
So at a 2023-01-01 cutoff the latest visible FEDFUNDS is November 2022 (published
Dec 1 2022) and the latest CPI is November 2022 (published Dec 13 2022).

Run:  python data/fetch_fred.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_DIR, END, FRED_SERIES, USER_AGENT  # noqa: E402

OUT = DATA_DIR / "fred"
# Pull from 2019 so agents can compute year-over-year changes at a 2021 cutoff.
FRED_START = "2019-01-01"

# Publication lag after the observation month, see module docstring.
RELEASE_LAG_DAYS = {"FEDFUNDS": 3, "UNRATE": 7, "CPIAUCSL": 15}


def fetch(series: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # FRED uses "." for missing
    df = df.dropna()
    dates = pd.to_datetime(df["date"])
    if series in RELEASE_LAG_DAYS:
        avail = dates + pd.DateOffset(months=1) + pd.Timedelta(days=RELEASE_LAG_DAYS[series])
    else:
        avail = dates
    df["available"] = avail.dt.strftime("%Y-%m-%d")
    return df[(df["date"] >= FRED_START) & (df["date"] <= END)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for s in FRED_SERIES:
        df = fetch(s)
        df.to_csv(OUT / f"{s}.csv", index=False)
        print(f"{s:9s} {df['date'].iloc[0]} .. {df['date'].iloc[-1]}  {len(df)} rows")
        frames.append(df.assign(series=s))
    macro = pd.concat(frames)[["date", "series", "value", "available"]].sort_values(["date", "series"])
    macro.to_csv(OUT / "macro.csv", index=False)
    print(f"wrote {OUT / 'macro.csv'} {macro.shape}")


if __name__ == "__main__":
    main()
