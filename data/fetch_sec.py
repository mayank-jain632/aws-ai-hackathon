"""Quarterly revenue, net income and total debt for the universe from SEC XBRL data.

The plan names the SEC Financial Statement Data Sets
(https://www.sec.gov/dera/data/financial-statement-data-sets). Those are one ~125 MB zip
per quarter, 18 quarters for 2021Q1..2025Q2, about 2.2 GB, and each num.txt has to be
scanned for ten CIKs. The same XBRL facts, tagged with the same us-gaap concepts and
filing dates, are served per company by the SEC "companyfacts" API, which is the
source this script uses:

    https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json

SEC asks for a descriptive User-Agent and at most 10 requests per second.

A fact is attributed to the date it became public (the filing date, `filed`), which is
the date backend/app/data.py filters on. That is the no-look-ahead rule: a quarter's
numbers are only visible to an agent once the 10-Q or 10-K was filed.

Output: data/sec/fundamentals.csv with columns
    ticker, fy, fp, period_end, filed, form, revenue, net_income, total_debt, concept_*
one row per (ticker, fiscal quarter), period_end in 2021-01-01 .. 2025-06-30, values in
USD. Revenue and net income are three-month figures; Q4 is derived as FY minus Q1..Q3
when the filer reports only a full-year value in the 10-K. total_debt is the latest
consolidated debt balance reported on or before period_end (long-term debt including
the current portion, plus short-term borrowings where tagged).
Also data/sec/raw/<TICKER>.json, the untouched companyfacts response.

Run:  python data/fetch_sec.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CIKS, DATA_DIR, UNIVERSE, USER_AGENT  # noqa: E402

OUT = DATA_DIR / "sec"
RAW = OUT / "raw"

# Filers switch between these over the years (Alphabet uses Revenues some years and
# RevenueFromContractWithCustomer... others), so facts are merged across all of them
# and, per period, the earliest-filed fact wins.
REVENUE = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",  # banks report net revenue
]
NET_INCOME = ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]
# Debt is an instant (balance sheet) value. Tags that already include the current
# portion are listed in DEBT_INCLUDES_CURRENT; the others get short-term pieces added.
DEBT_CANDIDATES = [
    "LongTermDebt",
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
    "LongTermDebtNoncurrent",
    "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
]
DEBT_INCLUDES_CURRENT = {
    "LongTermDebt",
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
}
DEBT_ST = ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "CommercialPaper"]

WINDOW_START, WINDOW_END = "2021-01-01", "2025-06-30"
FORMS = ["10-K", "10-Q", "10-K/A", "10-Q/A"]


def facts(cik: str) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    return r.json()


def usd_rows(gaap: dict, concept: str) -> pd.DataFrame:
    rows = gaap.get(concept, {}).get("units", {}).get("USD", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[df["form"].isin(FORMS)].copy()
    df["concept"] = concept
    return df


def quarterly_flow(gaap: dict, concepts: list[str]) -> pd.DataFrame:
    """Three-month values keyed by period end (duration facts), merged across concepts.

    For each (start, end) the earliest-filed fact wins, so a restatement in a later
    filing never moves the "filed" date forward. Q4 is derived as FY minus the three
    prior quarters when no three-month Q4 fact exists.
    """
    frames = [usd_rows(gaap, c) for c in concepts]
    frames = [f for f in frames if not f.empty and "start" in f]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames).dropna(subset=["start"])
    df["days"] = (pd.to_datetime(df["end"]) - pd.to_datetime(df["start"])).dt.days
    df = df.sort_values("filed").drop_duplicates(["start", "end"], keep="first")
    q = df[(df["days"] > 80) & (df["days"] < 100)]
    fy = df[(df["days"] > 350) & (df["days"] < 380)]
    cols = ["end", "start", "val", "filed", "form", "fy", "fp", "concept"]
    out = q[cols].copy()
    derived = []
    for _, y in fy.iterrows():
        if (q["end"] == y["end"]).any():
            continue
        prior = q[(q["end"] > y["start"]) & (q["end"] < y["end"])]
        if len(prior) == 3:
            derived.append(
                {
                    "end": y["end"],
                    "start": prior["end"].max(),
                    "val": y["val"] - prior["val"].sum(),
                    "filed": y["filed"],
                    "form": y["form"],
                    "fy": y["fy"],
                    "fp": "Q4",
                    "concept": y["concept"] + " (FY minus Q1-Q3)",
                }
            )
    if derived:
        out = pd.concat([out, pd.DataFrame(derived)])
    out = out.sort_values("filed").drop_duplicates("end", keep="first")
    out = out[(out["end"] >= WINDOW_START) & (out["end"] <= WINDOW_END)]
    return out.sort_values("end")


def instant_series(gaap: dict, concept: str) -> pd.Series:
    """Balance-sheet value keyed by period end (instant facts, earliest filing wins)."""
    df = usd_rows(gaap, concept)
    if df.empty:
        return pd.Series(dtype=float)
    if "start" in df:
        df = df[df["start"].isna()]
    df = df.sort_values("filed").drop_duplicates("end", keep="first")
    df = df[(df["end"] >= "2020-01-01") & (df["end"] <= "2025-07-15")]
    return df.set_index("end")["val"].sort_index()


def total_debt(gaap: dict) -> tuple[pd.Series, str]:
    """Pick the debt tag that is the consolidated total.

    Among the candidate tags with at least four balance dates, a total is never smaller
    than its components, so the one with the largest median wins. Quarterly coverage
    breaks ties.
    """
    best, best_key, best_name = pd.Series(dtype=float), (0, 0.0), ""
    for c in DEBT_CANDIDATES:
        s = instant_series(gaap, c)
        if len(s) < 4:
            continue
        key = (1 if len(s) >= 12 else 0, float(s.median()))
        if key > best_key:
            best, best_key, best_name = s, key, c
    if best.empty:
        return best, ""
    if best_name in DEBT_INCLUDES_CURRENT:
        return best, best_name
    for c in DEBT_ST:
        st = instant_series(gaap, c)
        if len(st) >= 4:
            return best.add(st.reindex(best.index).fillna(0), fill_value=0), f"{best_name}+{c}"
    return best, best_name


def build(ticker: str, data: dict) -> pd.DataFrame:
    gaap = data["facts"]["us-gaap"]
    rev = quarterly_flow(gaap, REVENUE)
    ni = quarterly_flow(gaap, NET_INCOME)
    debt, c_debt = total_debt(gaap)
    if rev.empty or ni.empty:
        raise RuntimeError(f"{ticker}: revenue or net income missing")
    df = rev.rename(columns={"val": "revenue", "end": "period_end", "concept": "concept_revenue"})
    ni2 = ni.rename(columns={"val": "net_income", "end": "period_end", "concept": "concept_net_income"})
    df = df.merge(ni2[["period_end", "net_income", "filed", "concept_net_income"]],
                  on="period_end", how="inner", suffixes=("", "_ni"))
    df["filed"] = df[["filed", "filed_ni"]].max(axis=1)  # visible once both are public
    # Debt as of period_end: the latest balance reported on or before it. Caterpillar
    # only tags consolidated debt in the 10-K, so its quarters carry the prior year end.
    if debt.empty:
        df["total_debt"] = float("nan")
    else:
        df["total_debt"] = [
            debt[debt.index <= pe].iloc[-1] if (debt.index <= pe).any() else float("nan")
            for pe in df["period_end"]
        ]
    df["ticker"] = ticker
    df["concept_total_debt"] = c_debt
    cols = [
        "ticker", "fy", "fp", "period_end", "filed", "form", "revenue", "net_income",
        "total_debt", "concept_revenue", "concept_net_income", "concept_total_debt",
    ]
    df["fy"] = df["fy"].astype("Int64")
    return df[cols].sort_values("period_end")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    frames = []
    for t in UNIVERSE:
        raw = RAW / f"{t}.json"
        if raw.exists():
            data = json.loads(raw.read_text(encoding="utf-8"))
        else:
            data = facts(CIKS[t])
            raw.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(0.2)
        df = build(t, data)
        frames.append(df)
        d22 = df[df["period_end"] <= "2022-12-31"]["total_debt"].iloc[-1]
        print(
            f"{t:5s} {data['entityName'][:24]:24s} {df['period_end'].iloc[0]} .. {df['period_end'].iloc[-1]}"
            f"  {len(df):2d} q  debt@FY22={d22/1e9:6.1f}B  via {df['concept_total_debt'].iloc[0]}"
        )
    allf = pd.concat(frames)
    allf.to_csv(OUT / "fundamentals.csv", index=False)
    print(f"wrote {OUT / 'fundamentals.csv'} {allf.shape}")


if __name__ == "__main__":
    main()
