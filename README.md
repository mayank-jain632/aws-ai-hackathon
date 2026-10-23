# AWS hackathon

A fund management workspace using React/Vite, FastAPI, and Dexter's actual agent loop. Create a fund with a mandate, review its dashboard, and work with its own recursive agent canvas. Agents within a fund share files and keep separate conversations. Everything runs in one Docker container, with Amazon Bedrock model calls.

## Set up and run

Install Docker Desktop, Node.js 22.12 or newer, and npm. Start Docker Desktop, then run from the project root:

```sh
test -f .env || cp .env.example .env
test -f .env.local || touch .env.local
npm run dev
```

This builds one image and starts one container containing the production frontend, FastAPI backend, and all Dexter workers. No separate frontend or backend process is needed. The first build downloads dependencies; later starts reuse cached layers. Source changes require rebuilding with the same command.

Configure the workshop credentials below before starting. Open http://127.0.0.1:5173. The fund dashboard preserves your existing board as Team 4 fund. Create another fund in three steps: goals and capital, risk/universe limits, then research mode and permissions. Presets fill sensible defaults; advanced fields remain editable. Each fund has an overview, pause/archive controls, and its own agent canvas. Starting capital is paper cash; no returns, trades, or valuations are invented. Use Start fund planning to create a real Bedrock-authored brief and checklist, or open the canvas and try:

> Create a researcher named Scout. Ask Scout to create a writer agent that writes a short introduction in hello.txt, reads it back, and reports the result.

New subagents appear beneath their parent. Collapse or expand a branch using its subagent count. Drag cards to arrange them, scroll to zoom, or use **Arrange tree** to restore the automatic layout. **Stop** cancels the selected agent and all its descendants.

The role-aware canvas supports sixteen agents and four active runs. `create_agent`, `list_agents`, and `message_agent` let agents delegate and follow up with their descendants. The canvas also exposes Dexter's existing finance, search, and URL-fetch tools, described below. Shell commands remain disabled. Paper submissions are available to orchestrators/executors under backend approval checks; read-only order reconciliation is also available to moderators; see `docs/agent-roles.md`.

## Agent tools

The canvas uses Dexter's existing tool implementations directly alongside its shared file and agent-delegation tools. Before adding an equivalent integration, inspect the pinned upstream registry and enable its existing implementation. Keep custom code for missing app behavior such as ownership, roles, mandates, and historical filtering; do not rebuild Exa or the financial provider clients.

| Tools | Use | Configuration |
|---|---|---|
| `get_financials` | Company statements, metrics, ratios, earnings, and segments | `FINANCIAL_DATASETS_API_KEY` |
| `get_market_data` | Stock/crypto prices, news, and insider/ownership data | `FINANCIAL_DATASETS_API_KEY` |
| `read_filings` | SEC filing content | `FINANCIAL_DATASETS_API_KEY` |
| `stock_screener` | Find stocks by financial criteria | `FINANCIAL_DATASETS_API_KEY` |
| Native direct finance tools | Statements, ratios, earnings, segments, price history, ticker lookup, news, insider trades/ownership, institutional holdings/investors, beneficial ownership, and filing sections | `FINANCIAL_DATASETS_API_KEY` |
| `analyze_sentiment` | Jev sentiment labels, probabilities, confidence and sample score for retrieved excerpts | `OPENROUTER_API_KEY`; only Jev uses OpenRouter |
| `get_macro_series` | Current-vintage FRED observations including rates, inflation, employment, yield curve and volatility | No key |
| `apify_actor`, `apify_run` | Inspect/start a public-data scraper, read results/status, or abort it | `APIFY_TOKEN` |
| `web_fetch` | Read a URL and answer a question about its content | Bedrock credentials for the model call |
| `web_search` | Search current web information through Exa | Appears when `EXASEARCH_API_KEY` is set |
| `x_search` | Search X/Twitter through Dexter's X adapter | Appears when `X_BEARER_TOKEN` is set; API access still depends on the token's permissions |

