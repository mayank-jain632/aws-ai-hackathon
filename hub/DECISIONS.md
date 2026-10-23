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

When the team answers one, delete it here and log the answer below as a decision. Lane responsibilities and remaining implementation work are in `hub/PRD.md`; older log entries retain the section numbers from the PRD version they described.

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

### D16 · Proposed · Kushagra, direct data-breadth instruction recorded by Codex
**Instruction:** Enable broad data access, sentiment with the latest Jev decision model through OpenRouter only for that model, native Exa live search, and Apify where useful.
**Implementation scope:** Reuse all upstream Dexter finance tools, Exa and X; add only capabilities absent upstream: Jev sentiment via the OpenRouter Decisions API, current FRED macro, and bounded Apify data collection. OpenRouter's verified latest alias is `~typesafe/jev-latest`, currently Jev 1.14; preserve returned version/probabilities. All existing agents and finance routing remain on Bedrock. No research API layer or mode locks, historical experiment changes, brokerage changes, or new AWS resources.
**Affects:** Lane 3 live-data tools and Lane 1 native registry/allowlist, Lane 5 provider-secret forwarding. Local provider credentials are empty; wiring and mocked checks must not be described as live-provider verification.

### D17 · Proposed · 13:02 · Aaron (logged by Claude Code)
**Decision:** Aaron owns the moderator/watchdog half of PRD lane 4 ("Execution / moderator"); the two execution owners keep the Alpaca adapter and order state. The watchdog adds a deterministic pre-trade gate, claim checks, a firm-wide emergency stop over the existing per-fund desk stop, a background monitor, an LLM second opinion on flagged trades, and a feedback and lessons loop.
**Why:** PRD section 4 items 5 to 7 need someone watching every order and agent claim, and lane 4 had execution owners but no moderator owner.
**Affects:** new files under `backend/app/watchdog/`, `backend/app/routes/watchdog.py` and `backend/tests/test_watchdog_*.py`; one-line hooks in `backend/app/main.py`, `backend/app/paper.py` and `backend/worker/run.ts`. No change to `schema.py`, the desk policy model, or the existing stop semantics (a person still clears a stop).


### D18 · Proposed · Kushagra, direct recursive-role follow-up recorded by Codex
**Instruction:** Agents can spin up other types with their own tools/access, and the orchestrator can use all capabilities; finish the current workflow before configuring Alpaca and other environment values.
**Implementation:** Give orchestrators all registered tools, permit cross-role descendants for non-blind agents, and restrict blind descendants to the same immutable strategy. Preserve backend mandate, review, evaluation, human approval and emergency-stop checks. Queue runs with four active worker slots; suspended parents yield and reacquire capacity safely across siblings, nested calls and cancellation.
**Affects:** Lane 1 runtime, role profiles, authenticated handoff routes and registry; Agent snapshot waiting/queued metadata and environment template. No new panels, providers, accounting model, experiment definition, deployed image or billed infrastructure in this slice. Real Bedrock role/file handoff is verified separately from broker mocks.

### D19 · Proposed · 13:15 · Aaron (logged by Claude Code)
**Decision:** Every paper order passes the watchdog gate `review_order` inside `paper.submit`, and a firm-wide emergency stop (people trip and clear it at `PUT /api/watchdog/halt`; the watchdog can trip it) sits above each fund's desk stop. Watchdog types (`WatchOrder`, `WatchMandate`, `WatchPortfolio`, `Verdict`, `ModeratorEvent`) stay in `backend/app/watchdog/models.py` and are proposed for `schema.py` when Lane 1 adopts shared order and fill shapes.
**Why:** The PRD needs moderator checks before every order; keeping the gate deterministic and outside the model makes a block explainable and impossible for an agent to talk past.
**Affects:** Lane 4 execution (`paper.submit` now raises "Watchdog blocked this order: ..." on a block), Lane 1 (`roles.py` tool lists, `run.ts` registry entry). Risk-band guardrails in `watchdog/rules.py` (top-three concentration 50/65/85%, daily turnover 35/60/100%, one order 10/20/35% of equity, price band 3/5/8%) are operational order-flow limits, not evaluation thresholds; a human can override them per mandate.

### D20 · Proposed · Kushagra, direct model-selection instruction recorded by Codex
**Instruction:** Offer Claude Opus 5.5 or GPT-6.1 Sol for main agents and use Claude Opus 4.6 for backtesters. After the access check, Kushagra selected Sol 6.1 as the default.
**Implementation:** Shared verified Bedrock profile catalog, per-agent persisted model selection, parent inheritance with explicit child override, fixed Opus 4.6 evaluators, and model selector in the existing agent panel. Keep Dexter's loop and all role/mandate/evaluation/order checks. Deployment policy includes the profiles and retains Luna for the existing watchdog second opinion. No automatic fallback.
**Affects:** Runtime/worker, human model route, frontend Agent contract and panel, environment template, deployment IAM. Catalog listing is not inference access: actual participant-role calls explicitly deny both new main choices; real Opus 4.6 evaluation passed. AWS records Opus 4.6's cutoff as May 2025, so this model pin does not remove historical leakage. No hosted rollout, IAM restriction bypass, new infrastructure or experiment change.

