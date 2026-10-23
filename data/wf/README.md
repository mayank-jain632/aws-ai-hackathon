# data/wf: point-in-time snapshot for the walk-forward backtest (hub D15)

Built by `python data/fetch_wf.py` on 2026-10-23. The older `data/` snapshots (ending 2025-06-30) are untouched.
`data/wf/sec/raw/` caches the untouched SEC JSON responses (delete it to refetch).

| File | Source | Range | Rows |
|---|---|---|---|
| `prices/<T>.csv` (10 tickers + SPY) | Yahoo chart API (Stooq is behind a JS challenge) | 2021-01-04 .. 2026-10-22 | 1458 each |
| `fred/macro.csv` (date,series,value,available) | FRED fredgraph CSV via `curl --http1.1` | obs 2019-01-01 .. 2026-10-22 | 11767 |
| `sec/fundamentals.csv` | SEC companyfacts (logic of `data/fetch_sec.py`) | period_end 2021-01 .. 2026-09-30, filed <= 2026-10-22 | 221 |
| `sec/filings_8k.csv` | EDGAR submissions API (recent + extra JSON pages) | filed 2025-01-01 .. 2026-10-22 | 254 |

Rows per FRED series: FEDFUNDS 93, CPIAUCSL 92, UNRATE 92, DGS10 1952, T10Y2Y 1953, VIXCLS 1996,
BAMLH0A0HYM2 786 (FRED serves only ~3 years of it, from 2023-10-24), USEPUINDXD 2852, DCOILWTICO 1951.
8-Ks per ticker: AAPL 17, AMZN 21, CAT 20, GOOGL 27, JPM 47, MSFT 14, NVDA 21, PG 35, UNH 28, XOM 24.

## Availability (visibility) rules, enforced by `backend/app/wf/pit.py`

For a decision after the close on `as_of`:

- prices: `date <= as_of`
- SEC fundamentals and 8-Ks: `filed < as_of` (strictly before; 8-Ks must also have an acceptance date, New York time, before `as_of`)
- FRED: `available <= as_of`, where `available` is
  FEDFUNDS = month start + 1 month + 3 days, UNRATE = + 1 month + 7 days, CPIAUCSL = + 1 month + 15 days
  (same rules as `data/fetch_fred.py`), DGS10 = same day (as in `data/fetch_fred.py`), all other daily series = date + 1 day.

`filed` for a fundamentals row is the later of the revenue and net income first-filing dates; Q4 rows are derived
(FY minus Q1..Q3) and carry the 10-K filing date. The earliest-filed fact wins, so restatements never move `filed`.

## Known leaks and gaps

- FRED values are as finally published/revised (vintage history is not used), so revised monthly series
  (CPI, UNRATE, FEDFUNDS is not revised) can differ slightly from what was first released. Release lags are conservative approximations, not exact calendars.
- Prices are split-adjusted, not dividend-adjusted (price-return backtest). Yahoo may restate past splits retroactively; no splits for these names are known inside the window.
- Fundamentals come from companyfacts as of 2026-10-23: values are the earliest-filed fact, but the XBRL concept chosen per company is picked with full-history knowledge (a tag-selection leak of negligible size).
- XOM's Q2 2026 quarter is absent from companyfacts at fetch time (latest XOM row: 2026-03-31); other tickers reach 2026-06-30 (NVDA 2026-07-26, PG 2026-09-30).
- Total debt is the latest balance reported on or before period end (CAT only tags consolidated debt in the 10-K).
- `USEPUINDXD` is the daily news-based policy uncertainty index; its recent values may be revised.
- 8-K `items` are from the submissions index; `description` is the filer's primary document description (often just "8-K"). 8-K bodies are not downloaded.
- The last FRED rows (e.g. 2026-10-22 daily values) have `available` = 2026-10-23, after the last decision, so they are never used.
