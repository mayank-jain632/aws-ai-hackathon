"""Point-in-time snapshot for the leakage-safe walk-forward backtest (hub D15) in data/wf/.

Outputs (the older data/ snapshots and fetchers are untouched):
    data/wf/prices/<TICKER>.csv     date,open,high,low,close,volume (Yahoo chart API)
    data/wf/fred/macro.csv          date,series,value,available
    data/wf/sec/fundamentals.csv    same columns as data/sec/fundamentals.csv, through 2026-09-30
    data/wf/sec/filings_8k.csv      every 8-K / 8-K/A, 2025-01-01 .. 2026-10-22
    data/wf/sec/raw/                untouched SEC JSON responses (cache)

Run:  python data/fetch_wf.py
"""

from __future__ import annotations

import datetime as dt
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sec
from common import ALL_TICKERS, CIKS, DATA_DIR, UNIVERSE, USER_AGENT

OUT = DATA_DIR / "wf"
PRICE_START, PRICE_END = "2021-01-01", "2026-10-22"
FRED_START, FRED_END = "2019-01-01", "2026-10-22"
SEC_PERIOD_END, SEC_FILED_END = "2026-09-30", "2026-10-22"
K8_START = "2025-01-01"
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

MONTHLY_LAG = {"FEDFUNDS": 3, "UNRATE": 7, "CPIAUCSL": 15}  # same rules as data/fetch_fred.py
DAILY_SERIES = ["DGS10", "T10Y2Y", "VIXCLS", "BAMLH0A0HYM2", "USEPUINDXD", "DCOILWTICO", "DFEDTARU"]
FRED_ALL = ["FEDFUNDS", "CPIAUCSL", "UNRATE", *DAILY_SERIES]
DAILY_LAG_DAYS = {"DGS10": 0}  # DGS10 keeps data/fetch_fred.py's same-day rule; other daily series +1 day

ITEM_TITLES = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.04": "Mine Safety",
    "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate a Financial Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy a Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure/Appointment of Directors or Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.04": "Temporary Suspension of Trading Under Employee Benefit Plans",
    "5.05": "Amendments to the Registrant's Code of Ethics",
    "5.06": "Change in Shell Company Status",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "5.08": "Shareholder Director Nominations",
    "6.01": "ABS Informational and Computational Material",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


def curl_get(url: str, ua: str | None = None, retries: int = 5, timeout: int = 40) -> str:
    cmd = ["curl", "-s", "--http1.1", "-f", "-m", str(timeout)]
    if ua:
        cmd += ["-A", ua]
    last = ""
    for i in range(retries):
        p = subprocess.run([*cmd, url], check=False, capture_output=True, text=True)
        if p.returncode == 0 and p.stdout:
            return p.stdout
        last = f"rc={p.returncode} {p.stderr[:120]}"
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"curl failed for {url}: {last}")


# ------------------------------------------------------------------------------ prices


def fetch_prices(ticker: str) -> pd.DataFrame:
    p1 = int(dt.datetime(2021, 1, 1, tzinfo=dt.UTC).timestamp())
    p2 = int(dt.datetime(2026, 10, 24, tzinfo=dt.UTC).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit"
    )
    for attempt in range(4):
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
        if r.status_code == 200:
            break
        time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"yahoo {ticker}: HTTP {r.status_code}")
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(res["timestamp"], unit="s", utc=True)
            .tz_convert("America/New_York")
            .strftime("%Y-%m-%d"),
            "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
            "volume": q["volume"],
        }
    ).dropna(subset=["close", "open", "high", "low"])
    df = df[(df["date"] >= PRICE_START) & (df["date"] <= PRICE_END)].sort_values("date")
    df = df.drop_duplicates("date", keep="last").round({"open": 4, "high": 4, "low": 4, "close": 4})
    df["volume"] = df["volume"].fillna(0).astype("int64")
    return df


def run_prices() -> dict[str, pd.DataFrame]:
    (OUT / "prices").mkdir(parents=True, exist_ok=True)
    out = {}
    for t in ALL_TICKERS:
        df = fetch_prices(t)
        df.to_csv(OUT / "prices" / f"{t}.csv", index=False)
        out[t] = df
        print(f"  prices {t:5s} {df['date'].iloc[0]} .. {df['date'].iloc[-1]} {len(df)} rows")
        time.sleep(0.5)
    return out


# ---------------------------------------------------------------------------- FRED


def fetch_fred(series: str) -> pd.DataFrame:
    text = curl_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
    df = pd.read_csv(io.StringIO(text))
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna()
    dates = pd.to_datetime(df["date"])
    if series in MONTHLY_LAG:
        avail = dates + pd.DateOffset(months=1) + pd.Timedelta(days=MONTHLY_LAG[series])
    else:
        avail = dates + pd.Timedelta(days=DAILY_LAG_DAYS.get(series, 1))
    df["available"] = avail.dt.strftime("%Y-%m-%d")
    df["series"] = series
    return df[(df["date"] >= FRED_START) & (df["date"] <= FRED_END)][["date", "series", "value", "available"]]


def run_fred() -> pd.DataFrame:
    (OUT / "fred").mkdir(parents=True, exist_ok=True)
    frames = []
    for s in FRED_ALL:
        df = fetch_fred(s)
        frames.append(df)
        print(f"  fred {s:13s} {df['date'].iloc[0]} .. {df['date'].iloc[-1]} {len(df)} rows")
    macro = pd.concat(frames).sort_values(["date", "series"])
    macro.to_csv(OUT / "fred" / "macro.csv", index=False)
    return macro


