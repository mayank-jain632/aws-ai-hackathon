# Decisions

Append-only. Agents add **Proposed** entries. Only a human marks one **Accepted** or **Rejected**, by changing the status word and adding their name. To reverse a decision, add a new entry that names the one it replaces; never rewrite an old entry.

Entry format:

```
### D<n> · <Proposed | Accepted | Rejected> · <HH:MM> · <who>
**Decision:** one sentence.
**Why:** one sentence.
**Affects:** lanes, files, or the demo.
```

## Open questions (need a human call)

When the team answers one, delete it here and log the answer below as a decision. Questions that one lane can settle on its own live in `hub/PRD.md` section 12 instead.

- **Q11. One model or several?** Every call uses `gpt-5.6-luna` today. Mixing model families across agents shows more of Bedrock. See `docs/reference/aws-services-and-allowed-models.md` for what the event allows.

## Log

### D1 · Accepted · 10:55 · team
**Decision:** The first baseline is The Desk as specified in `PLAN.md`, built in Lanes A to C.
**Why:** It covers every requirement on the track page (commit `7cdec07`).
**Affects:** everyone.

### D2 · Accepted · 12:00 · team
**Decision:** Every coding agent coordinates through this hub: `AGENTS.md` at the root, plus `hub/DECISIONS.md`, `hub/status/`, and `hub/IDEAS.md`.
**Why:** Six people on different coding agents need one rulebook so stray ideas and invented facts do not derail the build.
**Affects:** every session in every tool.

### D3 · Proposed · 12:00 · Kushagra (logged by Aaron's agent)
**Decision:** Replace The Desk UI with the Docker agent canvas built on Dexter's agent loop (commits `aff6af5`, `4361ccc`).
**Why:** Gives people and agents a shared surface where agents create and message their own subagents.
**Affects:** frontend, `backend/app/main.py`; The Desk's `/api/run` route and UI are no longer on `main`. Needs the team to confirm, together with Q0.

### D4 · Accepted · 12:10 · Aaron
**Decision:** The agent interface covers both: agents trade on a market when the user allows it, and people interact with agents directly. We use the data from both.
**Why:** The human and agent sides each generate signal the portfolio can learn from.
**Affects:** Q0, Q1, Q2.

### D5 · Accepted · 12:10 · Aaron, relaying the judges
**Decision:** Put remaining effort into working functionality and breadth of data inputs, not UI polish.
**Why:** The judges said UI is not a concern and that functionality and data breadth are the real goal.
**Affects:** every lane; `PLAN.md` section 3 (visual direction) is no longer a priority.

### D6 · Accepted · 12:17 · Chaithu (logged by Claude Code)
**Decision:** Answer Q0: `main` carries The Desk pipeline behind a plain single-column report page (results vs baseline, allocation with rationale, analyst memos with sources); the agent canvas moves to branch `agent-canvas` and D3 is not adopted.
**Why:** D5 says functionality and breadth of data inputs win; the report page shows every input and backtest result directly, and `/api/run` is back on `main` so the pipeline is no longer stranded.
**Affects:** `frontend/` (canvas UI files removed), `backend/app/main.py` (`/api/run` and `/api/last-close` restored), root `package.json` (`dev:frontend`/`dev:backend` run directly again; the Docker sandbox is `dev:canvas`/`stop:canvas`), `README.md`. `backend/worker/`, `compose.yaml` and `backend/Dockerfile` stay in the tree for the canvas branch to reuse. Next phase is defined by a PRD (breadth of analysis variables, statistical significance of the backtests).


### D7 · Proposed · 12:34 · Kushagra, direct instruction recorded by Codex
**Instruction:** When asked whether to preserve the report on main or replace it with the hosted canvas, Kushagra explicitly selected: "Replace main with this hosted canvas".
**Implementation:** The current main UI and API entrypoint are replaced by the hosted collaborative canvas. The Desk data, analyst, schema, and backtest modules remain in the repository, and the prior report remains recoverable from Git history and report-baseline. Main's default command is again `npm run dev`, running the single-container app.
**Hosting:** Dedicated Team 4 EC2 instance, CloudFront HTTPS, encrypted EBS state, ECR image, Secrets Manager environment, scoped IAM role with Bedrock access, and Systems Manager management. Resource inventory and passwords are excluded from Git. `scripts/hosting.py --cleanup` previews removal.
**Authorization:** This deployment and push were explicitly requested by Kushagra in the active chat, including the choice that overrides D6 for this implementation. This entry is Proposed because agents do not change hub decisions to Accepted; a human can record formal team acceptance separately. The implementation is not an inference of team consensus.
**Affects:** frontend, backend/app/main.py, README.md, default run instructions, demo accounts and shared board, AWS resources. No live-money trading, historical experiment change, or additional financial data source is introduced.

### D8 · Accepted · 12:55 · Aaron (PRD owner, from the 11:24 team brainstorm)
**Decision:** `hub/PRD.md` v0.1 is the product direction: a research, strategy, blind backtest gate, and execution pipeline that trades for six client mandates in three risk bands, watched by a moderator with an emergency stop, for a wealth management analyst. On `main`, the hosted canvas from D7 is the runtime and The Desk modules from D6 become the canvas agents' tools. Feature freeze and demo prep start at 3:00 PM.
**Why:** It turns the brainstorm into one plan, and it ends the back-and-forth between D6 and D7 by keeping both: D7's hosted runtime and D6's working pipeline.
**Affects:** every lane. Answers Q1, Q2, Q3, Q5, Q6, Q8, and Q9; Q4 and Q7 become PRD P1 items; Q10 goes to lane 5. Chaithu's planned next-phase PRD (analysis variables, statistical significance) is folded into PRD sections 5 to 7 so there is only one PRD.

