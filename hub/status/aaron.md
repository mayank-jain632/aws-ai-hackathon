# Aaron · Lane 4 (moderator half): watchdog and moderator

Updated 13:15 by Claude Code

**Shipped**
- Watchdog pre-trade gate on `main` (D17, D19), locally checked, broker mocked: `backend/app/watchdog/`. 16 deterministic rules, no LLM in the path: emergency stop, trading permission, client universe, ticker exists in our data, backend PASS (buys), quantity/cash/no-short sanity, per-order size, position size, top-three concentration, account and tested drawdown, price band vs last close, rapid fire, duplicate under a new id, same-day wash trade, daily turnover, daily order count
- Wired into the live order path: `paper.submit` calls `watchdog.gate.enforce(...)` after the Alpaca snapshot and before recording intent. A block raises ValueError, so the existing route logs `paper_order_blocked` and the executor sees the reason
- Firm-wide emergency stop over every fund (on top of each fund's desk stop): `PUT /api/watchdog/halt` (people only), `is_halted()` / `halt_reason()`
- Feedback log beside each desk and `watchdog/LESSONS.md` in the fund's shared workspace; `watchdog_lessons` canvas tool for strategy, executor, moderator (orchestrator via `*`)
- `GET /api/watchdog`, `GET /api/funds/{id}/watchdog`, dry-run `POST /api/watchdog/review`
- Tests: `backend/tests/test_watchdog_rules.py` (each rule), `backend/tests/test_watchdog_gate.py` (real `paper.submit` path with broker stub, halt across funds, routes, role denial), `backend/worker/watchdog-tools.test.ts`

**Interface for execution and strategy owners**
- Nothing to call if you go through `paper.submit`; the gate already runs there
- Elsewhere: `from backend.app.watchdog import review_order, is_halted, WatchOrder, WatchMandate, WatchPortfolio`. `review_order(order, mandate, portfolio) -> Verdict` with `decision` (`approve`/`block`), `reason` (plain language), `blocked_by`, `near_misses`, per-rule results. Check `is_halted(desk)` before every order
- Fractions are 0..1. Guardrails per risk band (concentration, turnover, order share of equity, price band) live in `rules.GUARDRAILS`; a mandate field overrides them

**In flight**
- 14:15 slice: background monitor (runaway order counts, retry loops, uncertain orders, positions vs mandate, strategy memo claims vs cutoff) writing moderator events to `workspace/watchdog/events.jsonl`; Bedrock second opinion (`gpt-5.6-luna`, no temperature) on flagged trades
- 15:00 slice: lessons loop polish and a scripted demo (oversized conservative order blocked, then the firm-wide stop halts everything)

**Blocked, or need from someone**
- Lane 1: I added `watchdog_lessons` to the strategy, executor and moderator tool lists and `watchdog_audit` to moderator in `roles.py`. Say if you want them placed differently
- Not verified: built-container registry listing, real Alpaca orders, hosted rollout

**Files I am working in right now**
- `backend/app/watchdog/`, `backend/app/routes/watchdog.py`, `backend/worker/watchdog-tools.ts`, `backend/tests/test_watchdog_*.py`
- One-line hooks: `backend/app/main.py`, `backend/app/paper.py`, `backend/worker/run.ts`, `backend/app/roles.py` (tool names only)
