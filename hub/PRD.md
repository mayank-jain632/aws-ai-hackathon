# Product: agentic portfolio desk

Product direction is D8. This document separates the existing system from the work needed to finish it. `README.md` covers running and deploying; `hub/status/` records each lane's current work. A feature listed as a target is not a claim that it is implemented or deployed.

## 1. Product and existing foundation

A wealth-management team creates funds and client mandates, then uses agents to research investments, propose strategies, evaluate them against historical evidence, and execute approved paper trades. People can inspect and direct the agents, read their work, change mandates, and stop execution. Keep the interactive canvas; do not replace it with a report-only application or a separate agent framework.

| Already built | Implementation and boundary |
|---|---|
| Local single-container app | One Dockerfile builds one image; one container serves React/Vite, FastAPI, and Bun/Dexter workers. `npm run dev` starts it at port 5173. |
| Real Dexter agent loop | Pinned upstream `Agent`, with Bedrock integration and a selected tool registry in `backend/worker/run.ts`. This is not a placeholder loop. |
| Recursive agents | Agents create and message their own descendants. Conversations stay separate; agents on one board share a filesystem. Parent stop cancels its descendants. |
| Collaborative canvas | Shared roster, chats with author attribution, activity, files, dragged positions, and connection count over SSE. Pan, zoom, selection, and collapsed branches are personal. |
| Fund workspace on main | Fund creation, mandate presets/editing, overview, pause/archive controls, and per-fund canvases are merged. The original board is preserved as Team 4 fund; new funds have separate runtime storage. AWS rollout is not established by a merge. |
| Demo login | Kush, Mayank, and Gerson demo accounts share the board. Credentials stay outside Git. Reuse this login. |
| AWS hosting | EC2 runs the container; CloudFront provides HTTPS; encrypted EBS stores state; ECR stores images; Secrets Manager stores secrets; IAM supplies Bedrock credentials; Systems Manager manages the host. |
| Native Dexter research tools on main | Finance, market data, SEC filings, screening, URL fetch, Exa web search, and X search reuse upstream implementations. See the registry and README for key requirements. Their presence on main does not prove the hosted image is updated or providers have been tested live. |
| Additional live research inputs | Native direct finance/earnings/ownership tools, live FRED series, Jev sentiment via OpenRouter Decisions only, and optional Apify public-web collection. Role permissions still apply; see `docs/data-sources.md` for credential and verification limits. |
| Historical analysis modules | `backend/app/data.py`, `backend/app/agents/`, `backend/app/backtest.py`, and `backend/app/schema.py` retain the Desk loaders, analysts, portfolio-manager logic, and backtest. Their former report page is historical, not the current app. |

The last deployment verified by this chat ran Bedrock delegation and shared file tools, demo login, collaboration, and restart persistence. Verify the deployed image before claiming newer tools are live.

## 2. Reuse before adding

**Extend Dexter, do not rebuild its capabilities.** Inspect the pinned upstream registry first, then import and enable its existing tools in our adapter and allowlist. Configure their existing environment keys. Add a provider client or equivalent tool only when a documented requirement cannot be met by the upstream implementation.

- Exa uses Dexter's `exaSearch` / `web_search`, not a second Exa client or a parallel search API.
- Financial Datasets, filing readers, market data, screening, URL fetch, and X follow the same rule.
- Keep our delegation bridge because it manages persistent, visible canvas agents and ownership. Do not replace it with an isolated upstream subagent implementation that loses board identity or the shared filesystem.
- Thin checks for authentication, role permissions, mandates, provenance, and historical cutoffs are legitimate integration code. A new wrapper name alone is not a new capability.
- Reuse the Desk loaders and backtest for historical evaluation. A current-data tool is not a point-in-time historical loader.
- Keep one app container and existing storage/deployment controls. New AWS services must have a concrete role; do not claim that the canvas currently runs on AgentCore.

## 3. Target workflow

```text
fund + client mandate
  -> orchestrator
  -> research specialists <-> adversarial review
  -> quant / strategy proposal
  -> isolated backtest and backend pass/fail gate
  -> paper execution, only with a passing result and permission
  -> moderator checks / emergency stop
```

Use role-specific instructions and backend-enforced capabilities around the existing Dexter loop. The orchestrator coordinates; researchers gather cited evidence; adversarial agents challenge assumptions; the strategy agent produces a testable proposal; the backtester receives a frozen strategy and numeric data, not open-ended research access; the executor receives only approved orders. Role capabilities, frozen strategy/review records, numeric-only evaluator input, existing snapshot-backtest gates and guarded Alpaca paper-order code are implemented and locally verified. The owning status and `docs/agent-roles.md` record their limits. Real provider execution and hosted rollout of this workflow remain unverified; this does not establish a completed autonomous pipeline.

