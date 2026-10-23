# Kushagra · Lane: agent canvas and AWS hosting

Updated 2026-10-23 by Codex

**Shipped**
- One-container canvas hosted at https://dgvmahl7u2clq.cloudfront.net on a dedicated EC2 instance, with CloudFront HTTPS, encrypted EBS storage, ECR image, Secrets Manager environment, IAM Bedrock access, and Systems Manager management.
- Demo accounts for kush@example.com, mayank@example.com, and gerson@example.com. Passwords remain outside Git in the deployer's ignored `.local/hosting/demo-accounts.json`.
- Shared agent tree, chats with author attribution, files, synchronized canvas positions, and live connection count. Selection, pan, zoom, and branch collapse remain local to each viewer.
- Verified real Bedrock delegation and file tools, cross-account board synchronization, origin/session/file-access boundaries, and state persistence through container restart. Build, frontend/Python lint, and all six existing backend tests pass.
- Deployment/update script and scoped cleanup preview in `scripts/hosting.py`; no workshop desktops or existing AgentCore sample modified.

**In flight**
- Commit/push destination awaiting Kushagra's choice after discovering main's accepted D6 report-page decision. The hosted app is already working independently of that Git decision.

**Blocked, or need from someone**
- Confirm whether to preserve the report on main and push this work to agent-canvas, or explicitly replace main with the hosted canvas.
- Finance/search API keys are available to hosted workers, but the existing stripped-down registry still exposes only file and delegation tools. No trading functionality has been added by this deployment.

**Files I am working in right now**
- `frontend/src/App.tsx`, `frontend/src/board/Canvas.tsx`, `frontend/src/types.ts`
- `backend/app/main.py`, `backend/app/agent.py`, `backend/app/access.py`
- `scripts/hosting.py`, `README.md`, `hub/status/kushagra.md`
