# PRD: agentic trading desk for wealth managers

**v0.1 · 12:55 · owner Aaron · malleable.** This is the one PRD for the team. It sets direction and checkpoints for the first builds; lanes fill in details as they go. To change it, log a decision in `hub/DECISIONS.md` and edit the section it touches in the same commit. Sources: the 11:24 team brainstorm (Granola), the judges' feedback, and what is on `main` at 12:50 (the hosted canvas from D7, plus The Desk modules from D6).

## 1. The product in one paragraph

A platform where teams of agents do the investment work for a wealth management desk. Research agents each study one kind of data. A strategy agent turns their findings into a strategy for each client. A backtest agent tests that strategy on history it never saw during research, and only a strategy that passes goes live. An execution agent then places the trades for that client, inside limits the client approved in advance. A moderator agent watches everything and can stop all trading at once. The people who use it (wealth management analysts, traders, anyone at the client firm) set the client mandates and read the results. They do not run the agents. To them the platform is a black box to operate but a glass box to audit: every trade traces back to a strategy, a backtest, and the research behind it.

## 2. Who it is for

- **Primary user:** a JPMorgan-style wealth management analyst running several client portfolios. Not retail.
- **Clients:** the people whose money is managed. They approve a mandate (risk band, limits, whether agents may trade) and the agents act only inside it.
- **Demo audience:** the judges. They score innovation, technical implementation, use of AWS AI services, and presentation. They told us UI does not matter; working functionality and breadth of data inputs do, and they **will test it against their own data**.

## 3. What makes it different

1. **Statistics, not vibe trading.** An LLM picks the strategy, but nothing trades until a blind backtest says it holds up against S&P 500 buy-and-hold.
2. **Breadth of data.** As many independent data inputs as we can wire up, each one dated so a backtest never sees the future.
3. **Agents act, people govern.** Agents place every trade; people set the mandate, read the audit trail, and hold the emergency stop.
4. **Adaptive.** The pipeline reruns on new data (daily in the story; on demand in the demo) and can change strategy when conditions change.

## 4. The pipeline

```
client mandates (6 clients, 3 risk bands)
        |
        v
[orchestrator]  runs the phases in order for each client, logs every hand-off
        |
        v
PHASE 1  research team        each agent works alone on one data family; no cross-talk until all are done
        |                     output: dated memo per agent with cited, dated sources
        v
PHASE 2  strategy agent        reads all memos plus the client's mandate
        |                     output: a named strategy, target weights, rationale, "what would change my mind"
        v
PHASE 3  backtest agent        sees only the strategy, never the research (stays unbiased)
        |                     in-sample up to the cutoff, out-of-sample after; benchmark S&P 500 buy-and-hold
        |                     output: metrics plus PASS or FAIL against the client's band
        v
PHASE 4  execution agent       only for PASS and only if the mandate allows trading
        |                     output: orders and fills (Alpaca paper trading; a logged dry run if no keys)
        v
[moderator]  runs after every pipeline run (daily or weekly in the story); checks limits, drawdown, order counts;
             owns the emergency stop that the execution agent checks before every order
```

### How the two halves on `main` become one product

`main` holds two things that each cover half of the brainstorm. The hosted canvas (D7) is a working agent runtime: agents that create and message their own subagents, a shared filesystem, a shared board for several analysts' accounts, hosted on AWS. The Desk modules (D6) are a working research team, date-safe data, and a backtest. They join through the canvas tool list:

- **The canvas is the runtime.** The orchestrator is a canvas agent. It spawns each phase's agents as its subagents, so analysts watch the pipeline run on the board, and the agent tree is the agent flow diagram for the slides.
- **The Desk is the toolbox.** Today the canvas agents only have file and delegation tools (the `tools` array in `backend/worker/run.ts`). New tools there call The Desk modules through internal backend routes: research slices, strategy, backtest, orders. That bridge is the first thing lane 1 builds.
- **The shared filesystem is the audit trail.** Each phase writes its output as a file under one folder per run and client (memos, strategy, backtest result, orders, moderator events), which the next phase reads and the analysts can open from the board.

| Piece on `main` | Today | Becomes |
|---|---|---|
| Hosted canvas (`frontend/`, `backend/app/agent.py`, `backend/app/access.py`, `backend/worker/`) | Dexter agent tree, shared files, demo accounts, EC2 behind CloudFront | the runtime and the analyst's view; orchestrator and phase agents run here |
| Canvas tool list (`backend/worker/run.ts`) | read, write, and edit file; create, list, and message agent | gains finance tools that call The Desk modules: the bridge |
| Five analysts (`backend/app/agents/`) | technical, fundamentals, macro, sentiment, geopolitics | Phase 1 research tools; new data inputs add new research tools |
| PM agent (`backend/app/agents/pm.py`) | target weights with rationale | engine behind the Phase 2 strategy agent, now per client and risk band |
| Backtest (`backend/app/backtest.py`) | monthly rebalance, metrics, 6 tests | engine for the Phase 3 backtest agent, plus the pass/fail gate |
| Loaders (`backend/app/data.py`) | cutoff-filtered prices, SEC, FRED, events | the date-safe base every new data input plugs into |
| Report page and `/api/run` | not on `main`; kept in git history and branch `report-baseline` | `/api/run` logic returns as an internal tool route; the report page is optional now that UI does not score |

