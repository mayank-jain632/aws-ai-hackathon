# AWS integration review

Written 2026-10-23 by the watchdog session for Aaron. It maps where each lane can plug into the AWS services the event gives us, ranked by what judges can see before the 3:00 PM feature freeze (demos at 4:30 PM). "Verified" means exercised against AWS and recorded in a status file; everything else here is proposed or in progress.

## Hard constraints

- **Allowed services and models** are listed in `docs/reference/aws-services-and-allowed-models.md`. Only the models named there are available to the workshop account.
- **The hosted role is narrow.** `scripts/hosting.py` gives the EC2 role `team4-agent-canvas` four things: `bedrock:InvokeModel` and `InvokeModelWithResponseStream` on the catalog models plus Luna, `secretsmanager:GetSecretValue` on its one secret, ECR pull on its repository, and `AmazonSSMManagedInstanceCore`. Any new AWS call from the hosted app needs an IAM change first.
- **New billed resources** need a person's authorization, ownership tags, an inventory and a scoped cleanup path (AGENTS.md). D25 adds: agents create only their own owner-named resources tagged `Owner=<name>`, and only Kushagra's deployment owner changes the hosted role, secret, image or distribution. Aaron authorized the four watchdog resources below; anything else needs its own OK.
- **Workshop CLI credentials expire after 60 minutes.** They only reach code through `./workshop-run` and the ignored `~/.aws/aws-hackathon-2026.*` files.

## Already on AWS

| Service | What it does for us | Evidence |
|---|---|---|
| EC2 | Runs the one app container (React, FastAPI, Bun/Dexter workers) | Hosted revision `4c776fe`, `hub/status/orchestration.md` |
| CloudFront | HTTPS at dgvmahl7u2clq.cloudfront.net, no API caching | Verified by Lane 5 |
| EBS (encrypted) | Persists funds, conversations, shared files, desk and watchdog records across restarts | Six funds and their records survived a restart |
| ECR | Stores the app image | `scripts/hosting.py` |
| Secrets Manager | Provider keys (Alpaca, Financial Datasets, X, Exa, OpenRouter, Apify) and demo logins | Alpaca and Financial Datasets reads verified hosted |
| IAM | Instance role scoped to exact Bedrock profile and model ARNs | `scripts/hosting.py` policy `app` |
| Systems Manager | Host management without SSH; deploys run through `send_command` | `scripts/hosting.py` |
| Bedrock Converse | Every canvas agent through `ChatBedrockConverse` in `backend/worker/run.ts`; Desk analysts and the watchdog second opinion through `backend/app/agents/base.py` (`us.openai.gpt-5.6-luna`, no temperature) | Luna verified hosted; Opus 4.6 evaluator verified |
| AgentCore Runtime (separate sample) | `backend/agent.py` is the starter-kit handler: one Converse call to Luna, `maxTokens` 128. `backend/setup_agentcore_role.py` made its execution role. Its runtime, S3 bucket, role and log group are still deployed, inventoried in the ignored `backend/resources.json`, with cleanup in `scripts/cleanup_cloud.py`. It is not wired to the product | README "earlier cloud sample runtime still exists" |

## Model findings (fix first)

