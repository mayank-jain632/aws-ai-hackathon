# Dedicated Dexter roles

These roles extend the pinned upstream Dexter `Agent` and native tools. They do not introduce another agent loop. `backend/app/roles.py` is the capability registry; `GET /api/agent-roles` exposes it. The canvas shows each agent's role. New boards start with one orchestrator; specialists are created on demand, retain separate histories, and share files inside their fund.

| Role | Available work | Delegation |
|---|---|---|
| `orchestrator` | Every registered capability, including research, strategy, review, evaluation, paper execution and stop, subject to backend checks | Create and message any descendant role, including orchestrators |
| `research` | Native finance and ownership data, filings, screening, Exa/URL/X, live FRED, Jev sentiment, optional Apify and shared files | Create and message any descendant role |
| `adversarial` | Challenge research/strategy with native evidence; record APPROVE or CHANGES_REQUESTED | Create and message any descendant role |
| `strategy` | Research, write declarative target weights, register an immutable strategy | Create and message any descendant role |
| `backtester` | `run_backtest` plus delegation restricted to its bound strategy ID | Create/message only same-strategy blind backtesters |
| `executor` | Native web search, URL fetch, market data; paper account and guarded paper orders | Create and message any descendant role |
| `moderator` | Inspect desk, inspect paper account, engage emergency stop | Create and message any descendant role |

Native finance tools use `FINANCIAL_DATASETS_API_KEY`. Exa web search and X search appear only when their existing keys are configured. No extra search client or custom research API is introduced. Research-capable profiles also include all direct native finance inputs plus `analyze_sentiment`, `get_macro_series`, `apify_actor`, and `apify_run`. Jev alone uses OpenRouter; other model calls stay on Bedrock. The backtester never gets native research or file tools. Its delegation and descendant roster are restricted to blind evaluators of the same immutable strategy, with sanitized context and file lists.

The model's tool list is filtered from server-owned permissions, and backend tool routes check the authenticated agent's role. Non-blind agents may request other role types, including an executor or another orchestrator, while retaining their own role identity and direct tool restrictions. Children do not inherit the parent's tool set. Parent-child ownership and fund token lookup remain enforced. Old root agents become orchestrators; old specialists default to research. Roles survive roster reloads.

The human's written role and tool requirements take priority over the supplied flow diagram. The roster stays flexible: one root can create additional orchestrators and task-focused research agents. The diagram's five research groups, separate order-planner box and significance box are context, not a fixed roster or proof those extra capabilities exist.

## Handoffs

1. Give the orchestrator a concrete task and evidence/date context. It creates research specialists for the needed data families. Research and strategy instructions require adversarial challenges.
2. A strategy developer calls `register_strategy` with positive long-only weights summing to one, cutoff/end dates, memo paths, rationale and change triggers. Revisions receive new IDs; agents cannot edit registered records through files.
3. A separate adversarial agent records its review using `review_strategy`. A backtester cannot be created until the registered strategy has an approving review.
4. The orchestrator calls `create_agent` with `role: "backtester"` and that `strategy_id`. Backend-generated input contains only the ID, weights and dates. User task text, the chosen display name, prior conversations, file names and fund free-text context are excluded from the evaluator's model context.
5. `run_backtest` calls the existing Desk engine against the existing snapshot and SPY. It computes metrics and compares them with human-configured thresholds. The model cannot manufacture a backend PASS or change weights/windows. The result includes limitations.
6. The executor can submit orders only after backend PASS, adversarial approval, trading permission, any required human approval, and a cleared stop. The moderator can engage the stop; only a person can clear it.

The roster supports sixteen agents and four active workers. Additional runs queue. A parent releases its active worker slot during delegation and reacquires it before resuming; concurrent sibling tool calls share one suspended parent. Waiting/queued identities remain visible, and branch cancellation includes queued descendants. Reuse idle specialists. The orchestrator has 24 model iterations, specialists 12, and the evaluator 3. Iteration exhaustion is an error, not successful task completion. A branch stop still cancels agent workers and descendants; it does not cancel accepted brokerage orders.

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

The server sets `LOCAL_AGENT_ROLE` and `AGENT_ALLOWED_TOOLS`; standalone diagnostics with no permissions return an empty registry. A real Bedrock orchestrator → research → strategy → adversarial handoff wrote and verified a shared file in an ephemeral test container, without orders or market-data calls. This verifies recursive role/file wiring, not a complete investment run, hosted rollout, or real Alpaca execution.

## Alpaca deployment verification

On 2026-10-23, AWS-Hack paper account `PA33F249I` was connected locally and to the existing AWS Secrets Manager environment. The existing EC2 service reloaded the credentials without changing its image. Both the deployed backend and a real hosted Bedrock/Dexter `alpaca_paper_account` call returned ACTIVE/USD, $100,000 cash/equity, no positions and no open orders. CloudFront login and health passed. No orders were submitted; strategy evaluation, human approvals and execution guards still apply. Account balances are a verification snapshot, not a continuing performance claim.

## Agent models

GPT-6.1 Sol is the default. Claude Opus 5.5 is the alternate for orchestrators and non-blind specialists. Use the model selector in the existing agent panel while the agent is idle. Choices persist per agent and fund. New specialists inherit their parent's choice unless `create_agent.model` explicitly selects the other main model. Existing agents without a saved choice migrate to the configured default without losing conversations or files.

Backtesters and their blind descendants always use Claude Opus 4.6. Human selection and delegation cannot change that pin. The selected profile also drives nested native finance calls; there is no silent provider/model fallback.

`backend/model-catalog.json` holds the verified Bedrock US profile IDs used by Python, Bun and deployment IAM. `MAIN_AGENT_MODEL` sets the default for agents without a saved choice. `GET /api/agent-models` lists the catalog. A person can `PUT /api/funds/{fund_id}/agents/{agent_id}/model` with `{"model":"us.openai.gpt-6.1-sol"}`; the original board also supports `/api/agents/{agent_id}/model`. Running agents reject changes. Worker credentials cannot use this human control.

Availability check on 2026-10-23: the AWS catalog lists all three profiles, but actual Dexter invocations using the workshop participant credentials explicitly deny both Sol 6.1 and Opus 5.5 in IAM. Their configuration is implemented, but successful inference is blocked with those credentials. A real Opus 4.6 bound evaluator completed its authenticated `run_backtest` against cached historical prices with zero orders. The hosting script includes all three profiles and retains Luna for the separate watchdog second opinion; this does not override workshop restrictions or prove hosted access. Hosted follow-up at 13:28 CDT: both Sol and Opus 5.5 agreement/authorization/entitlement/region checks report available. An actual authenticated Sol/Dexter run on image `1792779772` called native X and Financial Datasets tools successfully and completed in three model turns. This clears the hosted Sol activation blocker; local workshop participant permissions are separate.

[AWS lists Opus 4.6's knowledge cutoff as May 2025](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-6.html). That overlaps the existing historical test window. The pin does not eliminate model-memory leakage. Numeric-only evaluator input, restricted tools and deterministic backend metrics remain necessary.