## 5. Requirements

**P0, must work by 3:00 PM**

1. **Clients and mandates.** Six hard-coded clients across three risk bands (conservative, balanced, aggressive) and different wealth levels. Each mandate states the allowed universe, max position size, max drawdown, and a trading permission flag.
2. **One run, end to end.** One instruction to the orchestrator agent on the canvas (and the same thing through one API call, for scripted demo runs) runs all four phases for all six clients and leaves every output in the shared workspace.
3. **Research team on more data.** Every existing data family, plus at least two new inputs from section 7.
4. **Strategy per client.** A named strategy and weights that respect the mandate, with a rationale that cites research memos.
5. **Blind backtest gate.** The backtest agent gets the strategy only. It reports return, CAGR, max drawdown, and Sharpe for in-sample and out-of-sample windows against S&P 500 buy-and-hold, then PASS or FAIL against the client's band.
6. **Execution with guardrails.** PASS plus permission produces orders. FAIL or no permission produces a logged "blocked" with the reason. Paper trading only.
7. **Emergency stop.** One flag the moderator (or a person) sets; the execution agent refuses every order while it is on. The demo shows it working.
8. **No look-ahead in backtests.** Every input used in a backtest drops anything not public by the cutoff. Live mode uses data as of now and is never scored as a backtest.
9. **Audit trail.** Per client, an analyst can open the memos, strategy, backtest result, orders or blocks, and moderator events from the board.
10. **AWS visibly used.** Bedrock Converse for every agent, and the hosting already on AWS (EC2, CloudFront, ECR, Secrets Manager). The brainstorm also named AgentCore: show at least two of AgentCore Runtime, Memory, and Observability in the demo, because judges score AWS AI services specifically.
11. **Disclaimer.** Historical and paper-trading experiment, not financial advice; retro-scored results are approximate.

**P1, if time allows**

- **Bring your own data.** Judges said they will test with their own data. Accept a custom universe and a price CSV in the `data/prices/` format, with no code changes.
- **Statistical significance.** Walk-forward over every cutoff, how often the strategy beats the benchmark, and a confidence interval on excess return.
- **Leakage check.** Same run with tickers masked as "Company 3, semiconductors"; report the gap.
- **AgentCore Memory for the strategy agent**, so it remembers past strategies per client and says when one of its "what would change my mind" triggers fired.

**P2, roadmap slide only**

- MCP integration (through AgentCore Gateway) so the platform plugs into a firm's existing tools and other agents can call it.
- Separate tenants per client firm; today every demo account shares one board.

## 6. Experiment definition (target)

The brainstorm set these targets. The backtesting lane owns turning them into code, `README.md`, and `data/README.md`, and logs the exact values as a decision.