# ----------------------------------------------------------------------------- SEC


def sec_get_json(url: str, cache: Path) -> dict:
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    data = json.loads(curl_get(url, ua=USER_AGENT, timeout=60))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.25)  # well under SEC's 10 req/s
    return data


def instant_series_wf(gaap: dict, concept: str) -> pd.Series:
    df = fetch_sec.usd_rows(gaap, concept)
    if df.empty:
        return pd.Series(dtype=float)
    if "start" in df:
        df = df[df["start"].isna()]
    df = df.sort_values("filed").drop_duplicates("end", keep="first")
    df = df[(df["end"] >= "2020-01-01") & (df["end"] <= SEC_FILED_END)]
    return df.set_index("end")["val"].sort_index()


def run_fundamentals() -> pd.DataFrame:
    (OUT / "sec" / "raw").mkdir(parents=True, exist_ok=True)
    fetch_sec.WINDOW_END = SEC_PERIOD_END  # parametrize the hard-coded end date
    fetch_sec.instant_series = instant_series_wf  # total_debt() resolves it from module globals
    frames = []
    for t in UNIVERSE:
        data = sec_get_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIKS[t]}.json",
            OUT / "sec" / "raw" / f"facts_{t}.json",
        )
        df = fetch_sec.build(t, data)
        df = df[df["filed"] <= SEC_FILED_END]
        frames.append(df)
        print(f"  fundamentals {t:5s} {df['period_end'].iloc[0]} .. {df['period_end'].iloc[-1]} {len(df)} q, "
              f"last filed {df['filed'].max()}")
    allf = pd.concat(frames)
    allf.to_csv(OUT / "sec" / "fundamentals.csv", index=False)
    return allf


def _rows_from_block(block: dict, ticker: str, cik: str) -> list[dict]:
    rows = []
    n = len(block.get("accessionNumber", []))
    for i in range(n):
        form = block["form"][i]
        filed = block["filingDate"][i]
        if form not in ("8-K", "8-K/A") or not (K8_START <= filed <= SEC_FILED_END):
            continue
        acc = block["accessionNumber"][i]
        items = [x.strip() for x in (block.get("items", [""] * n)[i] or "").split(",") if x.strip()]
        doc = block["primaryDocument"][i]
        rows.append(
            {
                "ticker": ticker,
                "filed": filed,
                "accepted": block["acceptanceDateTime"][i],
                "form": form,
                "items": ",".join(items),
                "item_titles": "; ".join(ITEM_TITLES.get(x, f"Item {x}") for x in items),
                "description": block["primaryDocDescription"][i] or "",
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}",
                "accession": acc,
            }
        )
    return rows


def run_8k() -> pd.DataFrame:
    rows: list[dict] = []
    for t in UNIVERSE:
        cik = CIKS[t]
        sub = sec_get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", OUT / "sec" / "raw" / f"sub_{t}.json")
        rows += _rows_from_block(sub["filings"]["recent"], t, cik)
        for f in sub["filings"].get("files", []):
            if f.get("filingTo", "9999") < K8_START:
                continue
            extra = sec_get_json(
                f"https://data.sec.gov/submissions/{f['name']}", OUT / "sec" / "raw" / f"sub_{t}_{f['name']}"
            )
            rows += _rows_from_block(extra, t, cik)
    df = pd.DataFrame(rows).drop_duplicates("accession").sort_values(["ticker", "filed", "accession"])
    df.to_csv(OUT / "sec" / "filings_8k.csv", index=False)
    return df


# ------------------------------------------------------------------------- checks


def acceptance(prices: dict[str, pd.DataFrame], macro: pd.DataFrame, fund: pd.DataFrame, k8: pd.DataFrame) -> bool:
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= cond
        print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")

    for t, df in prices.items():
        d = pd.to_datetime(df["date"])
        gap = int(d.diff().dt.days.max())
        check(f"prices {t}", not df["date"].duplicated().any() and gap <= 5,
              f"rows={len(df)} last={df['date'].iloc[-1]} max_gap_days={gap}")
    check("prices last date == 2026-10-22 for all", all(df["date"].iloc[-1] == "2026-10-22" for df in prices.values()))
    check("macro available >= date", bool((macro["available"] >= macro["date"]).all()), f"rows={len(macro)}")
    check("macro no dup (date,series)", not macro.duplicated(["date", "series"]).any())
    for s, g in macro.groupby("series"):
        print(f"      {s:13s} {g['date'].min()} .. {g['date'].max()} rows={len(g)} last_avail={g['available'].max()}")
    check("fundamentals filed >= period_end", bool((fund["filed"] >= fund["period_end"]).all()), f"rows={len(fund)}")
    check("fundamentals no dup (ticker,period_end)", not fund.duplicated(["ticker", "period_end"]).any())
    check("8-K accepted date >= filed date", bool((k8["accepted"].str[:10] >= k8["filed"]).all()), f"rows={len(k8)}")
    check("8-K no dup accession", not k8["accession"].duplicated().any())
    print("  8-K rows per ticker:", k8.groupby("ticker").size().to_dict())
    return ok


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    prices = run_prices()
    macro = run_fred()
    fund = run_fundamentals()
    k8 = run_8k()
    print("acceptance checks")
    if not acceptance(prices, macro, fund, k8):
        raise SystemExit("acceptance checks FAILED")


if __name__ == "__main__":
    main()
