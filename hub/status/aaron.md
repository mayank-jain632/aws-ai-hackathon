# Aaron · Lane 4 (moderator half): watchdog and moderator

Updated 13:30 by Claude Code

**Shipped**
- Watchdog pre-trade gate on `main` (D17, D19), locally checked, broker mocked: `backend/app/watchdog/`. 16 deterministic rules, no LLM in the path: emergency stop, trading permission, client universe, ticker exists in our data, backend PASS (buys), quantity/cash/no-short sanity, per-order size, position size, top-three concentration, account and tested drawdown, price band vs last close, rapid fire, duplicate under a new id, same-day wash trade, daily turnover, daily order count
- Wired into the live order path: `paper.submit` calls `watchdog.gate.enforce(...)` after the Alpaca snapshot and before recording intent. A block raises ValueError, so the existing route logs `paper_order_blocked` and the executor sees the reason
- Firm-wide emergency stop over every fund (on top of each fund's desk stop): `PUT /api/watchdog/halt` (people only), `is_halted()` / `halt_reason()`
- Feedback log beside each desk and `watchdog/LESSONS.md` in the fund's shared workspace; `watchdog_lessons` canvas tool for strategy, executor, moderator (orchestrator via `*`)
- `GET /api/watchdog`, `GET /api/funds/{id}/watchdog`, dry-run `POST /api/watchdog/review`
- Background monitor (`watchdog/monitor.py`), started by the watchdog router's lifespan every `WATCHDOG_INTERVAL_SECONDS` (default 60, 0 disables) across the board and every fund. Also on demand: `POST /api/watchdog/audit`, `POST /api/funds/{id}/watchdog/audit`, and the moderator's `watchdog_audit` tool (the orchestrator already runs the moderator after execution). Flags runaway order bursts (>10 in 10 min, trips the firm-wide stop), agents retrying blocked orders (3 warn, 6 trip), unknown broker outcomes, holdings past the mandate, shorts, holdings outside the universe. Logs order outcomes into the feedback log. Events go beside the desk, to `workspace/watchdog/events.jsonl`, and onto the desk audit as `watchdog_event`
- Claim checks (`watchdog/claims.py`): each strategy's cited memos must exist in the fund's shared files, cite no dates after the strategy cutoff (reuses `assert_no_lookahead`), and not be edited after the strategy was frozen. `check_sources(sources, decision_date, known_ids)` for Desk `Source` lists
- Second opinion (`watchdog/opinion.py`) on blocked and near-miss orders through `run_structured` (Bedrock Converse, `gpt-5.6-luna`, no temperature): foul play or honest mistake, plain explanation, suggested fix, written into the lessons. Mock mode or a Bedrock error falls back to a rule-based note that says so
- Tests: `backend/tests/test_watchdog_monitor.py`, `backend/tests/test_watchdog_rules.py` (each rule), `backend/tests/test_watchdog_gate.py` (real `paper.submit` path with broker stub, halt across funds, routes, role denial), `backend/worker/watchdog-tools.test.ts`

**Interface for execution and strategy owners**
- Nothing to call if you go through `paper.submit`; the gate already runs there
- Elsewhere: `from backend.app.watchdog import review_order, is_halted, WatchOrder, WatchMandate, WatchPortfolio`. `review_order(order, mandate, portfolio) -> Verdict` with `decision` (`approve`/`block`), `reason` (plain language), `blocked_by`, `near_misses`, per-rule results. Check `is_halted(desk)` before every order
- Fractions are 0..1. Guardrails per risk band (concentration, turnover, order share of equity, price band) live in `rules.GUARDRAILS`; a mandate field overrides them

**In flight**
- 15:00 slice: lessons loop polish, `docs/watchdog.md`, and a scripted demo (oversized conservative order blocked with a clear reason, then the firm-wide stop halts every fund)

**Blocked, or need from someone**
- Lane 1: I added `watchdog_lessons` to the strategy, executor and moderator tool lists and `watchdog_audit` to moderator in `roles.py`. Say if you want them placed differently
- Not verified: a live Bedrock second opinion (no workshop credentials on this machine; the structured call is exercised with a stub), built-container registry listing, real Alpaca orders, hosted rollout

**Files I am working in right now**
- `backend/app/watchdog/`, `backend/app/routes/watchdog.py`, `backend/worker/watchdog-tools.ts`, `backend/tests/test_watchdog_*.py`
- One-line hooks: `backend/app/main.py`, `backend/app/paper.py`, `backend/worker/run.ts`, `backend/app/roles.py` (tool names only)