- **Universe:** the top 15 S&P 500 names by weight, frozen as of the in-sample start (today `main` uses 10).
- **Benchmark:** S&P 500 buy-and-hold (SPY) first; equal weight of the universe second.
- **Windows:** in-sample through the cutoff (the brainstorm said 2025; the lane picks the exact date), out-of-sample from the cutoff to the latest data. Today's price snapshot ends 2025-06-30, so out-of-sample needs fresher prices.
- **Model memory:** models know a lot about 2023 to 2025 (NVIDIA's run, for example). Agents must reason from fetched data, and the out-of-sample window is the number we lead with.

## 7. Data inputs

Every input gets a fetch script or adapter, a cached snapshot for the demo, an `available` date per row, and a cutoff-aware loader. Live-only inputs (no history) feed the live run only and are labeled that way.

| Input | Family | Mode | Status |
|---|---|---|---|
| Daily prices (Yahoo fallback for Stooq) | price | backtest + live | on `main`, 10 tickers |
| SEC XBRL fundamentals, filtered by `filed` date | company financials | backtest | on `main` |
| FRED: CPI, Fed funds, 10-year yield, unemployment | macro | backtest | on `main` |
| Curated geopolitical and company events | geopolitical | backtest | on `main`, hand-written, unverified |
| Alpaca market data (free tier) | price, live | live | brainstorm, new |
| Market news sentiment (scraped headlines) | sentiment | live, backtest if dated | brainstorm, new |
| Reddit r/wallstreetbets and other social signals | sentiment | live | brainstorm, new |
| Live web search for current context | context | live | brainstorm, new |
| X/Twitter | sentiment | mocked sample feed | brainstorm, API restricted |
| More FRED series: yield curve slope, high-yield spread, VIX, policy uncertainty | macro | backtest | research brief, about 10 minutes |
| SEC Form 4 insider buying | company | backtest | research brief, new |
| Earnings call transcripts (Hugging Face, 2005 to 2025) | sentiment | backtest | research brief, new |
| Geopolitical Risk index (Caldara and Iacoviello) | geopolitical | backtest | research brief, new |

Details and setup times for the research-brief rows: `docs/research/finance-track-brief.md`.

## 8. New shared shapes

These go in `backend/app/schema.py` next to `RunResponse`. The orchestration lane owns the file; propose changes in `hub/DECISIONS.md` first.

- `Client` and `Mandate`: id, name, risk band, wealth, allowed universe, max position, max drawdown, trading allowed.
- `Strategy`: client id, name, target weights, rationale, memo ids cited, "what would change my mind".
- `BacktestResult`: strategy id, windows, metrics for strategy and benchmark, verdict PASS or FAIL, reason.
- `Order` and `Fill`: client id, ticker, side, quantity, status (`filled`, `blocked`, `dry_run`), reason, timestamp.
- `ModeratorEvent`: time, check, result, action (including the emergency stop).
- `PipelineRun`: run id, mode (`backtest` or `live`), cutoff, and one record per client holding the above.

## 9. Lanes

Six lanes for six people. Claim one by writing it at the top of your `hub/status/<name>.md`. The brainstorm named lanes 1 to 3. Names in brackets come from who has been building what today; they are suggestions, not assignments. Mayank and Gerson have demo accounts but no lane yet.

| Lane | Owns | First deliverable |
|---|---|---|
| 1. Orchestration and agent loop | orchestrator agent, the canvas finance tools (the bridge), phase hand-offs, shared shapes, the strategy agent | orchestrator spawns the four phases for 6 clients in mock mode |
| 2. Backtesting and evaluation [Chaithu] | backtest agent, pass/fail gate, experiment definition, P1 statistics | gate returning PASS or FAIL for one strategy |
| 3. Data sourcing | every new input in section 7 | two new inputs with cutoff-safe loaders |
| 4. Execution and moderator | Alpaca paper client, orders, emergency stop, moderator checks | dry-run orders blocked by the stop |
| 5. AWS platform and canvas [Kushagra] | hosted canvas, AgentCore Runtime, Memory, Observability, credentials, deploys | one agent on AgentCore with a visible trace; hosted canvas redeployed with the bridge |
| 6. Demo and pitch [Aaron] | demo script, cached demo run, two slides, this PRD and the hub | demo script and slide outline |

## 10. Checkpoints

Everyone reruns `git fetch` at each checkpoint and reads every status file.

| Time | Checkpoint |
|---|---|
| 1:30 PM | Shared shapes merged. Pipeline runs end to end in mock mode for 6 clients. Two new data inputs merged. |
| 2:15 PM | Real Bedrock calls through all four phases. Gate working. Paper orders or dry runs placed. Emergency stop works. AgentCore Runtime hosting at least one agent. |
| 3:00 PM | **Feature freeze, demo prep starts.** Cache one full demo run so the demo never depends on network or fresh credentials. Slides: AWS architecture, agent flow, roadmap. |
| 4:00 PM | Hand in. Demos at 4:30 PM. |

## 11. Non-goals and anti-goals

- **Not building:** real-money trading, any brokerage beyond Alpaca paper, login or multiple tenants, UI polish, mobile, production hardening.
- **Failure even if it works:** a backtest that wins because the model remembers the future; an agent citing data it invented; any order placed without a PASS and the client's permission; a demo that only works with live network and fresh credentials.

## 12. Open, decided inside each lane

Each lane decides these, logs the answer in `hub/DECISIONS.md`, and updates this PRD. Nobody waits on a meeting.

- Exact cutoff date and out-of-sample window (lane 2).
- Pass/fail thresholds per risk band (lane 2, with lane 1).
- Which two data inputs land first (lane 3).
- One Alpaca paper account with client sub-ledgers, or one account per client (lane 4).
- Which agents run on AgentCore Runtime versus on the hosted canvas for the demo (lane 5).
- Strategy agent: free choice of strategy, or a fixed menu it chooses from (lane 1).
- How canvas tools reach The Desk modules: internal backend routes, or Python called from the worker (lane 1 with lane 5).
- The run folder layout in the shared workspace (lane 1).
