# Dedicated Dexter roles

These roles extend the pinned upstream Dexter `Agent` and native tools. They do not introduce another agent loop. `backend/app/roles.py` is the capability registry; `GET /api/agent-roles` exposes it. The canvas shows each agent's role. New boards start with one orchestrator; specialists are created on demand, retain separate histories, and share files inside their fund.

| Role | Available work | Delegation |
|---|---|---|
| `orchestrator` | Coordinate phases, read/write files, use native research, inspect desk records | Create and message specialist descendants |
| `research` | Native finance, market data, filings, screening, web/URL/X tools and shared files | Spawn an adversarial reviewer |
| `adversarial` | Challenge research/strategy with native evidence; record APPROVE or CHANGES_REQUESTED | None |
| `strategy` | Research, write declarative target weights, register an immutable strategy | Spawn an adversarial reviewer |
| `backtester` | Only `run_backtest` for its bound strategy ID | None |
| `executor` | Native web search, URL fetch, market data; paper account and guarded paper orders | None |
| `moderator` | Inspect desk, inspect paper account, engage emergency stop | None |

Native finance tools use `FINANCIAL_DATASETS_API_KEY`. Exa web search and X search appear only when their existing keys are configured. No extra search client or custom research API is introduced. The backtester never gets these tools, file tools, roster inspection, or delegation tools.

The model's tool list is filtered from server-owned permissions, and backend tool routes check the authenticated agent's role. A research agent cannot request an executor child or change its own role. Parent-child ownership and fund token lookup remain enforced. Old root agents become orchestrators; old specialists default to research. Roles survive roster reloads.

## Handoffs

1. Give the orchestrator a concrete task and evidence/date context. It creates research specialists for the needed data families. Research and strategy instructions require adversarial challenges.
2. A strategy developer calls `register_strategy` with positive long-only weights summing to one, cutoff/end dates, memo paths, rationale and change triggers. Revisions receive new IDs; agents cannot edit registered records through files.
3. A separate adversarial agent records its review using `review_strategy`. A backtester cannot be created until the registered strategy has an approving review.
4. The orchestrator calls `create_agent` with `role: "backtester"` and that `strategy_id`. Backend-generated input contains only the ID, weights and dates. User task text, the chosen display name, prior conversations, file names and fund free-text context are excluded from the evaluator's model context.
5. `run_backtest` calls the existing Desk engine against the existing snapshot and SPY. It computes metrics and compares them with human-configured thresholds. The model cannot manufacture a backend PASS or change weights/windows. The result includes limitations.
6. The executor can submit orders only after backend PASS, adversarial approval, trading permission, any required human approval, and a cleared stop. The moderator can engage the stop; only a person can clear it.

The roster supports sixteen agents and four active workers, including waiting parents. Reuse idle specialists; do not launch every role concurrently. The orchestrator has 24 model iterations, specialists 12, and the evaluator 3. Iteration exhaustion is an error, not successful task completion. A branch stop still cancels agent workers and descendants; it does not cancel accepted brokerage orders.

## Human controls

`GET /api/desk` returns the default board's records. For a fund, use `GET /api/funds/{fund_id}/desk`. The same two prefixes support:

- `PUT .../policy`: required universe, max_position and max_drawdown as fractions, min_sharpe, min_excess_return as a fractional return difference, max_order_notional in dollars, and max_daily_orders. `trading_allowed` defaults to false and `approval_required` to true. The evaluation owner must choose thresholds; there are no implied risk-band defaults.
- `PUT .../stop` with `{"stopped": true|false, "reason": "..."}`.
- `POST .../strategies/{strategy_id}/approve` for human strategy approval.

These routes use the app's existing human login boundary. Worker requests cannot change policy, grant approvals or clear the stop. Updating policy engages the stop and invalidates human approvals; tests must match the current policy hash. The per-fund dashboard mandate is also checked when executing.

Policy, strategy, review, test, approval, order and moderator records are persisted in `desk.json` beside that fund's roster, outside the agent-visible shared workspace. The human desk endpoint provides the audit view; tool results also appear in canvas activity. There is no new trading-controls screen in this change.

## Paper execution

The backend needs `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`, or `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`. Store them in ignored environment files or the existing deployment secrets. No keys are sent in model tool arguments. The API host is fixed to `https://paper-api.alpaca.markets`; a live-account URL setting cannot redirect it. See the official [paper-trading documentation](https://docs.alpaca.markets/us/docs/paper-trading) and [order endpoint](https://docs.alpaca.markets/us/reference/postorder).

Orders are market/day, long-only, dollar-notional orders against a registered strategy. Before submission the backend checks cash, current positions, pending orders, target/mandate exposure, order count, notional limits and stop. One shared broker lock serializes submissions across funds. A stable `client_order_id` is saved before the network call. Reusing it returns the recorded result; changing its request is rejected. An uncertain response is recorded as `unknown` and is not automatically resubmitted. Broker acceptance is not a fill. The account tool returns current positions and open orders; stored submission receipts are not a full fill-reconciliation service.

The adapter uses the configured shared paper account, not independent brokerage subledgers per fund. It counts all account positions and pending orders conservatively. Fund execution is blocked when cash reserve, sector, exclusions or rebalance constraints lack matching enforcement/evaluation support. It must not silently ignore those settings. Missing credentials produce an explicit error; no fake fill or successful dry run is returned.

## Evaluation limits and verification

Historical evaluation currently reuses the recorded monthly-rebalanced, fully invested, long-only target-weight engine and actual cached prices. It does not execute generated Python strategies, ingest Alpaca history, implement a historical brokerage clock, add transaction costs/dividends, or provide walk-forward significance. A requested test end beyond the snapshot is rejected rather than silently shortened. Model-memory leakage and the provenance of strategy research still matter; hiding research from the evaluator does not make retrospective strategy selection unbiased. Native live tools must not supply evidence for a past decision.

Verification covers API role denials, delegation escalation, fund isolation, frozen evaluator input, persistence, actual snapshot metrics, review/approval/stop gates, paper-host selection, projected exposure and duplicate/uncertain submissions. Brokerage responses are mocked. Worker registry diagnostics in the built image verify every role's actual tools without a model call:

```sh
bun --tsconfig-override /app/vendor/dexter/tsconfig.json /app/backend/worker/run.ts --list-tools
```

The server sets `LOCAL_AGENT_ROLE` and `AGENT_ALLOWED_TOOLS`; standalone diagnostics with no permissions return an empty registry. Local verification does not establish a hosted rollout or a real Alpaca/Bedrock execution of this workflow.
