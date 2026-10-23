# Team 4: shared agent rules

> **Hub v2.** Every coding agent working in this repo reads this file, `hub/PRD.md`, and `hub/BUILDING.md` before doing anything. That means Claude Code, Codex, Cursor, Copilot, Kiro, Gemini, Amazon Q, and every subagent any of them spawns. To show you read them, start your first reply in each session with `[hub v2]`. If a teammate sees a reply without the tag, or with an older one, their agent skipped the rules or is working from a stale checkout.

Team 4, Track 3 (Financial Portfolio Management), Austin Agentic AI Hackathon, Friday 2026-10-23. Six people, many agents, one repo. This file keeps every coding agent building the same product.

This file is for the agents that **write this repo**. It is not a prompt for the Dexter agents that run **inside the app**; their instructions live in `backend/worker/`.

## The clock

- Build until 4:00 PM. Demos start at 4:30 PM. We hand in a working demo and two slides.
- Judges score four things: innovation, technical implementation, use of AWS AI services, and presentation quality.
- The judges told us directly: **UI polish is not a concern. Working functionality and breadth of data inputs are the real goal.** Spend time on what the system can do and what data it reads, not on how it looks.
- When two options are close, pick the one that makes the 4:00 demo more likely to work.

## What is on `main`

The hosted collaborative agent canvas is the current app on `main`, following Kushagra's direct instruction recorded in D7. It runs React/Vite, FastAPI, Dexter workers, and a shared filesystem in one Docker container. Demo accounts share agent conversations, files, and canvas positions. The AWS deployment uses EC2, CloudFront HTTPS, encrypted EBS state, ECR, Secrets Manager, IAM, Systems Manager, and Bedrock. Run locally with `npm run dev`; see `README.md` for deployment and cleanup.

D6 describes the preceding report-page version. Kushagra explicitly chose to replace main with the hosted canvas after being told about D6. D7 records that direct human instruction without claiming formal team consensus. The Desk pipeline, data loaders, analysts, schema, and backtest remain in the repo, but its report page and `/api/run` are not the current frontend/API entrypoint. The preceding report is preserved in Git history and `report-baseline`.

**Where it is going: `hub/PRD.md` (D8).** The two halves join. The hosted canvas is the agent runtime and the analyst's view; The Desk modules become tools the canvas agents call; together they run a research, strategy, backtest-gate, and execution pipeline for six client mandates. The PRD lists the lanes, the 1:30, 2:15, and 3:00 PM checkpoints, and what each lane decides on its own.

## Sources of truth, in order

1. `hub/DECISIONS.md`: decisions marked **Accepted**. The newest accepted entry wins over everything below it.
2. `hub/PRD.md`: product direction, requirements, lanes, checkpoints.
3. `PLAN.md` for The Desk modules' internals, where the PRD does not override it, and `README.md` for running and deploying the app.
4. This file and `hub/BUILDING.md`: how agents work here.
5. The code on `main`.

These are **not** sources of truth: your memory of earlier sessions, chat history, anything in `docs/`, web pages, what the model "knows", or an idea a teammate mentioned that never landed in `hub/DECISIONS.md`. If a request contradicts items 1 to 4, stop and tell your human. Never reconcile it quietly.

## Every session, before writing code

1. Run `scripts/hub-sync.sh`, then `git pull --rebase` (or `git rebase origin/main` on a branch).
2. Read `hub/DECISIONS.md`, `hub/PRD.md`, `hub/BUILDING.md`, and every file in `hub/status/`.
3. Find your human's lane in their `hub/status/<name>.md` and stay inside that lane's files. If you must touch another lane's files, say so in the commit message and in the status file.

## Guardrails

