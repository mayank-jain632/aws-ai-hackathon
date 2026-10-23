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

When the team answers one, delete it here and log the answer below as a decision.

- **Q1. How does the agent market work?** D4 says agents trade a market when the user allows it. Open: is the market a simulation replayed over historical prices or a live paper market, what does the user's permission look like, and what data from the trades and from human-agent conversations feeds back into the system?
- **Q2. What does a human do besides chat with agents?** Grant or revoke trading permission, set a mandate or risk limit, post their own view, override a position?
- **Q3. What is the one demo moment?** `PLAN.md` says the cutoff drag. The canvas suggests a live agent tree. Pick one to rehearse.
- **Q4. How do we answer "isn't the model just remembering that NVDA went up?"** The cutoff filter protects the data, not the model. A masked-ticker run against a named-ticker run is one answer.
- **Q5. Which AWS AI services do we show beyond Bedrock Converse?** Candidates: AgentCore Runtime, Gateway, Memory, Observability; Comprehend; Chronos. Judges score this directly.
- **Q6. Which new data inputs come first?** Judges said breadth of data inputs is the goal. Candidates with setup times are in `docs/research/finance-track-brief.md`.
- **Q7. One cutoff or all of them?** Report a single date, or run every cutoff and report how often we beat equal weight.
- **Q8. Lanes for six people.** Who owns the canvas, the data inputs, the agent tools, the market, evaluation, and the slides and pitch?
- **Q9. Feature freeze time.** Suggested 3:30 PM, leaving 30 minutes to rehearse.
- **Q10. Demo from AgentCore Runtime or from the local Docker sandbox?** Credentials expire hourly, so a cached local run is the safer fallback either way.
- **Q11. One model or several?** Every call uses `gpt-5.6-luna` today. Mixing model families across agents shows more of Bedrock.

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
