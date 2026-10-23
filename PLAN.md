# The Desk — Track 3: Financial Portfolio Management

Austin Agentic AI Hackathon · October 23, 2026 · AWS / Arpio / Posit
Track page: https://atx.rahman.dev/track-3.html

---

> **Historical baseline, not the current app specification.** The dense Desk UI and later report page are superseded by the hosted collaborative Dexter canvas. Reuse the data, analysts and backtest modules described here; do not rebuild this UI or infer that its old endpoints remain active. Current behavior and direction are in `README.md` and `hub/PRD.md`. The baseline experiment method below remains relevant until the evaluation lane explicitly records a replacement.

## 1. What we are building

**The Desk**: a single-screen research desk where five AI analyst agents and one
portfolio-manager agent build an investment thesis from data available on or before a
chosen cutoff date, and the thesis is backtested forward against a baseline.

Everything the judges asked for is visible on one screen:

| Judge requirement (from track page)                     | Where it lives on screen            |
|---------------------------------------------------------|-------------------------------------|
| State the asset universe, cutoff date, and baseline     | Header bar + cutoff slider          |
| Show the agents' reasoning for an allocation decision   | Analyst memos + Book rationale      |
| Compare equity curve and key metrics with the baseline  | Curve panel + metrics row           |
| Show which sources influenced the portfolio             | Evidence drawer (click any weight)  |
| Show what would change the position or confidence       | "Changes my mind" line per position |
| No look-ahead bias                                      | Cutoff slider drives every query    |
| Reproducible experiment                                 | Section 5 below + committed data    |

**Demo moment:** drag the cutoff from 2023-01 to 2024-01. Memos rewrite, weights shift,
the equity curve redraws. Click any weight and the evidence trail opens.

---

## 2. Screen layout (one screen, no scroll at 1440x900)

```
+-----------------------------------------------------------------------------+
| TAPE   AAPL 231.40 ^0.8%  MSFT 412.10 v0.3%  NVDA ...   (live, scrolling)   |
+--------------+------------------------------+-------------------------------+
| ANALYSTS     | BOOK                         | PERFORMANCE                   |
|              |                              |                               |
| Technical    | Ticker  Wt    Rationale      |   equity curve                |
|  stance/conf | AAPL   12%   "..."           |   portfolio vs EW vs SPY      |
|  sources     |        changes my mind: ...  |                               |
| Fundamentals | MSFT   10%   "..."           | ----------------------------- |
| Macro        | ...                          | Return  CAGR  MaxDD  Sharpe   |
| Sentiment    |                              | +18.2%  ...   -9.1%  1.21     |
| Geopolitics  |                              |                               |
+--------------+------------------------------+-------------------------------+
| CUTOFF  2022-01 ---------o----------------- 2024-06      universe . baseline|
+-----------------------------------------------------------------------------+
```

Regions:

1. **Tape** – live prices for the universe via the TradingView ticker sidecar. Falls back
   to last close from the committed Stooq data if the socket is down.
2. **Analysts** – five memos (Technical, Fundamentals, Macro, Sentiment, Geopolitics).
   Each memo: per-ticker stance (long / neutral / avoid), confidence 0–1, 2–3 cited
   sources with dates <= cutoff.
3. **Book** – PM agent's target weights, one-line rationale per position, and a
   "changes my mind" trigger per position.
4. **Performance** – equity curve from cutoff forward (portfolio, equal-weight, SPY),
   plus total return, CAGR, max drawdown, Sharpe.
5. **Cutoff slider** – re-runs the whole pipeline for the chosen date. Cached per date.
6. **Evidence drawer** – slides in on weight click: every source that touched that
   position, which analyst used it, and how the PM weighed each analyst.

---

## 3. Visual direction (the "not AI-generated" rule)

**Avoid:** gradients, glassy rounded cards with shadows, hero sections, emoji icons,
centered marketing copy, Inter-on-white with indigo buttons, bouncy animations.

**Do:**

- Palette: background `#0b0c0e`, ink `#e8e6e1`, muted `#8a8782`, hairline `#232528`,
  one accent `#d9a441` (amber). Green `#3fb950` / red `#f85149` reserved for P&L only.
- Type: **Instrument Serif** for the title and memo headlines, **IBM Plex Mono** for
  everything numeric and tabular with `font-variant-numeric: tabular-nums`. Section
  labels in small caps, letter-spaced.
