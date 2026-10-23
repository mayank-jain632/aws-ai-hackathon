# Kushagra · Lane 5: AWS platform, fund dashboard, and canvas

Updated 2026-10-23 by Codex

**Shipped**
- One-container canvas hosted at https://dgvmahl7u2clq.cloudfront.net on a dedicated EC2 instance, with CloudFront HTTPS, encrypted EBS storage, ECR image, Secrets Manager environment, IAM Bedrock access, and Systems Manager management.
- Demo accounts for kush@example.com, mayank@example.com, and gerson@example.com. Passwords remain outside Git in the deployer's ignored `.local/hosting/demo-accounts.json`.
- Shared agent tree, chats with author attribution, files, synchronized canvas positions, and live connection count. Selection, pan, zoom, and branch collapse remain local to each viewer.
- Verified real Bedrock delegation and file tools, cross-account board synchronization, origin/session/file-access boundaries, and state persistence through container restart. Build, frontend/Python lint, and all six existing backend tests pass.
- Deployment/update script and scoped cleanup preview in `scripts/hosting.py`; no workshop desktops or existing AgentCore sample modified.

**In flight**
- Directly requested by Kushagra: fund home/dashboard, short detailed mandate setup, per-fund overview, and an existing agent canvas per fund. Working in managed worktree fund-dashboard.
- New files in `frontend/src/funds/`, `backend/app/funds.py`, and `backend/app/routes/funds.py`. Preserve existing board as the first fund, then keep each fund's agents, files, layout, and discussions separate; all agents inside one fund still share its filesystem.
- Cross-lane integration: minimal main.py router/lifecycle lookup edits and a worker prompt context line are required to scope private delegation to the owning fund. No trading execution, strategy gate, or shared pipeline schema changes.
- User-requested data breadth: adding cutoff-aware cached data tools and live Exa context search. Cross-lane work touches Lane 1 tool registration and adds a private research router; no experiment or shared financial schema changes. Work is isolated on `codex/agent-data-tools`.

**Blocked, or need from someone**
- Finance/search API keys are available to hosted workers, but the existing stripped-down registry still exposes only file and delegation tools. No trading functionality has been added by this deployment.
- Agent-loop inspection by Codex on 2026-10-23: `create_agent` and `message_agent` wait for the child's result; waiting parents count toward the four active runs, so recursive delegation can exhaust capacity before reaching the six-agent roster cap. Lane 1 should account for this when orchestrating phases.
- Dexter's eight-iteration exhaustion emits `done`; the Python adapter records "Run completed" and returns to idle even when the answer says the task was not completed. This is a status-reporting gap for pipeline consumers. Inspection only; no runtime code changed or Bedrock calls made.

**Files I am working in right now**
- `frontend/src/App.tsx`, `frontend/src/board/Canvas.tsx`, `frontend/src/types.ts`
- `backend/app/main.py`, `backend/app/agent.py`, `backend/app/access.py`
- `scripts/hosting.py`, `README.md`, current-state facts in `AGENTS.md`, D7 in `hub/DECISIONS.md`, `hub/status/kushagra.md`