### D23 · Proposed · 13:33 · Aaron (logged by Claude Code)
**Decision:** Aaron adds a read-only scores and reasoning view per fund desk, in new files, mounted from the fund overview by one link.
**Why:** The track asks teams to show which sources influenced the portfolio and the agents' reasoning; today that evidence is spread across desk records, mandate, watchdog logs and shared files.
**Affects:** new `backend/app/scores/`, `backend/app/routes/scores.py` (`GET /api/funds/{fund_id}/scores`, one `include_router` line in `main.py`), new `frontend/src/scores/`, and one mount element plus its import in `frontend/src/funds/FundOverview.tsx`. Reads desk, mandate, watchdog, workspace files, and, once merged, `synthesis.json` and `reports/wf/`; writes nothing. Each ring shows its raw metric, formula and source, or "not produced yet" with the owning lane.

### D24 · Proposed · Kushagra, hosted flow and explicit one-dollar paper approval
**Instruction:** Test Sol 6.1 through the hosted EC2 role and complete the agent flow, keeping Opus 4.6 backtesting. The human then approved exactly one $1 AAPL PAPER test order, a $1/one-order cap and restoring its fund stop afterward.
**Implementation/evidence:** Eight real hosted role identities completed the research/challenge/strategy/review/blind-test/executor/moderator handoffs. The frozen numeric integration baseline passed; the policy permission/cap update caused a fresh Opus 4.6 evaluation before recording human strategy approval. Sol's executor submitted once and its moderator restored the stop. Actual Alpaca lookup confirmed filled. Initial pending_new receipts exposed a missing agent capability, so add read-only alpaca_paper_order reconciliation for a recorded fund order, including uncertain outcomes by stable ID, without any POST/retry or gate bypass.
**Affects:** Paper adapter, existing desk router/tool module and executor/moderator profiles; runtime tool contract and verification docs. No new framework, investment claim, performance threshold, account policy mutation by this role task, extra order, infrastructure or financial-data source. Hosted activation and rollout remain coordinated with deployment.

### D21 · Accepted · 12:55 · Mayank (logged by Claude Code)
_Drafted as D15 before `main` took D15 to D20; renumbered on this branch to avoid a collision. Code comments and `data/wf/README.md` written before the renumbering still say "hub D15"; they mean this entry._

**Decision:** Backtests that score the agents use Claude Opus 4.6 (`us.anthropic.claude-opus-4-6-v1`, temperature 0) over a clean window of weekly decisions from Fri 2025-10-03 to Fri 2026-10-16 (55 decisions, equity marked through 2026-10-22), with 8 early decisions as a dev window and the rest as a frozen test window run once. The pipeline is research (the five analysts) then strategy then execution (weekly order policy: market-on-open, limit, skip-if-gapped, stop and target), simulated by a deterministic daily-bar engine with no LLM in the fill logic. Baselines run through the same engine: equal-weight buy-and-hold (primary), SPY, weekly rebalanced equal weight, a no-LLM momentum rule, the mechanical `pm.seed_weights`, and a random-policy distribution. Universe stays the 10 names on `main`.
**Why:** Opus 4.6's documented training cutoff is 2025-08, and a closed-book probe agreed (it recalled Fed-rate, SPY and NVDA monthly facts through Aug 2025 and abstained or erred afterwards), so decisions from Oct 2025 (cutoff plus a buffer month) cannot be explained by memory; the gpt-5.6 runs on 2022-2024 can. This answers Q4 and Q7 and gives PRD section 6 its out-of-sample window.
**Rules:** (1) No mock, fixture or curated-event fallback anywhere in a backtest: an unavailable analyst abstains and is logged. (2) Filings and news are visible strictly before the decision date, prices through it; orders fill no earlier than the next open; when stop and target are both hit in one bar the stop fills first. (3) The model's cutoff and the window go in every run manifest, and the runner refuses earlier dates unless run as an explicitly labelled contaminated control. (4) Leakage audit: masked-ticker run against named run on the clean window, plus the same comparison on a contaminated pre-cutoff window as a positive control, plus future-poison, truncation-invariance and cheat-canary tests. (5) The window needs fresher data than `data/` holds (it ends 2025-06-30), so a new snapshot goes in `data/wf/` from `data/fetch_wf.py`; the existing snapshots and fetchers are untouched. The hand-written `curated_events.csv` is not used in the window; SEC 8-K filings with acceptance timestamps replace it.
**Affects:** new files only: `backend/app/wf/`, `backend/app/agents/strategy.py` and `execution.py`, `data/fetch_wf.py`, `data/wf/`, `backend/tests/wf/`. No edit to `schema.py`, `main.py`, `data.py`, `backtest.py` or the analysts; shared shapes for this work live in `backend/app/wf/schemas.py`. Lane 2 (Chaithu) owns the Phase 3 gate; this is the evaluation engine behind it and the P1 significance and leakage items.

