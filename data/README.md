# data/ — committed snapshots for The Desk

Everything the agents and the backtest read lives here so the demo never depends on
the network. All files were downloaded on **2026-10-23** by the `fetch_*.py` scripts in
this folder. Re-run any script to refresh; each is idempotent.

Loaders in `backend/app/data.py` take a `cutoff` and drop anything not public by that
date before an agent sees it (the no-look-ahead rule). Agents must never read these
CSVs directly.

| Folder | Script | Source | Range covered | Rows |
|---|---|---|---|---|
| `prices/` | `fetch_stooq.py` | Stooq daily CSV `https://stooq.com/q/d/l/?s=aapl.us&i=d`, falling back to Yahoo Finance `https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d` | 2021-01-04 .. 2025-06-30, daily | 1127 trading days x 11 tickers |
| `fred/` | `fetch_fred.py` | FRED CSV `https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS` (also CPIAUCSL, DGS10, UNRATE) | 2019-01-01 .. 2025-06-30 (monthly; DGS10 daily) | 1858 |
| `sec/` | `fetch_sec.py` | SEC XBRL companyfacts API `https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` (same facts as the Financial Statement Data Sets `https://www.sec.gov/dera/data/financial-statement-data-sets`) | fiscal quarters ending 2021-01-31 .. 2025-06-30, filed through 2025-08 | 180 ticker-quarters |
| `gdelt/` | `fetch_gdelt.py` + hand-curated `curated_events.csv` | GDELT DOC 2.0 API `https://api.gdeltproject.org/api/v2/doc/doc?mode=timelinetone` | 2021-04-26 .. 2025-05-14 (curated events); daily tone 2021-01-01 .. 2025-06-30 when `tone.csv` is present | 83 curated events |
| `fixtures/` | `fixtures/make_fixture.py` | synthetic | n/a | one fake `RunResponse` |

Universe: AAPL, MSFT, NVDA, AMZN, GOOGL, JPM, XOM, UNH, PG, CAT. Reference: SPY.

## Files

**prices/** — `<TICKER>.csv` with `date,open,high,low,close,volume`; `close.csv` is the
wide table of closes (one column per ticker) that the backtest uses. Closes are
split-adjusted but not dividend-adjusted, so the backtest measures price return.

**fred/** — `<SERIES>.csv` and the long `macro.csv` with `date,series,value,available`.
`date` is FRED's observation date (first of the month for monthly series); `available`
is when the number was published and is what the loader filters on: FEDFUNDS the
first business day of the next month (+3 days), UNRATE the first Friday (+7), CPI
around mid-month (+15), DGS10 same day. At a 2023-01-01 cutoff the latest visible
FEDFUNDS is November 2022, 3.78%, which is the Sharpe risk-free rate for that run.

**sec/** — `fundamentals.csv` with one row per ticker and fiscal quarter:
`ticker,fy,fp,period_end,filed,form,revenue,net_income,total_debt,concept_*`. Values
in USD. Revenue and net income are three-month figures; a Q4 is derived as full year
minus Q1..Q3 when the 10-K reports only the annual number. `total_debt` is the latest
consolidated debt balance on or before `period_end` (Caterpillar tags it only in the
10-K, so its quarters carry the prior year-end). The loader filters on `filed`, so a
quarter is visible only once its 10-Q/10-K was on EDGAR. `raw/<TICKER>.json` is the
untouched API response. JPMorgan's revenue is net revenue
(`RevenuesNetOfInterestExpense`).

**gdelt/** — `curated_events.csv` with `date,subject,kind,tone,headline`: 83 dated,
well-known public events for the ten companies and three themes (ukraine_energy,
china_reopening, chip_export_controls), each with a tone score on the GDELT scale
(-10 bad .. +10 good). The headlines are our own one-line paraphrases, not quotes.
`tone.csv` (`date,subject,kind,tone`), when present, is the GDELT DOC API daily
average tone for the same subjects. `raw/<subject>.csv` are the API responses.

## Deviations from PLAN.md, and why

- **Stooq → Yahoo fallback.** On 2026-10-23 Stooq answers non-browser requests with a
  JavaScript proof-of-work page instead of CSV. `fetch_stooq.py` still tries Stooq
  first and falls back to the Yahoo chart endpoint, which needs no key and returns the
  same daily bars. All eleven tickers in this snapshot came from Yahoo.
- **SEC companyfacts instead of the quarterly zips.** The Financial Statement Data
  Sets are ~125 MB per quarter (2.2 GB for the window). The companyfacts API serves
  the same XBRL facts, with the same `filed` dates, per company. It is published by
  the same SEC office.
- **GDELT curated events.** The DOC API throttles an address for minutes after a
  handful of requests, so the daily tone pull is slow and was unreliable during the
  build. The curated table is what agents cite; it is marked as hand-written and the
  script documents how to regenerate `tone.csv`.
- **FRED availability dates.** Added so a monthly value is not visible before it was
  released. This is stricter than the plan's "dated <= cutoff" wording.

Historical experiment, not financial advice.