The backtest agent having no research context does not remove model-memory leakage. Report the actual evaluation assumptions and limitations.

## 4. Requirements still to complete

1. Connect the now-merged fund creation, mandate setup, overview, and per-fund canvas to the strategy/evaluation/execution workflow. Preserve the legacy Team 4 board and enforce shared files within a fund with isolation between funds. Dashboard metadata is not proof that trading limits are enforced.
2. Six client mandates across conservative, balanced, and aggressive risk bands. Record allowed assets, capital, position/drawdown limits, and explicit paper-trading permission. These client mandates are not the three demo login accounts.
3. A persisted run record linking research, adversarial review, strategy, evaluation, and proposed/executed orders. Expose useful progress and artifacts through the existing canvas and fund overview.
4. A backend evaluation gate using recorded metrics and stated risk-band thresholds. The model cannot approve itself, invent returns, or treat an unfinished run as a successful gate.
5. Alpaca paper execution with recorded broker order IDs and actual simulated fills. Recheck permission, limits, available capital, passing evaluation, and emergency stop before every order. A submitted order is not yet a fill.
6. Moderator checks and a human-accessible stop. Keep the existing branch stop; it cancels agent work and does not by itself cancel outstanding broker orders.
7. A repeatable demo showing a strategy, agent work, evaluation, and paper execution or an explicitly blocked order. Missing credentials are an unavailable integration; a dry run never masquerades as a broker fill.
8. AgentCore integration where it serves a defined requirement, with a real invocation/trace before claiming it works. Existing Bedrock and AWS hosting remain the verified foundation.

Optional evaluation work includes walk-forward results, confidence intervals, masked-ticker checks, and user-supplied data. None is already implemented merely because it appears here.

## 5. Two modes, real evidence

| Mode | Evidence | Execution and results |
|---|---|---|
| Live paper | Current provider data and Dexter's web/X research. Use a quote/market-data provider for prices, not search snippets. | Alpaca paper account, simulated funds, recorded broker orders/fills and portfolio state. |
| Historical replay | Real dated prices, filings, economic releases, and verified historical events available at the simulated timestamp. | Local simulated cash, orders, fills, and valuation using stated next-bar/cost assumptions. Alpaca paper cannot execute against a historical clock. |

Do not add fictional companies, fabricated news/social posts, or injected fictional events. Synthetic fixtures may exercise tests, clearly labeled, but are not investment evidence or demo performance. Historical evidence must pass cutoff-aware loaders. Live search, current financial APIs, and current X results must not enter historical decisions.

Existing historical baseline: ten stocks plus SPY, daily price snapshots through 2025-06-30, monthly rebalancing, equal-weight and SPY comparisons, and no transaction costs or dividends. See `PLAN.md` and `data/README.md` for the baseline's exact method. Fifteen stocks, refreshed windows, risk-band thresholds, and execution costs are targets until the evaluation lane records the chosen method. Do not silently change them.

Data limitations: SEC facts may include revisions; FRED availability dates are approximations; curated event headlines and tone scores are hand-written and unverified; a GDELT tone snapshot may be absent. Verify or exclude questionable evidence, and report missing sources rather than inventing replacements.

## 6. Lane boundaries

| Lane | Responsibility | Build on |
|---|---|---|
| 1. Orchestration / roles | Role capabilities, phase handoffs, shared pipeline shapes, strategy integration | Existing Dexter loop and persistent canvas delegation |
| 2. Evaluation | Strategy contract, historical replay/backtest, thresholds and leakage checks | Existing loaders and backtest; recorded method |
| 3. Data / research | Enable native Dexter providers, verify inputs and provenance, historical adapters where needed | Upstream tool implementations and existing loaders |
| 4. Execution / moderator | Alpaca paper adapter, order state, permission/risk checks, emergency stop | Approved strategy/evaluation records |
| 5. Platform / canvas | Funds, collaborative canvas, hosting, persistence, deployed-image verification, scoped AgentCore integration | Working single-container app and AWS deployment |
| 6. Demo / pitch | Demo sequence, evidence, slides and this product description | Actual verified features and recorded outputs |

Current assignments and files in progress are in `hub/status/`; do not infer ownership from this table. Fund/dashboard work is now merged; typed-role/pipeline work has an active claim. Coordinate rather than building duplicates.

## 7. Done means verified

- State separately: implemented on main, checked locally, deployed, and exercised against a real provider.
- Keep existing demo accounts, collaboration, conversations, files, and restart persistence working.
- Update callers with shared contracts. Use tests appropriate to the change and preserve existing passing checks.
- Never present pending tools, mocked responses, dry runs, or proposed infrastructure as completed functionality.
- Record remaining gaps in the owning status file. Keep credentials, account passwords, provider keys, and private run files outside Git.