1. **The canvas defaults are not on the published list.** `backend/model-catalog.json` sets `us.openai.gpt-6.1-sol` as the default and `us.anthropic.claude-opus-5-5` as the alternate (D20). Neither appears in the event's model list. After account-level activation the hosted EC2 role does run Sol 6.1 (D24, eight role agents verified at 13:28), but workshop participant credentials are still denied both, so local runs and any laptop demo need an allowed model. The remaining risk is a judge asking why the demo uses a model outside the published list.
2. **Allowed replacements.** OpenAI GPT-5.4, GPT-5.5, GPT-5.6 Luna, Sol and Terra; Claude Sonnet 5, Opus 5, Fable 5, Opus 4.8, 4.7, 4.6, Sonnet 4.6, Opus 4.5, Sonnet 4.5, Haiku 4.5; Amazon Nova; Meta Llama; Mistral; DeepSeek-R1.
3. **Recommendation.** Keep Sol 6.1 on the hosted role if the team accepts that risk; otherwise GPT-5.6 Sol as the default, Claude Opus 4.8 as the alternate, Opus 4.6 stays the pinned evaluator. Resolve the exact profile IDs with `get_inference_profile` the way `hosting.py` already does, update the catalog, and rerun hosting so the IAM policy follows. `backend/app/models.py` hardcodes the error text "Choose Claude Opus 5.5 or GPT-6.1 Sol"; change it with the catalog.
4. **Data retention.** GPT-5.4, 5.5, 5.6 Luna, Sol, Terra and Claude Fable 5 need the account's Bedrock data retention set to Default. If a GPT call fails with a retention error, open the Bedrock Playground, send one prompt to that model, and accept Default when asked.
5. **Q11, one model or several.** A deliberate mix shows more of Bedrock at no extra build cost: GPT-5.6 Sol for orchestration, Opus 4.6 for blind evaluation (already pinned, cutoff May 2025), Luna for the watchdog's second opinion, and Nova Micro or Haiku 4.5 for cheap classification. Record the choice as a decision so it stops moving.
6. **Sentiment runs off AWS.** `analyze_sentiment` uses Jev through OpenRouter only. Amazon Comprehend `DetectSentiment` and `DetectTargetedSentiment` would add an AWS-native second reading on the same excerpts with no resource to create, just one IAM action.

## Wiring map by lane

Effort: S is under 30 minutes, M is about an hour, L is past the freeze.

### Lane 1, orchestration and roles

| Service | Plugs in at | Judges see | Effort | New resource |
|---|---|---|---|---|
| AgentCore Observability (ADOT/OTEL traces into CloudWatch) | Wrap `LocalAgent.run` in `backend/app/agent.py` and the worker spawn in `run.ts` with spans per agent and tool call | A trace tree of orchestrator, research, strategy, backtester, executor, watchdog | M | No, logs and traces land in CloudWatch; needs IAM for X-Ray/Logs |
| AgentCore Gateway (desk tools as MCP) | Expose `inspect_desk`, `run_backtest`, `submit_paper_order` and the watchdog review as Gateway targets | Any MCP agent can use the desk, still behind the watchdog | L | Gateway plus Lambda or HTTP target and auth design |
| AgentCore Runtime or Harness for the canvas | Would replace the EC2 worker host | Fully managed hosting | L | Yes. D7 and the PRD keep the canvas on EC2 with Dexter as the loop; moving it today is out of scope |

### Lane 2, evaluation and backtest

