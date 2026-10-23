"""Tiny synthetic data dirs for PIT tests (no network)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TICKERS = ["AAA", "BBB"]


def make_data_dir(root: Path, end: str = "2024-12-31") -> Path:
    (root / "prices").mkdir(parents=True)
    (root / "fred").mkdir()
    (root / "sec").mkdir()
    days = pd.bdate_range("2023-01-02", end)
    rng = np.random.default_rng(0)
    for i, t in enumerate([*TICKERS, "SPY"]):
        close = 100 + i * 10 + np.cumsum(rng.normal(0, 1, len(days)))
        df = pd.DataFrame(
            {"date": days.strftime("%Y-%m-%d"), "open": close - 0.2, "high": close + 1, "low": close - 1,
             "close": close, "volume": 1_000_000 + 1000 * np.arange(len(days))}
        )
        df.to_csv(root / "prices" / f"{t}.csv", index=False)
    macro = []
    for m in pd.date_range("2022-01-01", "2024-12-01", freq="MS"):
        for s, lag in (("FEDFUNDS", 3), ("CPIAUCSL", 15), ("UNRATE", 7)):
            avail = m + pd.DateOffset(months=1) + pd.Timedelta(days=lag)
            macro.append((m.strftime("%Y-%m-%d"), s, 4.0 + m.month * 0.1, avail.strftime("%Y-%m-%d")))
    for d in days:
        for s in ("DGS10", "T10Y2Y", "VIXCLS", "BAMLH0A0HYM2", "USEPUINDXD", "DCOILWTICO"):
            avail = d + pd.Timedelta(days=1)
            macro.append((d.strftime("%Y-%m-%d"), s, 20.0 + d.month, avail.strftime("%Y-%m-%d")))
    pd.DataFrame(macro, columns=["date", "series", "value", "available"]).to_csv(root / "fred" / "macro.csv", index=False)
    fund = []
    for t in TICKERS:
        for k, pe in enumerate(pd.date_range("2022-03-31", "2024-09-30", freq="QE")):
            filed = (pe + pd.Timedelta(days=30)).strftime("%Y-%m-%d")
            fund.append((t, pe.year, f"Q{pe.quarter}", pe.strftime("%Y-%m-%d"), filed, "10-Q",
                         1e9 + k * 1e7, 1e8 + k * 1e6, 5e8, "r", "n", "d"))
    pd.DataFrame(fund, columns=["ticker", "fy", "fp", "period_end", "filed", "form", "revenue", "net_income",
                                "total_debt", "concept_revenue", "concept_net_income",
                                "concept_total_debt"]).to_csv(root / "sec" / "fundamentals.csv", index=False)
    k8 = []
    for t in TICKERS:
        for n, (filed, items) in enumerate([("2024-10-15", "2.02,9.01"), ("2024-11-12", "5.02"),
                                            ("2024-12-10", "7.01"), ("2024-12-20", "8.01")]):
            k8.append((t, filed, f"{filed}T21:30:00.000Z", "8-K", items, "titles", "desc",
                       f"https://x/{t}/{n}", f"0000000000-24-{t}{n}"))
    pd.DataFrame(k8, columns=["ticker", "filed", "accepted", "form", "items", "item_titles", "description",
                              "url", "accession"]).to_csv(root / "sec" / "filings_8k.csv", index=False)
    return root
