# AWS hackathon

Team 4's starter uses React, TypeScript, and Vite for the frontend, FastAPI for the backend, and Amazon Bedrock with AgentCore for the agent.

## Set up

Install Python 3.12, uv, Node.js 22.12 or newer, npm, and AWS CLI v2. From the project root:

```sh
uv sync --locked
npm ci --ignore-scripts --no-audit --no-fund
```

Start the backend:

```sh
npm run dev:backend
```

Start the frontend in another terminal:

```sh
npm run dev:frontend
```

Open http://127.0.0.1:5173 and click **Check backend connection**. FastAPI's API documentation is at http://127.0.0.1:8000/docs. Both servers run locally; starting them does not call AWS.

## Folders

- `frontend/src/`: React interface. Vite forwards `/api` requests to FastAPI.
- `backend/app/`: FastAPI application, starting with `/api/health`.
- `backend/agent.py`: separate AgentCore starter that accepts a prompt and calls Bedrock.
- `scripts/`: local and AWS cleanup tools.
- `.vscode/`: project interpreter and debugging settings.

Python dependencies are in `pyproject.toml` and `uv.lock`. Node dependencies use npm workspaces and `package-lock.json`. `backend/requirements.txt` contains the separate agent deployment dependencies. Keep AWS calls and credentials on the backend, never in frontend code.

## Connect to AWS

Join the event at https://catalog.workshops.aws/join and use the temporary account and credentials supplied by Workshop Studio. A personal AWS account is not required. Confirm the account matches your teammates and use `us-east-1`.

The local wrapper uses these dedicated files instead of the default AWS configuration:

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

Keep both files private with `chmod 600`. In the ignored root `.env.local`, set:

```sh
export EXPECTED_AWS_ACCOUNT=YOUR_WORKSHOP_ACCOUNT_ID
```

Verify access from the project root:

```sh
./workshop-run aws sts get-caller-identity
./workshop-run uv run python backend/infer.py
```

The inference check makes one small Bedrock request. Refresh expired credentials through Workshop Studio. Existing local credentials and `.env.local` are already configured; replace them only when needed.

## AgentCore starter

The official starter is from https://atx.rahman.dev/hackathon-kit.zip. Direct Bedrock inference and the deployed runtime both returned `OK`. The model is `us.openai.gpt-5.6-luna`; its request must omit `temperature`.

The existing deployment's role, private encrypted bucket, and runtime are recorded in ignored `backend/resources.json`. Local deployment configuration is in `backend/.bedrock_agentcore.yaml`. Do not rerun role creation for this existing deployment.

Invoke it from the project root:

```sh
cd backend
../workshop-run ../.venv/bin/agentcore invoke '{"prompt":"Reply with OK."}' --agent team4_baseline_kushagra
```

This deployment uses the official kit's older Python CLI, which prints a deprecation notice. `npm run agentcore -- --help` selects the newer Node CLI; its commands and configuration differ. Runtime use and model requests can incur charges.

## Checks

```sh
npm run lint
npm run build
npm run check:python
```

## Cleanup

Preview cloud cleanup, then add `--apply` when finished with the runtime:

```sh
./workshop-run uv run python scripts/cleanup_cloud.py
./workshop-run uv run python scripts/cleanup_cloud.py --apply
```

This checks the account and ownership tags, then removes only the recorded starter resources. Organizer infrastructure is left alone.

After cloud cleanup, close project terminals and clean local dependencies and temporary credentials:

```sh
python3 scripts/cleanup.py
python3 scripts/cleanup.py --apply
```

The first command previews changes. Local cleanup moves generated files to macOS Trash and removes only this setup's dedicated credentials and `.env.local`. Source and lockfiles stay available. The `AWS Hackathon` editor profile can be removed through VS Code Profiles after switching to Default. Shared system tools, other AWS profiles, and shell startup files are left alone.
