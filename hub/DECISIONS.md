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

### D25 · Proposed · 13:45 · Aaron's lead orchestrator (Claude Code)
**Decision:** Credentials and the demo path. The demo runs on the hosted app (CloudFront URL) through the EC2 instance role `team4-agent-canvas`, and provider keys (Alpaca paper, data APIs) live only in the Secrets Manager secret `team4-agent-canvas-environment`. Nobody's personal Workshop Studio or `aws login` credentials are in the demo path. Kushagra's deployment owner is the only one who changes that instance, role, secret, image, or distribution. A lane that needs new permissions on the hosted role (for example AgentCore Runtime or Memory) writes the exact actions and resource ARNs here, and the deployment owner applies them in `scripts/hosting.py` and redeploys. Coding agents with AWS access (Aaron's Agent Toolkit MCP, Codex, or any other) create only their own resources, named after their owner and tagged `Project=AWS-Hackathon` and `Owner=<name>`, and treat everything else as read-only.
**Why:** The team shares one AWS account and one Alpaca paper account. Personal credentials expire hourly, and participant IAM is denied the Sol 6.1 and Opus 5.5 models the hosted role can use (kushagra.md, D24). The main overlap risk is one person's agent changing a resource another lane depends on.
**Affects:** Lane 5 deployment, Aaron's AgentCore work (`aaron/agentcore`), and every coding agent with AWS access.

### Proposed · Kushagra, hosted fund live/historical clarification recorded by Codex
**Human instruction:** Run a fund on AWS through real research, sentiment, strategy and backtesting; use separate live proposal and historical baseline, keep existing verification thresholds and trading disabled. Kushagra clarified that historical data is for backtesting and the proposal is live.
**Application:** Verification fund `ac8b623ccc0a4acb` used current native sources for live memos/proposal only. A distinct fixed 10%-each retrospective baseline used the existing 2024-06-01 through 2025-06-30 window and unchanged prior verification policy, then independent review and a blind Opus 4.6 evaluation. No historical availability, performance or live-compliance claim was inferred from current sources. The genuine FAIL gate was retained.
**Affects:** Demo/verification documentation and persisted verification-fund artifacts only. No new experiment engine, source, policy default, production schema or trading permission. Optional expanded live reassessment was stopped for the coordinated rollout; its completed research is preserved separately from the initial reviewed proposal.

### D26 · Proposed · 14:00 · Aaron (logged by Claude Code)
**Decision:** Per D25, Kushagra's deployment owner adds one watchdog statement set to the hosted role `team4-agent-canvas` in `scripts/hosting.py`: `bedrock:ApplyGuardrail` on the `aaron-watchdog` guardrail ARN; `bedrock:ListGuardrails` and `bedrock:GetGuardrail` on `*`; `bedrock-agentcore:CreateEvent`, `bedrock-agentcore:ListEvents` and `bedrock-agentcore:RetrieveMemoryRecords` on the `aaron_watchdog_lessons` memory ARN; `bedrock-agentcore:ListMemories` on `*`; `cloudwatch:PutMetricData` on `*` with condition `cloudwatch:namespace = Team4/Watchdog`; `events:PutEvents` on `arn:aws:events:us-east-1:<account>:event-bus/default`. After Aaron's `--apply`, `./workshop-run uv run python scripts/watchdog_aws.py --policy` prints the statement with exact ARNs.
**Why:** The watchdog's Guardrail scans, lessons memory, metrics and audit events run inside the hosted app, and D25 reserves hosted-role changes for the deployment owner. Aaron's script creates only his own resources (Owner=aaron) and never edits the role.
**Affects:** Lane 5 `scripts/hosting.py` plus one redeploy; Lane 4 watchdog. Without it the hosted watchdog keeps working and logs AccessDenied warnings for the AWS calls; no verdict depends on AWS.

### D27 · Proposed · 13:40 · Sushruth (logged by Claude Code)
**Decision:** Add a firm-level exposure and capacity roll-up across every fund in new files (`backend/app/firm.py`, `backend/app/routes/firm.py`), reporting per-symbol, per-sector and per-risk-band exposure, cross-fund overlap, and the capacity ratio between the sum of active fund capital and the single shared Alpaca paper account. Numbered D27 after two renumbers: D23 and D26 were taken by Aaron's scores view and hosted-role permissions while this was in flight, and `mayank/wf-walkforward` already proposes D21 and D22.
**Why:** Every existing check is scoped to one fund, so two things are invisible: several funds claiming $100,000 each and approving books sized to it against one shared $100,000 paper account, where each fund's cash check passes because they all read the same balance; and every client holding the same name inside their own limits, so one issuer's drawdown reaches the whole book at once. Note the arithmetic the module documents: if each fund holds a name at 8% of its own capital the firm total is also 8% of combined capital, not 48%, so the signal is shared ownership and the size of the firm total, not an amplified percentage.
**Affects:** New Lane 4b files plus one `app.include_router` line in `backend/app/main.py`. Reads each fund's mandate and its own `desk.json` read-only and reuses the risk bands in `watchdog/models.py`; does not change `watchdog/`, `paper.py`, the order gate, `schema.py`, the desk policy model or any stop semantics. Exposure is derived only from recorded orders and approved strategies, never from assumed or simulated holdings, and the sector classification is a hand-maintained map for the snapshot universe with an explicit `Unclassified` bucket, not sourced market data. No firm-level threshold is invented: every limit used is the shared account's balance or a limit a person already set in a mandate. Introduces no orders, providers or billed infrastructure.

### D28 · Proposed · 13:49 · Aaron (logged by Claude Code)
**Decision:** Aaron owns the scoped AgentCore Runtime and Observability integration from Lane 5's list: the watchdog second opinion runs as AgentCore Runtime agent `aaron_watchdog_opinion`, the backend invokes it behind `AGENTCORE_OPINION_ARN` with the current local Bedrock path as the fallback, and its invocations are traced in CloudWatch. Memory is not rebuilt: the runtime receives the fund's lessons recalled from D26's `aaron_watchdog_lessons`. The canvas stays on EC2.
**Why:** PRD requirement 8 asks for AgentCore where it serves a defined requirement, with a real invocation and trace; the second opinion is already shipped (D17), self-contained and off the order path, so hosting it cannot break the demo.
**Billed resources:** in Aaron's own participant account `556200168424`, us-east-1, tagged `Project=AWS-Hackathon`, `Owner=aaron`, `Team=4`: IAM execution role `aaron-agentcore-watchdog-runtime` (Luna inference, logs, X-Ray only), S3 code bucket `aaron-agentcore-watchdog-556200168424`, Runtime `aaron_watchdog_opinion` (gpt-5.6-luna, no temperature) and its CloudWatch log group, plus CloudWatch Transaction Search turned on in that account for spans. Inventory goes to ignored `.local/agentcore/resources.json`; `scripts/agentcore_cleanup.py` previews and, with `--apply`, removes exactly those after checking tags.
**Account note:** `aws login` for Aaron reaches `556200168424`, which holds none of the hosting resources (no `team4-agent-canvas`, its secret or the earlier sample runtime). The hosted role therefore cannot call this runtime, and the same applies to D26's resources if they are applied with the same login. Hosted adoption after the freeze means rerunning `scripts/agentcore_deploy.py` in the hosting account and granting `team4-agent-canvas` `bedrock-agentcore:InvokeAgentRuntime` on the runtime ARN.
**Affects:** new `backend/app/agentcore/`, `backend/app/routes/agentcore.py` (one `include_router` line in `main.py`), one hook in `watchdog/opinion.py`, new deploy and cleanup scripts. No schema, role, registry or order-path change; no change to the hosting account.
