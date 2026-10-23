# Multi-signal portfolio experiment — Track 3, Financial Portfolio Management

Five analyst agents (technical, fundamentals, macro, sentiment, geopolitics) each write a
dated memo from data available on or before a chosen cutoff. A portfolio-manager agent
reconciles them into target weights with a rationale and a "changes my mind" trigger per
position. The portfolio is then backtested from the cutoff forward against equal weight
and SPY. The result is a single report page: equity curve and metrics against the baseline, the
allocation with the PM's rationale, and each analyst memo with its cited sources.
`PLAN.md` records the original build plan; the next phase is defined by a PRD. Team
rules and decisions are in `AGENTS.md` and `hub/`. The Docker agent canvas is on branch
`agent-canvas` (`npm run dev:canvas` on `main` still builds its sandbox).

**This is a historical experiment, not financial advice.**

## Experiment definition (reproducibility)

| Item | Value |
|---|---|
| Universe (10) | AAPL, MSFT, NVDA, AMZN, GOOGL, JPM, XOM, UNH, PG, CAT |
| Reference | SPY |
| Cutoff | chosen on the slider, 2022-01-01 to 2024-06-01 in monthly steps; default 2023-01-01 |
| Evaluation window | cutoff to 2025-06-30 |
| Baseline | equal weight of the universe (SPY shown as a second line) |
| Rebalancing | monthly, back to the PM's target weights; long only; weights sum to 1 |
| Costs | none |
| Returns | price return from split-adjusted closes (no dividends) |
| Sharpe | daily returns annualised, risk-free = latest FEDFUNDS published by the cutoff |
| Look-ahead | every loader in `backend/app/data.py` takes `cutoff` and drops rows not public by then (prices by date, FRED by publication date, SEC by filing date, GDELT by event date) before any agent reads them; every cited source carries its date and the API asserts it is on or before the cutoff |
| Data | committed snapshots under `data/`, downloaded 2026-10-23; see `data/README.md` for sources and ranges |
| Model | `us.openai.gpt-5.6-luna` on Amazon Bedrock via the Converse API, one call per analyst plus one for the PM |
| Cache | responses cached under `backend/.cache/` keyed by cutoff, so re-running a cutoff is deterministic; pass `?refresh=true` to `/api/run` to recompute |

## Run it

Backend, through the workshop credential wrapper (see "Connect to AWS" below):

```sh
./workshop-run uv run fastapi dev --host 127.0.0.1 --port 8000
```

Without AWS access, `MOCK_AGENTS=1` serves fixture memos and weights with the real backtest.

Frontend:

```sh
npm run dev:frontend
```

Tests and lint:

```sh
uv run pytest backend/tests
```

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