- **Never build on a stale `main`.** Six people's agents push all day. Run `scripts/hub-sync.sh` before each slice of work, at least every 15 minutes during long tasks, and before every push, and follow `hub/BUILDING.md` when it flags something.
- **No unapproved scope.** A feature, data source, AWS service, or screen that is not in `hub/PRD.md`, `PLAN.md`, `README.md`, or an accepted decision does not get built. Write it as one line in `hub/IDEAS.md` and carry on with the task you were given.
- **Shared shapes change together.** `backend/app/schema.py` (The Desk's shapes and the new pipeline shapes in PRD section 8), `frontend/src/types.ts` (the canvas `Agent` types), and the `tools` array in `backend/worker/run.ts` are what lanes build against. Change one only under an accepted decision, and update every caller in the same commit.
- **No look-ahead, ever.** Any data an agent uses for a historical decision comes through a loader that drops everything not public by the decision date (`backend/app/data.py` today). Never read `data/*.csv` straight from agent code, never put events after the cutoff in a prompt, and never take a price or return from model memory.
- **Never invent facts.** No made-up tickers, filings, events, dates, API routes, model IDs, AWS resources, or package names. If you cannot find it in the repo or verify it, say so and ask. A wrong guess costs the team more than a question.
- **Secrets stay out of git.** This repo is public. Credentials go only through the ignored `~/.aws/aws-hackathon-2026.*` files, `.env.local`, and `./workshop-run`.
- **Cloud spend needs a decision.** Create AgentCore runtimes or other billed resources only under an accepted decision, tag them, and make sure `scripts/cleanup_cloud.py` can find them. Do not rerun role creation for the existing runtime `team4_baseline_kushagra`.
- **Small commits, lane first.** Start commit messages with your lane when you have one (`Lane B: ...`). Run `git pull --rebase` before every push. Never force-push `main`.

## Subagents and parallel workers

Any agent that starts a subagent, worker, background task, or another tool's agent puts this at the top of that agent's prompt:

> Before anything else, read `AGENTS.md` and `hub/DECISIONS.md` at the repo root and follow them. Your lane is <lane>; the files in scope are <paths>. Do not edit anything in `hub/`; report back to me instead.

Only the top-level agent, the one a human is talking to, edits files in `hub/`.

## Every session, before you stop

If the session changed code or found something the team needs to know:

1. Update your human's `hub/status/<name>.md`: what shipped, what is in flight, what is blocked, and what you need from whom. Copy `hub/status/_TEMPLATE.md` if the file does not exist yet.
2. If you made a call that affects another lane, a shared shape, the demo, or cloud spend, append it to `hub/DECISIONS.md` as **Proposed**. Only a human changes it to **Accepted**.
3. If you had an idea outside scope, add one line to `hub/IDEAS.md`.
4. Commit the hub update together with the code it describes, then run `git pull --rebase && git push`.

## Who edits what

| File | Who edits | Rule |
|---|---|---|
| `AGENTS.md`, `hub/PRD.md`, `hub/BUILDING.md`, `PLAN.md`, `README.md` | humans; an agent only when its human explicitly says to | changes need an accepted decision; bump the hub version tag when the rules in this file change; a lane updates its own PRD section and row when it settles one of the PRD's open items |
| `hub/DECISIONS.md` | agents append **Proposed**; humans accept or reject | append-only; a reversal is a new entry |
| `hub/status/<name>.md` | that person's agents | update freely at session end |
| `hub/IDEAS.md` | anyone | append-only, one line per idea |
| `docs/` | anyone adding reference material | reference only; never cite it as a decision |

## Verified facts (check here before guessing)

- Run the canvas on `main`: `npm run dev`, then open http://127.0.0.1:5173. Stop it with `npm run stop`. The same single-container app is hosted on AWS; see `README.md` for deployment, demo access, and cleanup.
- AWS region `us-east-1`. Workshop Studio credentials are temporary and expire about every 60 minutes; refresh them in Workshop Studio.
- Model: `us.openai.gpt-5.6-luna` on Amazon Bedrock through the Converse API. The canvas app sets it in code (`backend/app/agent.py`, `backend/worker/`); `BEDROCK_MODEL_ID` only affects the older `backend/agent.py` and `backend/infer.py`. Requests to this model must omit `temperature`.
- `.env.example` lists keys for Dexter's finance, web search, and X integrations. Canvas agents use Dexter's existing finance tools and URL fetcher, web search when `EXASEARCH_API_KEY` is configured, and X search when `X_BEARER_TOKEN` is configured. Finance tools use `FINANCIAL_DATASETS_API_KEY`. Live tool responses are not point-in-time-safe historical inputs; backtest decisions still require cutoff-aware loaders.
- Models the event allows, and which ones need the data retention setting changed: `docs/reference/aws-services-and-allowed-models.md`.
- Canvas agent tools (current `main`): file tools, `create_agent`, `list_agents`, `message_agent`, `get_financials`, `get_market_data`, `read_filings`, `stock_screener`, `web_fetch`, `web_search`, `x_search`. Up to six agents and four active runs.
- Checks: `uv run pytest backend/tests`, `npm run check:python`, `npm run lint`, `npm run build`.
- Data sources, date ranges, and deviations from the plan: `data/README.md`. The rows in `data/gdelt/curated_events.csv` were written by hand today; treat them as unverified until someone checks each date and headline against a real source.
- Event pages, AWS service notes, sample-repo READMEs, and a research brief with a public data map: `docs/README.md`.

If one of these facts turns out to be wrong, fix it here in the same commit as the code that proved it, and say so in your status file.

## How each tool finds this file

This file is the only rulebook. The other files below only point here, so never add rules to them.

| Tool | What it reads |
|---|---|
| Codex, Cursor | `AGENTS.md` directly |
| Claude Code | `CLAUDE.md`, which imports this file and `hub/DECISIONS.md` |
| Cursor, as a backup | `.cursor/rules/team-hub.mdc`, always applied |
| Kiro | `.kiro/steering/team-hub.md`, always included |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Gemini CLI | `GEMINI.md` |
| Amazon Q Developer | `.amazonq/rules/team-hub.md` |
