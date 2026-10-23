# AWS hackathon

A local agent canvas using React/Vite, FastAPI, and Dexter's actual agent loop. Agents form a recursive tree: each agent can create and manage its own subagents. All workers run in one Docker sandbox and share the same workspace and filesystem. Model calls use Amazon Bedrock.

## Set up and run

Install Docker Desktop, Node.js 22.12 or newer, and npm. Start Docker Desktop, then run from the project root:

```sh
test -f .env || cp .env.example .env
test -f .env.local || touch .env.local
npm run dev
```

This builds one image and starts one container containing the production frontend, FastAPI backend, and all Dexter workers. No separate frontend or backend process is needed. The first build downloads dependencies; later starts reuse cached layers. Source changes require rebuilding with the same command.

Configure the workshop credentials below before starting. Open http://127.0.0.1:5173. Click an agent to chat or inspect its activity and shared files. Try:

> Create a researcher named Scout. Ask Scout to create a writer agent that writes a short introduction in hello.txt, reads it back, and reports the result.

New subagents appear beneath their parent. Collapse or expand a branch using its subagent count. Drag cards to arrange them, scroll to zoom, or use **Arrange tree** to restore the automatic layout. **Stop** cancels the selected agent and all its descendants.

The initial version supports six agents and four active runs. `create_agent`, `list_agents`, and `message_agent` let agents delegate and follow up with their descendants. Shell commands, web research, and financial-data APIs are not enabled yet.

## Hosted AWS demo

The hosted version runs the same single container on a dedicated EC2 instance. CloudFront provides HTTPS and forwards live API/event traffic without caching it. An encrypted EBS disk stores agent conversations, files, and shared canvas positions across container restarts and deployments. ECR stores the image, Secrets Manager stores API keys and demo credentials, and an IAM instance role grants Bedrock access. Systems Manager manages the host without an open SSH port.

The demo accounts are `kush@example.com`, `mayank@example.com`, and `gerson@example.com`. Passwords are generated per account and saved locally in ignored `.local/hosting/demo-accounts.json`. All accounts join one shared board; chats show who sent each message. Agent activity, files, dragged positions, and connected viewer counts update across browsers. Pan, zoom, selection, and collapsed branches stay personal.

Build and deploy or update from this laptop:

```sh
docker build --platform linux/arm64 -f backend/Dockerfile -t aws-hackathon-sandbox:hosted .
./workshop-run uv run python scripts/hosting.py
```

The script prints the HTTPS URL and records only this deployment's resources in `.local/hosting/resources.json`. It copies configured API secrets from `.env` to Secrets Manager, never into the image. Hosted workers obtain renewable credentials from their instance role. API key placeholders alone do not enable additional Dexter tools.

This is a shared hackathon demo, with a single application process and no separate customer tenants. The workshop account and its resources remain subject to the event's lifetime. The hosted board starts independently of your laptop's agent history. Back up `/opt/agent-canvas/state` before removing the host; terminating it deletes that disk.

Preview cleanup:

```sh
./workshop-run uv run python scripts/hosting.py --cleanup
```

Add `--apply` to remove the app. CloudFront disabling and instance termination are asynchronous; rerun the same cleanup command when prompted until it completes. This removes the dedicated instance, distribution, image repository, security group, and IAM role, and schedules the secret for deletion with seven days of recovery. The existing workshop desktops and earlier AgentCore sample are separate resources.

## Shared workspace

Every agent reads and writes `.local/workspace/` on your laptop, mounted as `/app/.local/workspace` in Docker. Changes are visible to all agents immediately. Coordinate edits when working on the same file.

Conversations and activity remain separate. Dexter's history is in `.local/agent/`; created agents' histories are under `.local/agents/<id>/`. The roster is in `.local/agents.json`. All of `.local/` is excluded from Git and survives container restarts. The shared canvas layout is stored in `.local/layout.json`.

The sandbox uses a non-root user, a read-only application filesystem, resource limits, and only a localhost API port. Application code and the built frontend are inside the image. It mounts only this project's local state, environment settings, and the two dedicated workshop credential files. It does not mount your home directory or Docker socket. Network access remains available for Bedrock.

## Bedrock credentials

Use temporary credentials supplied by Workshop Studio. These dedicated files are already configured on this laptop and are mounted read-only in the sandbox:

```ini
# ~/.aws/aws-hackathon-2026.credentials
[aws-hackathon-2026]
aws_access_key_id = YOUR_TEMPORARY_ACCESS_KEY
aws_secret_access_key = YOUR_TEMPORARY_SECRET
aws_session_token = YOUR_TEMPORARY_SESSION_TOKEN
```

```ini
# ~/.aws/aws-hackathon-2026.config
[profile aws-hackathon-2026]
region = us-east-1
output = json
```

Keep both files private with `chmod 600`. Refresh them through Workshop Studio when the session expires. The Bedrock model is set in code to `us.openai.gpt-5.6-luna`. `.env` contains optional `AWS_REGION` and blank credentials for Dexter’s finance, search, and model providers; `.env.example` is the shared template. No account ID is required by the app. Adding a key does not enable a tool: this stripped-down adapter currently exposes shared file tools and agent delegation.

Credentials stay in the backend. Model requests incur normal Bedrock charges. Running this local version creates no new AgentCore resources.

## Code and checks

- `frontend/src/board/`: recursive tree layout and SVG canvas adapted from the sibling takehome project.
- `frontend/src/App.tsx`: selected agent's chat, activity, and shared files.
- `backend/app/`: FastAPI, worker lifecycle, and parent–child ownership.
- `backend/worker/`: pinned Dexter source setup and Bedrock/tool adapters.
- `backend/Dockerfile` and `compose.yaml`: shared local sandbox.
- `backend/agent.py`: earlier AgentCore sample, separate from this local app.

Dexter source is pinned to `534f6be455523c5926eba72bdaf4f914555be5c9` from https://github.com/virattt/dexter, whose README identifies it as MIT-licensed. The image build downloads that source into `/app/vendor/dexter`. The upstream agent loop is unchanged; the adapter adds Bedrock, agent tools, and a shared file workspace. The canvas reuses the takehome's SVG gesture approach, design tokens, and Geist font.

For optional host-side code checks, install Node dependencies with `npm ci --ignore-scripts --no-audit --no-fund`, then use Python 3.12 and uv:

```sh
uv sync --locked
npm run check:python
npm run lint
npm run build
```

## Stop and clean up

```sh
npm run stop
```

This removes only the project's sandbox container and network. Shared files and conversations stay in `.local/`. To also remove the project's image, run `docker compose down --rmi local`. Move `.local/workspace/`, `.local/agent/`, `.local/agents/`, and `.local/agents.json` to Trash if you want to reset the board.

The earlier cloud sample runtime still exists. Its inventory is in ignored `backend/resources.json`. Preview its cleanup, then add `--apply` when finished:

```sh
./workshop-run uv run python scripts/cleanup_cloud.py
./workshop-run uv run python scripts/cleanup_cloud.py --apply
```

After stopping Docker and cleaning up the cloud sample, preview local dependency and credential cleanup:

```sh
python3 scripts/cleanup.py
python3 scripts/cleanup.py --apply
```

That command keeps agent-created files and conversations. Shared system tools and other AWS profiles are left alone.
