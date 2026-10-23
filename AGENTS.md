# Team 4: shared agent rules

> **Hub v1.** Every coding agent working in this repo reads this file before doing anything. That means Claude Code, Codex, Cursor, Copilot, Kiro, Gemini, Amazon Q, and every subagent any of them spawns. To show you read it, start your first reply in each session with `[hub v1]`. If a teammate sees a reply without the tag, their agent skipped the rules.

Team 4, Track 3 (Financial Portfolio Management), Austin Agentic AI Hackathon, Friday 2026-10-23. Six people, many agents, one repo. This file keeps every coding agent building the same product.

This file is for the agents that **write this repo**. It is not a prompt for the Dexter agents that run **inside the app**; their instructions live in `backend/worker/`.

## The clock

- Build until 4:00 PM. Demos start at 4:30 PM. We hand in a working demo and two slides.
- Judges score four things: innovation, technical implementation, use of AWS AI services, and presentation quality.
- The judges told us directly: **UI polish is not a concern. Working functionality and breadth of data inputs are the real goal.** Spend time on what the system can do and what data it reads, not on how it looks.
- When two options are close, pick the one that makes the 4:00 demo more likely to work.

## What is on `main`

One product (D6 in `hub/DECISIONS.md` answered Q0):

**The Desk pipeline behind a plain report page.** Cutoff-filtered data loaders in `backend/app/data.py`, five analyst agents and a portfolio-manager agent in `backend/app/agents/`, the backtest in `backend/app/backtest.py`, the `RunResponse` shape in `backend/app/schema.py`, and `POST /api/run` in `backend/app/main.py`. The frontend (`frontend/src/`) is a single-column report: results vs the equal-weight baseline, the allocation with the PM's rationale, and each analyst memo with its cited sources. Run it with `npm run dev:backend` and `npm run dev:frontend`; see `README.md`.

The **agent canvas** (Docker sandbox, Dexter agent tree) lives on branch `agent-canvas`. Its worker code stays in `backend/worker/`, `compose.yaml` and `backend/Dockerfile` on `main` so it can be revived, but nothing on `main` runs it.

Next phase: a PRD on breadth of analysis variables and statistical significance of the backtests. Until it lands in `hub/DECISIONS.md`, ask your human before adding a new data input or changing the experiment definition.

## Sources of truth, in order

1. `hub/DECISIONS.md`: decisions marked **Accepted**. The newest accepted entry wins over everything below it.
2. `PLAN.md` for The Desk pipeline, and `README.md` for the agent canvas and how to run the app.
3. This file: how agents work here.
4. The code on `main`.

These are **not** sources of truth: your memory of earlier sessions, chat history, anything in `docs/`, web pages, what the model "knows", or an idea a teammate mentioned that never landed in `hub/DECISIONS.md`. If a request contradicts items 1 to 3, stop and tell your human. Never reconcile it quietly.

## Every session, before writing code

1. Run `git pull --rebase`.
2. Read `hub/DECISIONS.md` and every file in `hub/status/`.
3. Find your human's lane in their `hub/status/<name>.md` and stay inside that lane's files. If you must touch another lane's files, say so in the commit message and in the status file.

## Guardrails

- **No unapproved scope.** A feature, data source, AWS service, or screen that is not in `PLAN.md`, `README.md`, or an accepted decision does not get built. Write it as one line in `hub/IDEAS.md` and carry on with the task you were given.
- **Shared shapes change together.** `backend/app/schema.py` (The Desk's `RunResponse`) and `frontend/src/types.ts` (the canvas `Agent` types) are what lanes build against. Change one only under an accepted decision, and update every caller in the same commit.
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
| `AGENTS.md`, `PLAN.md`, `README.md` | humans; an agent only when its human explicitly says to | rule changes need an accepted decision; bump the hub version tag when the rules in this file change |
| `hub/DECISIONS.md` | agents append **Proposed**; humans accept or reject | append-only; a reversal is a new entry |
| `hub/status/<name>.md` | that person's agents | update freely at session end |
| `hub/IDEAS.md` | anyone | append-only, one line per idea |
| `docs/` | anyone adding reference material | reference only; never cite it as a decision |

## Verified facts (check here before guessing)

- Run the app on `main`: `npm run dev:backend` (FastAPI on 8000, through `./workshop-run` when it needs AWS) and `npm run dev:frontend` (Vite on 5173); see "Run it" in `README.md`. The Docker agent canvas is on branch `agent-canvas`; its sandbox builds with `npm run dev:canvas` and stops with `npm run stop:canvas`.
- AWS region `us-east-1`. Workshop Studio credentials are temporary and expire about every 60 minutes; refresh them in Workshop Studio.
- Model: `us.openai.gpt-5.6-luna` on Amazon Bedrock through the Converse API. The canvas app sets it in code (`backend/app/agent.py`, `backend/worker/`); `BEDROCK_MODEL_ID` only affects the older `backend/agent.py` and `backend/infer.py`. Requests to this model must omit `temperature`.
- `.env.example` lists keys for Dexter's finance, web search, and X integrations. Adding a key does not turn a tool on; the adapter only exposes file and delegation tools so far. Live data APIs return today's data, so anything used for a historical decision still has to pass the no-look-ahead rule above.
- Models the event allows, and which ones need the data retention setting changed: `docs/reference/aws-services-and-allowed-models.md`.
- Canvas agent tools (branch `agent-canvas`): `create_agent`, `list_agents`, `message_agent`. Up to six agents and four active runs.
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
