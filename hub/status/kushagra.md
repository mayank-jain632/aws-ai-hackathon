# Kushagra · Lane: agent canvas and AWS hosting

Updated 2026-10-23 by Codex

**Shipped**
- One-container canvas hosted at https://dgvmahl7u2clq.cloudfront.net on a dedicated EC2 instance, with CloudFront HTTPS, encrypted EBS storage, ECR image, Secrets Manager environment, IAM Bedrock access, and Systems Manager management.
- Demo accounts for kush@example.com, mayank@example.com, and gerson@example.com. Passwords remain outside Git in the deployer's ignored `.local/hosting/demo-accounts.json`.
- Shared agent tree, chats with author attribution, files, synchronized canvas positions, and live connection count. Selection, pan, zoom, and branch collapse remain local to each viewer.
- Verified real Bedrock delegation and file tools, cross-account board synchronization, origin/session/file-access boundaries, and state persistence through container restart. Build, frontend/Python lint, and all six existing backend tests pass.
- Deployment/update script and scoped cleanup preview in `scripts/hosting.py`; no workshop desktops or existing AgentCore sample modified.

**In flight**
- Integrating remote history and pushing the hosted canvas to main, explicitly authorized by Kushagra after disclosing D6. D7 records the direct instruction.

**Blocked, or need from someone**
- Finance/search API keys are available to hosted workers, but the existing stripped-down registry still exposes only file and delegation tools. No trading functionality has been added by this deployment.
- Agent-loop inspection by Codex on 2026-10-23: `create_agent` and `message_agent` wait for the child's result; waiting parents count toward the four active runs, so recursive delegation can exhaust capacity before reaching the six-agent roster cap. Lane 1 should account for this when orchestrating phases.
- Dexter's eight-iteration exhaustion emits `done`; the Python adapter records "Run completed" and returns to idle even when the answer says the task was not completed. This is a status-reporting gap for pipeline consumers. Inspection only; no runtime code changed or Bedrock calls made.

**Files I am working in right now**
- `frontend/src/App.tsx`, `frontend/src/board/Canvas.tsx`, `frontend/src/types.ts`
- `backend/app/main.py`, `backend/app/agent.py`, `backend/app/access.py`
- `scripts/hosting.py`, `README.md`, current-state facts in `AGENTS.md`, D7 in `hub/DECISIONS.md`, `hub/status/kushagra.md`
