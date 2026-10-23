"""GDELT tone for the ten company names and three event themes.

Source: GDELT DOC 2.0 API, mode=timelinetone, which returns the daily average tone
(GKG V1.5 tone, roughly -10 .. +10, negative is bad news) of online news matching
a query, for a date range:
    https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=timelinetone
        &startdatetime=20210101000000&enddatetime=20250630235959&format=csv

The raw GKG files (one zip every 15 minutes since 2015) would be tens of gigabytes
for this window, so the API's daily summary is what we use. The API rate-limits to
one request every 5 seconds and throttles an address for minutes after a burst; the
script sleeps 7 s between queries, backs off 30 s, 60 s, ... on 429, and resumes from
data/gdelt/raw/ so a rerun never repeats a finished subject. Windows are fetched one
calendar year at a time.

Because the API was unreliable on the day of the hackathon, agents read the
hand-curated data/gdelt/curated_events.csv (dated headlines with a tone score on the
same -10..+10 scale, written from well-known public events) through
backend.app.data.events(). The daily tone from this script, when present, is exposed
separately as backend.app.data.tone().

Output: data/gdelt/tone.csv with columns date,subject,kind,tone
    kind = "company" (subject = ticker) or "theme"
    (subject = ukraine_energy, china_reopening, chip_export_controls).
Also data/gdelt/raw/<subject>.csv, the untouched API responses.

Run:  python data/fetch_gdelt.py
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_DIR, END, START, USER_AGENT  # noqa: E402

OUT = DATA_DIR / "gdelt"
RAW = OUT / "raw"
API = "https://api.gdeltproject.org/api/v2/doc/doc"

THEMES = {
    "ukraine_energy": '(Ukraine OR Russia) (gas OR oil OR energy OR pipeline OR sanctions)',
    "china_reopening": 'China ("zero-COVID" OR "zero COVID" OR reopening OR lockdown OR reopen)',
    "chip_export_controls": '("export controls" OR "export control" OR "chip ban") (China OR Nvidia OR semiconductor)',
}

# A bare company name pulls in noise ("apple pie"); qualify the ambiguous ones.
COMPANY_QUERIES = {
    "AAPL": '"Apple" (iPhone OR "Tim Cook" OR "Apple Inc")',
    "MSFT": '"Microsoft"',
    "NVDA": '"Nvidia"',
    "AMZN": '"Amazon" (AWS OR Bezos OR Jassy OR "Amazon.com" OR retailer)',
    "GOOGL": '"Google" (Alphabet OR Pichai OR search OR Android)',
    "JPM": '("JPMorgan" OR "JP Morgan")',
    "XOM": '("Exxon" OR "ExxonMobil")',
    "UNH": '"UnitedHealth"',
    "PG": '"Procter & Gamble"',
    "CAT": '"Caterpillar Inc"',
}


def query_window(q: str, start: str, end: str) -> pd.DataFrame:
    params = {
        "query": q,
        "mode": "timelinetone",
        "startdatetime": start.replace("-", "") + "000000",
        "enddatetime": end.replace("-", "") + "235959",
        "format": "csv",
    }
    for attempt in range(8):
        r = requests.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=60)
        if r.status_code == 429 or "limit requests" in r.text[:200]:
            wait = 30 * (attempt + 1)  # GDELT throttles an address for minutes after a burst
            print(f"  429 from GDELT, waiting {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code != 200 or not r.text.lstrip("﻿").startswith("Date"):
            raise RuntimeError(f"GDELT {r.status_code}: {r.text[:200]!r}")
        df = pd.read_csv(io.StringIO(r.text.lstrip("﻿")))
        df.columns = ["date", "series", "tone"][: len(df.columns)]
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        time.sleep(7)
        return df
    raise RuntimeError("GDELT rate limit not clearing")


def query(q: str) -> pd.DataFrame:
    frames = []
    for year in range(2021, 2026):
        s = f"{year}-01-01" if year > 2021 else START
        e = f"{year}-12-31" if year < 2025 else END
        frames.append(query_window(q, s, e))
    df = pd.concat(frames).drop_duplicates("date").sort_values("date")
    return df[["date", "tone"]]


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    frames = []
    subjects = [(t, "company", q) for t, q in COMPANY_QUERIES.items()] + [
        (t, "theme", q) for t, q in THEMES.items()
    ]
    for subject, kind, q in subjects:
        raw = RAW / f"{subject}.csv"
        if raw.exists():
            df = pd.read_csv(raw, dtype={"date": str})
        else:
            df = query(q)
            df.to_csv(raw, index=False)
        df = df.assign(subject=subject, kind=kind)
        frames.append(df)
        print(
            f"{subject:22s} {kind:8s} {df['date'].iloc[0]} .. {df['date'].iloc[-1]}  {len(df)} days"
            f"  mean tone {df['tone'].mean():+.2f}",
            flush=True,
        )
    allf = pd.concat(frames)[["date", "subject", "kind", "tone"]].sort_values(["date", "subject"])
    allf["tone"] = allf["tone"].round(3)
    allf.to_csv(OUT / "tone.csv", index=False)
    print(f"wrote {OUT / 'tone.csv'} {allf.shape}")


if __name__ == "__main__":
    main()