- Layout: 1px hairlines, no shadows, no rounded corners above 2px, dense grid.
- Charts: `lightweight-charts` (TradingView's open-source library). No gridlines,
  thin strokes, series labels at line ends instead of a legend.
- Motion: only the tape scroll and the curve redraw. Nothing else animates.
- Copy: memos read like real analyst notes — dated, signed by the agent, footnoted
  sources.

---

## 4. Architecture

```
web/   Vite + React + TypeScript + Tailwind + lightweight-charts + TanStack Query
  |-- POST /run {universe, cutoff, baseline}  -->  api/
  |-- WS  /tape                               -->  tape/

api/   FastAPI
  |-- schema.py        RunRequest / RunResponse (the contract between lanes)
  |-- data.py          loads committed snapshots, filters everything to <= cutoff
  |-- agents/          Strands Agents on Amazon Bedrock (Claude via Converse API)
  |     technical.py  fundamentals.py  macro.py  sentiment.py  geopolitics.py  pm.py
  |-- backtest.py      monthly rebalance to target weights, metrics
  |-- main.py          /run with per-cutoff cache

tape/  Python sidecar wrapping Hattorius/Tradingview-ticker (GPL-3, keep isolated)
  |-- pushes {symbol, price, change_pct, ts} over a WebSocket

data/  committed snapshots so the demo never depends on network
  |-- prices/       Stooq daily OHLCV, universe + SPY
  |-- sec/          SEC Financial Statement Data Sets: revenue, net income, debt
  |-- fred/         CPI, FEDFUNDS, DGS10, UNRATE
  |-- gdelt/        GKG tone for company names + selected event themes
  |-- fixtures/     run_<cutoff>.json fake responses for UI development
```

### The contract: `RunResponse`

```ts
type Stance = "long" | "neutral" | "avoid";

interface Source   { id: string; kind: "sec"|"fred"|"gdelt"|"price"; title: string;
                     date: string; url?: string; excerpt: string }
interface View     { ticker: string; stance: Stance; confidence: number; note: string;
                     sources: string[] }                       // source ids
interface Memo     { analyst: "technical"|"fundamentals"|"macro"|"sentiment"|"geopolitics";
                     date: string; headline: string; body: string; views: View[] }
interface Weight   { ticker: string; weight: number; rationale: string;
                     changes_my_mind: string; analyst_influence: Record<string, number> }
interface Equity   { dates: string[]; portfolio: number[]; equal_weight: number[];
                     spy: number[] }
interface Metrics  { total_return: number; cagr: number; max_drawdown: number;
                     sharpe: number }

interface RunResponse {
  universe: string[]; cutoff: string; baseline: "equal_weight"|"spy";
  sources: Source[]; memos: Memo[]; weights: Weight[];
  equity: Equity; metrics: { portfolio: Metrics; baseline: Metrics };
}
```

---

## 5. Experiment definition (reproducibility)

- **Universe (10):** AAPL, MSFT, NVDA, AMZN, GOOGL, JPM, XOM, UNH, PG, CAT
- **Benchmark reference:** SPY
- **Cutoff range on slider:** 2022-01-01 to 2024-06-01, monthly steps
- **Default cutoff:** 2023-01-01
- **Baseline:** equal-weight of the universe (SPY shown as second reference)
- **Rebalancing:** monthly, back to PM target weights; long-only; weights sum to 1
- **Costs:** none (documented assumption)
- **Risk-free rate for Sharpe:** FEDFUNDS value at cutoff
- **Evaluation window:** cutoff -> 2025-06-30
- **Look-ahead rule:** every data loader takes `cutoff` and drops rows dated after it
  before any agent sees them

This is a historical experiment, not financial advice.

---

## 6. Build order — three parallel lanes

**Step 0 (everyone, first 15 min):** agree on the contract above. Write
`api/schema.py` and `web/src/types.ts`, commit `data/fixtures/run_2023-01-01.json`.
After this, lanes do not block each other.

### Lane A — UI
1. Scaffold `web/`, strip Tailwind to the palette and two fonts.
2. Four regions against the fixture: tape, analysts, book, performance, slider.
3. Evidence drawer on weight click.
4. Tape WebSocket client with fallback to last close.
5. 1440x900 pass: nothing scrolls, nothing wraps badly.

### Lane B — data + backtest + tape
1. `data/fetch_stooq.py`, `fetch_fred.py`, `fetch_sec.py`, `fetch_gdelt.py`; run them,
   commit snapshots.
2. `api/data.py` loaders with `cutoff` filtering.
3. `api/backtest.py` + metrics; check against a hand computation.
4. `tape/` sidecar around `ticker.py`, exposing `ws://localhost:8765/tape`.

### Lane C — agents
1. Bedrock Converse smoke test (starter kit `infer.py`).
2. Technical analyst with Strands: reads `data.py` output <= cutoff, returns a `Memo`.
3. Clone for the other four analysts.
4. PM agent: takes five memos, returns `Weight[]` with rationale, trigger, and
   per-analyst influence.
5. `POST /run` in `api/main.py`, cache keyed by cutoff.
6. AgentCore Runtime deployment only if time remains (follow README cleanup steps,
   it bills).

### Last hour (everyone)
- Swap fixture for real `/run`.
- README: universe, cutoff, baseline, assumptions, rebalancing rules (section 5 above).
- Rehearse the cutoff-drag demo twice.

---

## 7. Verification checklist

- [ ] App renders four regions + slider at 1440x900 with no page scroll
- [ ] Cutoff 2023-01-01: every source date in the evidence drawer is <= 2023-01-01
- [ ] Equity curve and metrics match a standalone pandas calculation for the same weights
- [ ] Moving the cutoff changes memos, weights and curve; second visit is instant (cache)
- [ ] Killing the tape sidecar leaves the header on last close with no console errors
- [ ] README states universe, cutoff, baseline, assumptions, rebalancing rules