Set provider keys in `.env` or `.env.local` for local workers. The finance tools are registered even without a key; successful provider access requires valid credentials. Their internal routing and the URL fetcher's model calls use Bedrock. The separate sentiment tool uses OpenRouter Decisions with `~typesafe/jev-latest`, currently Jev 1.14. Research-capable roles get the broader data tools; the blind backtester has `run_backtest` and same-strategy blind delegation only, without live-data or sentiment access. See [data sources](docs/data-sources.md) for exact coverage and verification.

Financial Datasets credentials are configured locally and in the hosted AWS secret. A real hosted Dexter `get_income_statements` call returned an AAPL annual statement and source URL on 2026-10-23. X bearer credentials are also configured locally and on AWS; the deployed native search tool retrieved real posts with source URLs after credits were added. After Bedrock activation completed, one hosted Sol run successfully called both `x_search` and `get_income_statements`, returned actual post URLs/timestamps and statement values/source URL, and finished idle. Verified on image `1792779772` at 13:28 CDT on 2026-10-23.

There is no custom research API or conversation mode/cutoff lock. The Desk's cached data loaders and backtest remain separate modules. Live search and finance responses are not point-in-time-safe backtest inputs; historical decisions must still use cutoff-aware loaders.

All configured provider integrations have now passed actual hosted-agent checks: Financial Datasets statements, X posts, Exa search, page fetching, FRED, Alpaca paper account reads, Apify collection/results, and Jev sentiment on both X and scraped evidence. Verified on AWS image `1792779772`, 2026-10-23. This covers the exercised paths, not every dataset or Actor. See [hosted verification](docs/data-sources.md#hosted-verification-2026-10-23) for exact inputs, results, cost and limitations. Rebuild locally with `npm run dev`, or deploy with the commands below.

The [hosted fund walkthrough](docs/fund-e2e-verification.md) records real multi-agent research, live proposal/review and a separate blind historical baseline. The backend correctly returned FAIL on the baseline’s excess-return gate; no orders were submitted. The initial live proposal is a provisional cash research hold, with expanded research preserved for its next reassessment.

## Hosted AWS demo

The hosted version runs the same single container on a dedicated EC2 instance. CloudFront provides HTTPS and forwards live API/event traffic without caching it. An encrypted EBS disk stores agent conversations, files, and shared canvas positions across container restarts and deployments. ECR stores the image, Secrets Manager stores API keys and demo credentials, and an IAM instance role grants Bedrock access. Systems Manager manages the host without an open SSH port.

The demo accounts are `kush@example.com`, `mayank@example.com`, and `gerson@example.com`. Demo passwords are saved locally in ignored `.local/hosting/demo-accounts.json`. Existing Team 4 funds retain their team access. New funds belong to their creator: use **Share** to add a teammate by email. Registered teammates see the fund on their dashboard. For a new email, copy the single-use invitation link so they can set a password; invitations expire after seven days, and no email is sent automatically. The owner can remove access in the same popup. Each fund has its own shared board; chats show who sent each message. Agent activity, files, dragged positions, and connected viewer counts update across browsers. Pan, zoom, selection, and collapsed branches stay personal.

Build and deploy or update from this laptop:

```sh
docker build --platform linux/arm64 -f backend/Dockerfile -t aws-hackathon-sandbox:hosted .
./workshop-run uv run python scripts/hosting.py
```

The script prints the HTTPS URL and records only this deployment's resources in `.local/hosting/resources.json`. It copies configured API secrets from `.env` to Secrets Manager, never into the image. Hosted workers obtain renewable credentials from their instance role. The image registers the native tools listed above. Exa and X search are included when their keys are set; actual provider access requires valid credentials.

Alpaca paper credentials are configured in the existing Secrets Manager environment. On 2026-10-23, the deployed backend and a real hosted Dexter `alpaca_paper_account` call verified AWS-Hack account `PA33F249I` as ACTIVE with $100,000 USD cash/equity and no positions or open orders. That account-read check submitted no orders. A later human-approved hosted flow submitted exactly one $1 AAPL paper order, verified its fill and restored the fund stop. See [Alpaca verification](docs/agent-roles.md#alpaca-deployment-verification) for scope. Secrets are loaded by `/opt/agent-canvas/start.sh` each time the existing `agent-canvas` systemd service starts; updating the secret requires restarting that service through Systems Manager.

This is a shared hackathon demo, with a single application process and no separate customer tenants. The workshop account and its resources remain subject to the event's lifetime. The hosted board starts independently of your laptop's agent history. Back up `/opt/agent-canvas/state` before removing the host; terminating it deletes that disk.

Preview cleanup:

```sh
./workshop-run uv run python scripts/hosting.py --cleanup
```

Add `--apply` to remove the app. CloudFront disabling and instance termination are asynchronous; rerun the same cleanup command when prompted until it completes. This removes the dedicated instance, distribution, image repository, security group, and IAM role, and schedules the secret for deletion with seven days of recovery. The existing workshop desktops and earlier AgentCore sample are separate resources.

## Shared workspace

The original Team 4 fund keeps its existing `.local/workspace/`, conversations, roster, and layout. New funds store their runtime under `.local/funds/<fund-id>/`, with a shared `workspace/` and separate `agent/`, `agents/`, roster, and layout. Fund metadata lives in `.local/funds.json`. Files, chats, worker authentication tokens, and canvas positions are scoped per fund. All agents inside a fund see its file changes immediately.

Conversations and activity remain separate. Dexter's history is in `.local/agent/`; created agents' histories are under `.local/agents/<id>/`. The roster is in `.local/agents.json`. All of `.local/` is excluded from Git and survives container restarts. The shared canvas layout is stored in `.local/layout.json`.

The sandbox uses a non-root user, a read-only application filesystem, resource limits, and only a localhost API port. Application code and the built frontend are inside the image. It mounts only this project's local state, environment settings, and the two dedicated workshop credential files. It does not mount your home directory or Docker socket. Network access remains available for Bedrock and the enabled data/search providers.

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

Keep both files private with `chmod 600`. Refresh them through Workshop Studio when the session expires. Canvas agents default to `us.openai.gpt-6.1-sol`, offer Opus 5.5 in the idle-agent model selector, and pin backtesters to Opus 4.6. `MAIN_AGENT_MODEL` configures new-agent defaults; saved per-agent choices persist. The workshop participant credentials previously denied Sol 6.1 and Opus 5.5 inference. Hosted model activation is now complete: both agreements report available, and a real hosted Sol run used X and Financial Datasets successfully. Local participant permissions remain separate from the EC2 role; Opus 4.6 evaluation was verified. See [agent models and access limits](docs/agent-roles.md#agent-models). `.env` contains optional `AWS_REGION` and blank credentials for Dexter’s finance, search, and model providers; `.env.example` is the shared template. No account ID is required by the app. Configure the provider keys listed in Agent tools to use Dexter's native finance and search integrations.

Credentials stay in the backend. Model requests incur normal Bedrock charges. Running this local version creates no new AgentCore resources.

## Code and checks

- `frontend/src/board/`: recursive tree layout and SVG canvas adapted from the sibling takehome project.
- `frontend/src/funds/`: fund dashboard, setup, and overview.
- `frontend/src/AgentWorkspace.tsx`: selected agent's chat, activity, and shared files.
- `backend/app/funds.py` and `backend/app/routes/funds.py`: fund mandates and scoped canvas access.
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

The hosted backtester uses Mayank’s walk-forward engine (`BACKTEST_ENGINE=wf`). The image includes `data/wf`, `reports/wf` and `specs`. Opus 4.6 remains the blind evaluator; reports retain their actual PASS/FAIL and author-model leakage labels. Existing strategies and approvals are preserved; switching engines does not relabel old results.

The hosted watchdog’s Guardrail and AgentCore Memory have a separate private inventory. Preview their cleanup with `./workshop-run uv run python scripts/hosting_watchdog.py --cleanup`; add `--apply` to remove only resources created by that setup. Run this before the existing hosting cleanup. Resources discovered from another setup are preserved.