### D22 · Accepted · 13:55 · Mayank (logged by Claude Code)
**Decision:** The `wf` harness is a reproducible, pluggable backtesting system whose purpose is to take whatever the other lanes build and score it with the same leakage controls and the same results format. Research, strategy and execution are plug-in points behind small interfaces: `Decider` (point-in-time context -> target weights, plus optional stops), `ExecutionPolicy` (weights -> orders) and `Evaluator` (frozen weights and dates -> metrics, mirroring the blind backtester's input). The agents already in `wf` (five analysts, strategy, LLM execution policy) are the default implementations; the order planner and backtesting agent that lane 4 and lane 2 are building replace them through adapters without changing the engine, the data layer or the reports. Each run is described by one hashed run spec (model, window, universe, components, costs, seed, data hashes) so a result can be reproduced exactly. Until an advanced executor lands, the baseline execution is deterministic: long-only market orders at the next open with costs, sells before buys, and the D19 watchdog limits modelled as pre-trade gates (blocked orders reported as blocked, never as fills). Every historical result names the model that authored the weights and its training cutoff, and is labelled model-clean only if the first decision is after that cutoff plus a buffer. Only `data/wf/` supports a model-clean result; the `data/` snapshot ends 2025-06-30, inside every candidate model's cutoff.
**Why:** Teammates are still building the executor and a more capable backtesting agent, so what we can own and finish is the evaluation system they plug into. The frozen run (D21) shows what that system produces: Opus 4.6, 47 clean test weeks, -1.3% against +18.8% for equal-weight buy-and-hold, with the 20.1-point gap about 13.8 stock selection, 3.7 cash drag (72% average invested) and 2.6 from the LLM execution policy and stops, and no named-over-masked advantage in the audit. Pinning the blind backtester to Opus 4.6 (D20) does not remove leakage, because the leak-prone agents are the ones that choose weights.
**Affects:** New files only under `backend/app/wf/` (interfaces, adapters, run spec, standard results). Lane 2 (Chaithu, `backend/app/synthesis/` significance and the gate) and Lane 4 (executor and watchdog) get an adapter contract; no code on `main` changes. The existing significance module keeps measuring allocation robustness on frozen weights; the `wf` rolling mode measures the weekly decision process. Needs a human accept or reject before any integration work touches another lane's files.

**Acceptance:** D21 and D22 were accepted by Mayank on 2026-10-23 (~13:45) by explicit instruction in the working chat ("accept d21 and 22"), recorded here by Claude Code. Same instruction: make the backtester itself a canvas agent using this harness, and rerun the execution pipeline through it. Also accepted by Chaithu (lane 2 owner) at 14:35.

### D25 · Proposed · 13:45 · Aaron's lead orchestrator (Claude Code)
**Decision:** Credentials and the demo path. The demo runs on the hosted app (CloudFront URL) through the EC2 instance role `team4-agent-canvas`, and provider keys (Alpaca paper, data APIs) live only in the Secrets Manager secret `team4-agent-canvas-environment`. Nobody's personal Workshop Studio or `aws login` credentials are in the demo path. Kushagra's deployment owner is the only one who changes that instance, role, secret, image, or distribution. A lane that needs new permissions on the hosted role (for example AgentCore Runtime or Memory) writes the exact actions and resource ARNs here, and the deployment owner applies them in `scripts/hosting.py` and redeploys. Coding agents with AWS access (Aaron's Agent Toolkit MCP, Codex, or any other) create only their own resources, named after their owner and tagged `Project=AWS-Hackathon` and `Owner=<name>`, and treat everything else as read-only.
**Why:** The team shares one AWS account and one Alpaca paper account. Personal credentials expire hourly, and participant IAM is denied the Sol 6.1 and Opus 5.5 models the hosted role can use (kushagra.md, D24). The main overlap risk is one person's agent changing a resource another lane depends on.
**Affects:** Lane 5 deployment, Aaron's AgentCore work (`aaron/agentcore`), and every coding agent with AWS access.

### D26 · Proposed · 13:30 · Chaithu (logged by Claude Code)
**Decision:** Add a synthesis layer between the research group and the existing desk gates: a strategy-role tool that turns a bundle of dated memos into a registered frozen strategy, a walk-forward significance report beside the backtest gate, and an executor-role order planner that sizes notional orders in code before `submit_paper_order`.
**Why:** The research, strategy, blind backtest and paper execution roles exist on `main`, but nothing consumed the research group's output automatically, the gate was a single window with no significance measure, and the executor did order arithmetic in prose; judges asked for breadth of inputs and statistically tested backtests.
**Affects:** New files `backend/app/synthesis/`, `backend/app/routes/synthesis.py`, `backend/tests/test_synthesis.py`, `docs/agent-flow.*`. One-line additions in `backend/app/roles.py` (two tool names), `backend/worker/desk-tools.ts` (two bridge tools) and `backend/app/main.py` (router). No change to desk gates, paper adapter, policy model, experiment definition or deployment; the significance report never replaces the gate.