| Service | Plugs in at | Judges see | Effort | New resource |
|---|---|---|---|---|
| AgentCore Code Interpreter | A new evaluator path beside `backend/app/backtest.py`, running generated strategy code in a sandbox | Agent-written strategies executed safely; `docs/agent-roles.md` says generated Python strategies are not executed today | L | Code Interpreter session; changes the recorded evaluation method, so Lane 2 must log a decision first |
| S3 | Archive each backtest result and walk-forward run (`reports/wf/` on Mayank's branch) | Durable, citable evaluation artifacts | S | Bucket |
| Athena or QuickSight over those results | Query the S3 archive | Charts of runs | M | Skip unless an S3 archive already exists |

### Lane 3, data and research

| Service | Plugs in at | Judges see | Effort | New resource |
|---|---|---|---|---|
| Amazon Comprehend | A `detect_sentiment` tool beside `analyze_sentiment` in `backend/worker/data-tools.ts`, or a Python helper | AWS-native sentiment next to Jev on the same excerpts | S | No; IAM `comprehend:DetectSentiment` and `DetectTargetedSentiment` |
| Bedrock Managed Knowledge Base over SEC filings | Research tool that retrieves filing passages | Cited RAG over 10-K and 10-Q text | M to L | KB plus S3 source. `data/sec/` holds only XBRL numbers (`fundamentals.csv`), so filing text must be fetched and ingested first |
| Titan or Cohere Embed, Cohere Rerank 3.5 | Inside the KB, or to rerank Exa results | Better retrieval | M | Rides on the KB |
| S3 Vectors | Vector store if we skip a Managed KB | Same | M | Vector bucket |
| AgentCore Browser | Research browsing beside Exa and `web_fetch` | Live page interaction | M | Browser session; Exa, X and Apify already cover public pages |
| Textract | Parse filing PDFs | Tables from scanned filings | M | No; only useful once filing PDFs are in scope |

### Lane 4, execution and watchdog

| Service | Plugs in at | Judges see | Effort | New resource |
|---|---|---|---|---|
| Bedrock Guardrails (`ApplyGuardrail`) | `backend/app/watchdog/claims.py` scanning strategy rationales and memos | Prompt-injection and limit-evasion text caught in agent-written evidence | S | Guardrail (authorized) |
| AgentCore Memory | `backend/app/watchdog/feedback.py` lessons | Each fund's lessons persist across sessions under that fund's server-assigned identity; agents retrieve them semantically | M | Memory (authorized) |
| CloudWatch metrics and alarms | `gate.enforce` and `monitor.audit` | Blocks per rule and halts on a CloudWatch graph; an alarm on the firm-wide halt | S | Metrics need none; the alarm is a resource (authorized) |
| EventBridge | Same hooks, `PutEvents` on the default bus | Halts and blocks as events other services can react to | S | Rule and log group (authorized) |
| AWS DevOps Agent | Point it at the halt alarm | An AWS agent investigating our agent's emergency stop | M | Console setup; not before freeze |
| AgentCore Identity | Alpaca keys in a token vault instead of Secrets Manager | Credential delegation story | M | Yes; Secrets Manager already works, so low value today |

### Lane 5, platform

| Service | Plugs in at | Judges see | Effort | New resource |
|---|---|---|---|---|
| IAM additions | `scripts/hosting.py` policy, or separate inline policies per lane like the watchdog's | Nothing directly; unblocks every row above | S | No |
| DynamoDB run record | PRD section 4 item 3; today `desk.json` on encrypted EBS already persists strategies, reviews, tests and orders | Queryable run history | M | Table. Low value while EBS persistence works |
| EventBridge Scheduler or Step Functions | Trigger the daily story by messaging the orchestrator through the existing API | A scheduled daily run | M | Schedule plus an API destination. It must start Dexter runs, never replace Dexter's loop |
| CloudWatch dashboard | One dashboard for app health, Bedrock invocations and watchdog metrics | One AWS screen for the demo | S | Dashboard |

### Lane 6, demo

- Show the AWS console beside the canvas: the Bedrock model behind each agent, the watchdog's CloudWatch graph and halt alarm, the Guardrail intervention on an injected memo, and the AgentCore Memory record of a lesson.
- Say plainly which parts are live AWS calls and which ran in mock mode; judges reward honest labeling over a bigger claim.

## What the watchdog lane wired (on main, not yet verified live)

The code below is on main. The AWS pieces passed live checks in Aaron's participant account (not hosted; see Two AWS accounts). Live Alpaca data runs only on the hosted app, where the keys live (D25).

- **Live market data in the pre-trade gate**, from Alpaca with the existing paper keys: asset tradability and status, latest trade against the previous close, the market clock, and the account's equity history for the drawdown peak. Falls back to the snapshot data and says so when Alpaca is unreachable.
- **Bedrock Guardrail `aaron-watchdog`**: a prompt-attack filter plus a denied topic for limit evasion (splitting orders, resubmitting under new ids, hiding exposure). The monitor runs strategy rationales and cited memos through `ApplyGuardrail` and records interventions as moderator events.
- **AgentCore Memory `aaron_watchdog_lessons`** with a semantic strategy and one namespace per fund (`/watchdog/funds/{actorId}/lessons/`, keyed on the server-assigned fund ID; Lane 5's isolation patch, 8533f38), so lessons persist across sessions and `watchdog_lessons` retrieves only that fund's.
- **CloudWatch metrics** in namespace `Team4/Watchdog` (verdicts by rule and decision, halts, moderator events) and an **alarm `aaron-watchdog-firm-wide-halt` on the firm-wide halt**.
- **EventBridge events** from source `team4.watchdog`, matched by rule `aaron-watchdog-audit`, which writes them to the log group `/aws/events/aaron-watchdog`.
- **`scripts/watchdog_aws.py`** provisions all of it: preview by default, `--apply` to create, `--verify` for live checks, `--cleanup` to remove. Per D25 it never touches `team4-agent-canvas`; Lane 5's `scripts/hosting_watchdog.py` reuses it for the hosting account (see Two AWS accounts). Everything is tagged `Project`, `Team`, `Name` and `Owner=aaron`.
- **Live market data is verified on the hosted app, not locally.** Per D25 the Alpaca keys live only in the hosted secret, so the gate's live checks run once the hosted image includes this code.

## Next 75 minutes, ranked

1. **Decide on the published model list** (Lane 5 with Lane 1, Kushagra). Hosted agents run on Sol 6.1 now (D24), so this is a judging and laptop-access question, not an outage; switching is a catalog edit plus a hosting rerun.
2. **Hosted watchdog on AWS** (Lane 5, in progress). Kushagra's deploy owner creates the hosting account's Guardrail and Memory with `scripts/hosting_watchdog.py` and redeploys; the full set already passed live checks in Aaron's participant account.
3. **Add Comprehend sentiment** (Lane 3). No resource, one IAM action, and it turns sentiment from an OpenRouter-only input into an AWS AI input.
4. **Second opinion on AgentCore Runtime** (Aaron's AgentCore session). It hosts the watchdog's second opinion in its own new runtime behind a flag in `backend/app/watchdog/opinion.py`, with Luna on Bedrock as the fallback. Kushagra's sample runtime stays untouched (D25).

**Not before freeze:** moving the canvas to AgentCore Runtime or Harness, Gateway, Code Interpreter evaluation, Knowledge Bases over filings, Step Functions or Scheduler, DynamoDB run records, AgentCore Identity, Browser, Textract, Athena, QuickSight, S3 Vectors, DevOps Agent. Do not use Amazon Forecast (closed to new customers) or Lookout for Metrics (retired).

## Two AWS accounts

- **Aaron's participant account (proof segment, not hosted).** Aaron's `team4-toolkit` login reaches his own participant account, not the account that hosts the app (D28). `scripts/watchdog_aws.py --apply` created the full set there at 13:52 (Guardrail, Memory, CloudWatch alarm, EventBridge rule and log group), and `--verify` passed all seven live checks. Label this evidence "Aaron's participant account, not hosted".
- **Hosting account (Lane 5).** Kushagra's deploy owner runs `scripts/hosting_watchdog.py`, which reuses `watchdog_aws.apply(..., core_only=True)` to create only the Guardrail and Memory there (43d416a, 50d3a36). `scripts/hosting.py` injects `WATCHDOG_GUARDRAIL_ID`, `WATCHDOG_GUARDRAIL_VERSION` and `WATCHDOG_MEMORY_ID` and scopes the hosted role to those ARNs, PutMetricData in `Team4/Watchdog`, and PutEvents on the default bus. No alarm, rule or log group is created there.
- **Runbook for the hosting account:** (1) `./workshop-run uv run python scripts/hosting_watchdog.py` to preview; (2) the same with `--apply`; (3) rerun `scripts/hosting.py` so the secret carries the IDs and the role carries the grants, then redeploy.
- **Off unless configured.** With neither the IDs nor `WATCHDOG_AWS=1`, the watchdog makes no AWS calls. With only the IDs (the hosted case) it never lists resources, so the scoped role sees no AccessDenied. No verdict depends on AWS either way; `scripts/watchdog_aws.py` reads the account from `sts get-caller-identity` and hardcodes no ID or ARN.

## Needs a human

- **Aaron:** load the workshop CLI credentials into `~/.aws/aws-hackathon-2026.credentials` and `.config`, refreshing them hourly.
- **Aaron or Kushagra:** decide the model switch. D20 records Kushagra's choice of Sol 6.1, so reversing it is a person's call.
- **Aaron:** mark D17 and D19 Accepted or leave them Proposed.
- **Kushagra:** run `scripts/hosting_watchdog.py --apply`, then `scripts/hosting.py`, and redeploy so the hosted watchdog's live data, Guardrail, Memory and metrics run; rerun `scripts/hosting.py` after any catalog change so the IAM policy matches.
- **Whoever owns the account:** set Bedrock data retention to Default if a GPT call fails with a retention error.
- **Aaron:** authorize any resource beyond the watchdog's four (a Knowledge Base, an S3 bucket, a Code Interpreter session) before anyone creates it.
