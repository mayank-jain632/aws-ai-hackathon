# Team 4: shared agent rules

**Hub v3.** Before working, read this file, `hub/DECISIONS.md`, `hub/PRD.md`, `hub/BUILDING.md`, and `hub/status/`. Start the first reply in a session with `[hub v3]`. These instructions govern coding agents editing the repository, not Dexter agents running inside the product.

Team 4, Financial Portfolio Management, Austin Agentic AI Hackathon, 2026-10-23. Judging emphasizes functionality, data inputs, AWS AI use, and a working presentation. Preserve the existing app while extending it.

## Current system and direction

`main` is a collaborative agent canvas, not the earlier report page. One Docker image/container serves React/Vite, FastAPI, and Bun workers running the pinned upstream Dexter Agent. Agents own descendants, share a filesystem within a board, and retain separate conversations. Demo login, shared chats/files/activity, synchronized positions, branch controls, and state persistence already exist.

The verified AWS deployment uses EC2, CloudFront HTTPS, encrypted EBS, ECR, Secrets Manager, IAM, Systems Manager, and Bedrock. It is not an AgentCore-hosted canvas. The earlier AgentCore sample is separate. Run locally with `npm run dev`; stop with `npm run stop`. See `README.md` for credentials, deployment, and cleanup.

D8 joins this runtime with portfolio research, strategy, evaluation, and paper execution. Fund creation, mandate setup, overview, pause/archive controls, and isolated per-fund canvases are merged on main. Typed roles and pipeline enforcement remain in flight; verify deployments separately. The Desk loaders, analysts, schema, and backtest remain available for reuse. Do not rebuild the runtime or revive the old report as the main interface.

## Sources of truth

1. Accepted decisions in `hub/DECISIONS.md`, newest applicable entry first.
2. `hub/PRD.md` for direction and requirements.
3. `README.md` for setup/deployment; `PLAN.md` for historical module internals not superseded by the PRD.
4. This file and `hub/BUILDING.md` for collaboration and implementation rules.
5. Actual current code for what is implemented, plus verification records for what has been exercised or deployed.

The PRD is a target, not proof of implementation. Status files identify active work; older reference documents and chat recollections do not establish current behavior. Surface conflicts before overwriting another lane's work. When the human has explicitly resolved a conflict in the current task, record that instruction rather than repeatedly requesting the same approval. Agents append Proposed decisions; only humans mark Accepted or Rejected.

## Before writing and before pushing

- Run `scripts/hub-sync.sh`, then integrate with `git pull --rebase` or `git rebase origin/main` from a clean checkout. Re-read changed shared files.
- Read every status file and stay in your lane's claimed files. Coordinate cross-lane changes and name them in the commit/status update.
- Re-sync before each slice, at least every 15 minutes during long work, and before pushing. Preserve other agents' uncommitted edits. Never force-push main.
- Follow `hub/BUILDING.md` for integration and checks. Update your own status and relevant proposed decisions with the code they describe. Commit messages start with the lane when applicable.

## Reuse before rebuilding

**Inspect Dexter before adding an equivalent capability.** `backend/worker/setup.py` pins upstream revision `534f6be455523c5926eba72bdaf4f914555be5c9`. Read its tool registry and provider module, then our override/allowlist in `backend/worker/run.ts`.

Enable existing upstream finance, market-data, filing, screening, URL-fetch, Exa, and X implementations before writing another client or tool. Exa uses Dexter's `exaSearch` / `web_search`. Do not create a second Exa API implementation. Configure the existing environment keys and verify the actual worker path.

Custom code is for missing product behavior: persistent canvas delegation, authentication, role restrictions, mandate checks, execution approval, and point-in-time adapters. Reuse Desk loaders/backtest where appropriate. Keep Dexter's Agent as the loop; a new role does not need a new agent framework.

Changing a registry also means checking the allowlist, descriptions, model routing, callers, and role permissions. Adding a key or dependency alone does not enable or verify a tool.

## Data and execution boundaries