### D9 · Accepted · 12:55 · Aaron
**Decision:** Every coding agent follows `hub/BUILDING.md`: run `scripts/hub-sync.sh` before each slice of work, at least every 15 minutes during long tasks, and before every push; claim work over 20 minutes in your status file first; put new work in new files; regenerate lockfiles instead of hand-merging them.
**Why:** Six people's agents push to `main` at once, and a 40-minute task built on a stale `main` lands as conflicts or as code that calls something that changed.
**Affects:** every session in every tool.


### D10 · Proposed · Kushagra, direct product instruction recorded by Codex
**Instruction:** Add a fund creation home page, fund management dashboard, detailed but demo-friendly mandate setup, and one overview plus agent canvas per fund. Keep existing functionality.
**Implementation scope:** Lane 5 adds fund metadata and scoped runtime storage in new fund modules, reuses the current canvas and login, and preserves the existing board as the first fund. Each fund has one shared agent filesystem; funds do not read each other's files or delegate across fund boundaries. Financial metrics come from recorded portfolio state or starting cash, not invented performance. No new trading execution is introduced.
**Affects:** new fund routes and UI, minimal canvas/runtime routing/context edits. This follows the direct user instruction while keeping the PRD's pipeline integrations available to other lanes.
### D11 · Proposed · 12:41 · Kushagra, direct instruction recorded by Codex
**Decision:** Expose existing price/OHLCV, SEC fundamentals, FRED macro, curated events and optional GDELT tone to canvas agents through cutoff-aware tools, plus live-only Exa web context search for the news and social research approved in D8.
**Why:** Kushagra explicitly requested broader data access after reviewing the current file-only canvas tools; D8 already authorizes the Desk bridge and live web research.
**Affects:** Lane 1 worker tool registry and private research router, Lane 5 container packaging. No experiment definition, financial schema, new paid infrastructure, or trading changes. Curated events remain labeled unverified, macro availability is approximate, and live context is excluded from historical tool sessions.

### D12 · Proposed · Kushagra, direct instruction recorded by Codex
**Instruction:** Reuse Dexter with dedicated orchestrator, research, adversarial-review, quant/strategy, blind backtesting and Alpaca paper-execution roles, restricting tools by role. Start with one orchestrator; researchers and strategy developers can create adversarial reviewers.
**Implementation scope:** Backend-enforced role capabilities and delegation rules, persistent role identity, a backtester with no web/file/delegation access and only a frozen numeric strategy, and an executor with live context and paper-only order access. Execution requires a backend-recorded passing test, a human trading mandate and emergency-stop checks. Existing historical engine and snapshots remain the evaluation method; no historical Alpaca ingestion or new experiment window is introduced. Crosses Lane 1 runtime/worker and Lane 4 integration files at Kushagra's request under D8. No new billed infrastructure.
**Affects:** Role registry, canvas Agent metadata, internal worker routes and new strategy/evaluation/paper-order adapters. Raises the roster capacity to accommodate the requested specialists while retaining four active workers. This records direct authorization; formal acceptance remains a human action.

### D13 · Proposed · Kushagra, direct correction recorded by Codex
**Instruction:** Undo the extra research layer and mode locking from D11/e1436ea; enable Dexter's existing search and finance tools directly in the canvas.
**Implementation:** Remove custom research modules/routes/tests/docs and their Docker data/pandas additions. Register upstream `get_financials`, `get_market_data`, `read_filings`, `stock_screener`, `web_fetch`, and configured Exa/X search in the existing worker adapter. Keep canvas file and delegation tools. No replacement data layer or mode locks.
**Affects:** Lane 1 worker registry and removal of the private research router, Lane 5 container packaging. D11's implementation is superseded by this explicit user correction. The separately requested role work should restrict these native tools by role; it must not depend on the removed research router. No deploy or new billed infrastructure.

### D14 · Proposed · Kushagra, direct documentation instruction recorded by Codex
**Instruction:** Update the Markdown files to match the native Dexter tools and removal of the extra research layer and mode locks.
**Implementation:** Correct README setup/tool documentation, AGENTS verified facts, and PRD descriptions of shipped live tools versus the planned historical pipeline. Preserve prior decision entries as history, including D11 and its reversal in D13. Provider checks used mocked responses; AWS deployment of the tool update remains unverified.
**Affects:** Documentation only, including Lane 1 integration descriptions in the PRD. No runtime, rule, experiment, or deployment changes.


### D15 · Proposed · Kushagra, direct documentation and coordination correction
**Instruction:** Keep the product direction, remove bloated or incorrect implementation context, include features already built, and make reuse of existing Dexter tools the default before adding equivalent tools. Send the corrections to breath of data, different agents, and kinda mina chat.
**Implementation:** Shorten AGENTS/PRD/BUILDING; bump the rules marker to Hub v3 for the reuse-first rule. Record existing login, collaboration, persistent shared files, native tools and AWS hosting, the newly merged fund dashboard, and separate deployed/locally-verified/in-flight states. Correct the stale baseline status and snapshot provenance language. D13 already records the native-tool correction; this pass changes documentation only and preserves the decision log.
**Affects:** Cross-lane documentation and integration guidance; no runtime, provider, experiment, infrastructure, or live-deployment changes. The human explicitly authorized these documentation edits.
