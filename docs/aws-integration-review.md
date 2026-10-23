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

1. **The canvas defaults are not on the allowed list.** `backend/model-catalog.json` sets `us.openai.gpt-6.1-sol` as the default and `us.anthropic.claude-opus-5-5` as the alternate (D20). Neither appears in the event's model list, and Lane 5 recorded that workshop IAM explicitly denies both. Hosted agents on those models fail before they use a tool, which is the one failure the demo cannot absorb.
2. **Allowed replacements.** OpenAI GPT-5.4, GPT-5.5, GPT-5.6 Luna, Sol and Terra; Claude Sonnet 5, Opus 5, Fable 5, Opus 4.8, 4.7, 4.6, Sonnet 4.6, Opus 4.5, Sonnet 4.5, Haiku 4.5; Amazon Nova; Meta Llama; Mistral; DeepSeek-R1.
3. **Recommendation.** GPT-5.6 Sol as the default, Claude Opus 4.8 as the alternate, Opus 4.6 stays the pinned evaluator. Resolve the exact profile IDs with `get_inference_profile` the way `hosting.py` already does, update the catalog, and rerun hosting so the IAM policy follows. `backend/app/models.py` hardcodes the error text "Choose Claude Opus 5.5 or GPT-6.1 Sol"; change it with the catalog.
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
| AgentCore Memory | `backend/app/watchdog/feedback.py` lessons | Lessons persist across funds and sessions; agents retrieve them semantically | M | Memory (authorized) |
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

The code below is on main with stubbed tests. None of it has run against AWS or Alpaca yet: that starts when Aaron loads the workshop credentials and the Alpaca keys, then runs `scripts/watchdog_aws.py --apply` and `--verify`.

- **Live market data in the pre-trade gate**, from Alpaca with the existing paper keys: asset tradability and status, latest trade against the previous close, the market clock, and the account's equity history for the drawdown peak. Falls back to the snapshot data and says so when Alpaca is unreachable.
- **Bedrock Guardrail `aaron-watchdog`**: a prompt-attack filter plus a denied topic for limit evasion (splitting orders, resubmitting under new ids, hiding exposure). The monitor runs strategy rationales and cited memos through `ApplyGuardrail` and records interventions as moderator events.
- **AgentCore Memory `aaron_watchdog_lessons`** with a semantic strategy, so lessons persist across funds and sessions and `watchdog_lessons` can retrieve the relevant ones.
- **CloudWatch metrics** in namespace `Team4/Watchdog` (verdicts by rule and decision, halts, moderator events) and an **alarm `aaron-watchdog-firm-wide-halt` on the firm-wide halt**.
- **EventBridge events** from source `team4.watchdog`, matched by rule `aaron-watchdog-audit`, which writes them to the log group `/aws/events/aaron-watchdog`.
- **`scripts/watchdog_aws.py`** provisions all of it: preview by default, `--apply` to create, `--verify` for live checks, `--cleanup` to remove. Per D25 it never touches `team4-agent-canvas`; `--policy` prints the exact statement (D26) that Kushagra's deployment owner adds in `scripts/hosting.py`. Everything is tagged `Project`, `Team`, `Name` and `Owner=aaron`.
- **Live market data is verified on the hosted app, not locally.** Per D25 the Alpaca keys live only in the hosted secret, so the gate's live checks run once the hosted image includes this code.

## Next 75 minutes, ranked

1. **Switch the canvas to allowed models** (Lane 5 with Lane 1, Kushagra). Every hosted agent run depends on it, and it is a catalog edit plus a hosting rerun.
2. **Provision and verify the watchdog's AWS wiring** (Lane 4, Aaron). Four AWS services in the order path and the monitor, each visible in the console, all already authorized.
3. **Add Comprehend sentiment** (Lane 3). No resource, one IAM action, and it turns sentiment from an OpenRouter-only input into an AWS AI input.
4. **Give the existing AgentCore sample runtime one real job** (Lane 5 with Lane 4) if items 1 to 3 land early. Redeploying `backend/agent.py` as the watchdog's second-opinion endpoint and calling it from the app gives PRD item 8 a real AgentCore invocation and trace without moving the canvas.

**Not before freeze:** moving the canvas to AgentCore Runtime or Harness, Gateway, Code Interpreter evaluation, Knowledge Bases over filings, Step Functions or Scheduler, DynamoDB run records, AgentCore Identity, Browser, Textract, Athena, QuickSight, S3 Vectors, DevOps Agent. Do not use Amazon Forecast (closed to new customers) or Lookout for Metrics (retired).

## Needs a human

- **Aaron:** load the workshop CLI credentials into `~/.aws/aws-hackathon-2026.credentials` and `.config`, refreshing them hourly.
- **Aaron or Kushagra:** decide the model switch. D20 records Kushagra's choice of Sol 6.1, so reversing it is a person's call.
- **Aaron:** mark D17 and D19 Accepted or leave them Proposed.
- **Kushagra:** add the D26 statement to the hosted role in `scripts/hosting.py`, redeploy the image so the watchdog's live data and AWS wiring run there, and rerun `scripts/hosting.py` after any catalog change so the IAM policy matches.
- **Whoever owns the account:** set Bedrock data retention to Default if a GPT call fails with a retention error.
- **Aaron:** authorize any resource beyond the watchdog's four (a Knowledge Base, an S3 bucket, a Code Interpreter session) before anyone creates it.