- Historical decisions use real evidence available by the cutoff, through cutoff-aware loaders. Never use current search, financial API responses, or model memory as historical prices, returns, or events.
- Live research and real historical replay are separate modes. No fictional market data, fabricated posts/news, or invented performance. Existing synthetic fixtures are tests only; hand-written event data remains unverified until checked.
- Do not claim a revision-prone snapshot is a perfect historical vintage. Report SEC/FRED/event limitations and absent sources.
- Paper execution only. Backend checks enforce mandate permission, passing evaluation, limits, and emergency stop. Orders, fills, dry runs, and blocked actions are distinct states. Do not invent a fill when credentials or execution are unavailable.
- A branch stop cancels agent work; it is not automatically a brokerage cancel-all. Agent iteration exhaustion is not proof a task or gate succeeded.

## Scope, contracts, and secrets

- Build authorized requirements from the PRD, README, PLAN, accepted decisions, or the human's explicit task. Put optional unrelated ideas in `hub/IDEAS.md`.
- Coordinate shared contracts in `backend/app/schema.py`, `frontend/src/types.ts`, and the worker registry; update actual callers together. Do not assume the Desk schema and canvas Agent types are the same contract.
- Preserve the one-container app, existing accounts, collaboration, and user-created data. Within a board/fund agents share files; do not introduce per-agent filesystems or cross-fund access.
- Credentials stay in ignored `.env`, `.env.local`, dedicated `~/.aws/aws-hackathon-2026.*` files, or AWS Secrets Manager. Never commit keys, demo passwords, session secrets, or private run data.
- New billed AWS resources require an accepted decision or explicit human authorization, ownership tags, inventory, and a scoped cleanup path. Existing hosting uses `scripts/hosting.py --cleanup`; the earlier AgentCore sample uses `scripts/cleanup_cloud.py`. Never rerun its role setup or modify workshop desktops incidentally.
- Do not call proposed tools, local code, mocked responses, or an old image a verified live deployment.

## Verified implementation facts

- Bedrock model: `us.openai.gpt-5.6-luna`, through Converse; omit `temperature`. Canvas defaults live in code. `BEDROCK_MODEL_ID` applies only to the older sample helpers.
- Native registry on main: file tools; `create_agent`, `list_agents`, `message_agent`; `get_financials`, `get_market_data`, `read_filings`, `stock_screener`, `web_fetch`; `web_search` with `EXASEARCH_API_KEY`; `x_search` with `X_BEARER_TOKEN`. Finance uses `FINANCIAL_DATASETS_API_KEY`. Recheck the registry after syncing because role work is active.
- At this documentation pass, the base manager permits six agents and four active runs, and the worker uses eight iterations with memory disabled. Those are present limits, not permanent product requirements. Waiting parents occupy active-run capacity.
- No real Alpaca execution, full role-enforced pipeline, evaluation gate, or AgentCore canvas deployment is established by this inventory. Per-fund storage isolation exists on main; that does not establish an AWS rollout or multi-tenant security. Check the owning lane's merged code and verification before claiming them.
- Tests: `uv run pytest backend/tests`, `npm run check:python`, `npm run lint`, `npm run build`. Mock Desk helpers do not make the canvas an offline mock app.

## File ownership and agent coordination

The human has authorized this documentation correction across `AGENTS.md`, `hub/PRD.md`, `hub/BUILDING.md`, `README.md`, and stale baseline descriptions. Later edits to direction/rules still require human authorization or the lane's delegated PRD section, plus a proposed decision. Decisions are append-only; status files belong to their named person. Reference material in `docs/` is not another product specification.

If subagents or other workers are used, include this at the start of their task:

> Read AGENTS.md, hub/DECISIONS.md, hub/PRD.md and hub/BUILDING.md first. Your lane is <lane>; your files are <paths>. Do not edit hub/; report findings to the parent.

Only the top-level agent edits hub files. Tool entrypoints such as CLAUDE.md, GEMINI.md and editor rule files point here; keep rules in this file rather than copying them into each entrypoint.
