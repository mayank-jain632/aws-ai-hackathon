# Aaron · Lane 4 (moderator half): watchdog and moderator

Updated 13:50 by Claude Code

**Shipped** (on `main`, locally checked, broker mocked; reference in `docs/watchdog.md`)
- Pre-trade gate `backend/app/watchdog/` (D17, D19): 16 deterministic rules, no LLM in the path. Emergency stop, trading permission, client universe, ticker exists in our data, backend PASS (buys), quantity/cash/no-short sanity, per-order size, position size, top-three concentration, account and tested drawdown, price band vs last close, rapid fire, duplicate under a new id, same-day wash trade, daily turnover, daily order count. The most serious block leads the reason
- Live order path: `paper.submit` calls `watchdog.gate.enforce(...)` right after the account and open-order checks, ahead of the adapter's exposure checks (which all still run). A block raises ValueError, the existing route logs `paper_order_blocked`, and the executor sees the watchdog's reason
- Firm-wide emergency stop over every fund, above each fund's desk stop: `PUT /api/watchdog/halt` (people only), `is_halted()` / `halt_reason()`. Status at `GET /api/watchdog` and `GET /api/funds/{id}/watchdog`; dry-run `POST /api/watchdog/review`
- Background monitor `watchdog/monitor.py`, started by the watchdog router's lifespan every `WATCHDOG_INTERVAL_SECONDS` (default 60, 0 disables) across the board and every fund, plus `POST /api/watchdog/audit`, `POST /api/funds/{id}/watchdog/audit` and the moderator's `watchdog_audit` tool. Flags runaway bursts (over 10 orders in 10 min trips the stop), agents retrying blocked orders (3 warn, 6 trip), unknown broker outcomes, holdings past the mandate, shorts, holdings outside the universe. Events go beside the desk, to `workspace/watchdog/events.jsonl`, and onto the desk audit as `watchdog_event`
- Claim checks `watchdog/claims.py`: each strategy's cited memos must exist in the fund's shared files, cite no dates after the strategy cutoff (reuses `assert_no_lookahead`), and be unchanged since the strategy was frozen. `check_sources(sources, decision_date, known_ids)` for Desk `Source` lists
- Second opinion `watchdog/opinion.py` on blocked and near-miss orders through `run_structured` (Bedrock Converse, `gpt-5.6-luna`, no temperature): foul play or honest mistake, plain explanation, suggested fix. Mock mode or a Bedrock error falls back to a rule-based note that says so
- Feedback loop: every verdict, desk-gate block, opinion and order outcome goes to `feedback.jsonl` beside the desk and is distilled into `workspace/watchdog/LESSONS.md`. `watchdog_lessons` tool for strategy, executor and moderator (orchestrator via `*`); their instructions in `roles.py` tell them to read it before registering or ordering
- Demo: `MOCK_AGENTS=1 uv run python scripts/watchdog_demo.py` drives the real routes with only the broker stubbed. A conservative client's $40,000 MSFT buy is blocked on position size, an $8,000 buy is allowed, the firm-wide stop refuses orders in two funds, and the lessons are printed
- Tests: `backend/tests/test_watchdog_rules.py` (each rule), `test_watchdog_gate.py` (real `paper.submit` path, halt across funds, routes, role denial, monitor loop starts with the app), `test_watchdog_monitor.py`, `backend/worker/watchdog-tools.test.ts`

**Interface for execution and strategy owners**
- Nothing to call if you go through `paper.submit`; the gate already runs there
- Elsewhere: `from backend.app.watchdog import review_order, is_halted, WatchOrder, WatchMandate, WatchPortfolio`. `review_order(order, mandate, portfolio) -> Verdict` with `decision` (`approve`/`block`), `reason`, `blocked_by`, `near_misses` and per-rule results. Check `is_halted(desk)` before every order
- Fractions are 0..1. Risk-band guardrails (concentration, turnover, order share of equity, price band) are in `rules.GUARDRAILS`; a mandate field overrides them

**In flight**
- Scores and reasoning view (D23), shipped to `main` with both click levels; locally checked against a labeled fixture fund and Mayank's real walk-forward output (from his branch, mounted with `SCORES_WF_DIR`). Not yet seen on the hosted canvas. `GET /api/funds/{fund_id}/scores` (fund members only, through the sharing middleware; workers get 403) returns one read-only scorecard. Eight rings: mandate fit, trade confidence, strategy, backtest, significance, execution, watchdog gate, sensitivity. Each scored ring carries its raw metric, formula, source record and owner. Click a ring for factors (value, weight, pass or fail, producing agent and role); click a factor for recorded reasoning (critique, rationale, memo text, analyst views) and provenance (record, file, time, cited sources with kind, title, date, URL, excerpt). The panel also lists every data source with its status and every tool call in the fund's agent activity logs. Rings with no data say "not produced yet" and name the owning lane. Fund records fill fund rings; walk-forward output fills empty rings only and is tagged firm-wide. Synthesis (`synthesis.json` beside the desk) is coded against Chaithu's shapes and switches on when it exists
- Nothing else in the 15:00 freeze scope. If time allows: run the demo on the hosted canvas once Lane 5 deploys this commit

**Blocked, or need from someone**
- Lane 5: the image copies only `backend`, `data` and `frontend`, so `reports/wf/` will not reach the hosted container after Mayank's merge. Add `reports` to the Dockerfile COPY and `.dockerignore`, or set `SCORES_WF_DIR` to a mounted copy
- Lane 1: `roles.py` now lists `watchdog_lessons` for strategy, executor and moderator and `watchdog_audit` for moderator, plus one sentence each in the strategy and executor instructions. Say if you want them placed differently
- Lane 5: hosted deploy of this commit to see the gate on the real Alpaca paper account
- Not verified: a live Bedrock second opinion (no workshop credentials on this machine; the call is exercised with a stub), the built-container registry listing, a real Alpaca order through the gate, hosted rollout. AgentCore Memory (PRD P1) not built; it needs an accepted decision for the new resource

**Files I am working in right now**
- Scores view: `backend/app/scores/`, `backend/app/routes/scores.py`, `backend/tests/test_scores.py`, `frontend/src/scores/`
- Cross-lane mount points: one `include_router` line in `backend/app/main.py`; in `frontend/src/funds/FundOverview.tsx` (Kushagra's core-product chat), one `<ScoresEntry fund={fund}/>` element and its import, nothing else
- `backend/app/watchdog/`, `backend/app/routes/watchdog.py`, `backend/worker/watchdog-tools.ts`, `backend/tests/test_watchdog_*.py`, `scripts/watchdog_demo.py`, `docs/watchdog.md`
- Small hooks: `backend/app/main.py`, `backend/app/paper.py`, `backend/worker/run.ts`, `backend/app/roles.py`
