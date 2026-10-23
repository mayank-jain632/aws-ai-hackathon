# AgentCore: watchdog second opinion on AgentCore Runtime (D28)

The canvas stays on EC2. One pipeline agent runs on Amazon Bedrock AgentCore: the watchdog's second opinion on blocked and near-miss paper orders (`backend/app/watchdog/opinion.py`, D17).

## How a flagged order reaches AgentCore

1. `paper.submit` runs the deterministic gate. A block or near miss is written to the fund's `feedback.jsonl`; the verdict is final.
2. `opinion.second_opinion` builds the order's context, then calls `backend.app.agentcore.second_opinion` when `AGENTCORE_OPINION_ARN` is set and mock mode is off.
3. The backend recalls lessons from the watchdog's AgentCore Memory `aaron_watchdog_lessons` (D26, `watchdog/aws.py`), then calls `InvokeAgentRuntime` with the reviewer instructions, the context, those lessons and the answer schema. It starts a W3C `traceparent`, so the X-Ray trace ID is known before the call, and uses one runtime session per fund per day.
4. Runtime agent `aaron_watchdog_opinion` (`backend/app/agentcore/remote/opinion_agent.py`) makes the Converse call (`us.openai.gpt-5.6-luna`, no temperature), checks the schema's required fields, retries once and returns. It runs under `opentelemetry-instrument`, so AgentCore Observability records its span and the Bedrock call.
5. The backend validates the reply against `SecondOpinion`. Any AWS error or invalid reply returns None, and the existing in-process Bedrock path runs. The opinion's `source` says which path answered (`agentcore:...` or `bedrock:...`).

Every invocation, successful or not, goes to `.local/agentcore/invocations.jsonl` with its session ID, X-Ray trace ID and console link. People can read it at `GET /api/agentcore`, together with links to the runtime, GenAI Observability and the runtime log group.

## Run it (Aaron's participant account)

```sh
AWS_PROFILE=team4-toolkit uv run python scripts/agentcore_deploy.py            # preview
AWS_PROFILE=team4-toolkit uv run python scripts/agentcore_deploy.py --apply    # deploy or update
AWS_PROFILE=team4-toolkit AGENTCORE_OPINION_ARN=<printed ARN> uv run python scripts/watchdog_demo.py --fast
```

The demo's $40,000 MSFT block produces a hosted second opinion; its line reads `Second opinion (agentcore:aaron_watchdog_opinion-...)`. With `AGENTCORE_OPINION_ARN` unset, as on the hosted app today, the hook returns None and `opinion.py` behaves exactly as before.

The deploy takes the account from the signed-in credentials and derives every ARN, the bucket name and the log group from it (`--account <id>` is an optional guard). It packages Linux arm64 wheels for Python 3.12 (`bedrock-agentcore`, `aws-opentelemetry-distro`, `boto3`) with the agent file, uploads the zip to the owner's bucket, creates the execution role and runtime, turns on CloudWatch Transaction Search, and sets trace indexing to 100% so every invocation opens on the X-Ray trace page. All resources are tagged `Project=AWS-Hackathon`, `Owner=aaron`, `Team=4`. The inventory is in ignored `.local/agentcore/resources.json`.

Cleanup previews by default, checks the account and every ownership tag, and then removes only the inventoried runtime, log group, bucket and role. `--restore-transaction-search` also returns the span destination and indexing to their previous values:

```sh
AWS_PROFILE=team4-toolkit uv run python scripts/agentcore_cleanup.py --apply --restore-transaction-search
```

## Hosting account runbook (for the deployment owner, after the freeze)

The hosted app calls AWS as `team4-agent-canvas` in the hosting account, which is not Aaron's participant account. To have it use the hosted second opinion:

1. With hosting-account credentials, from a checkout of `main`: `./workshop-run uv run python scripts/agentcore_deploy.py`, then the same with `--apply`. It prints the runtime ARN and the exact IAM statement.
2. Add that statement to the `team4-agent-canvas` role policy in `scripts/hosting.py` (shape below; `--policy` prints it again from the inventory).
3. Set `AGENTCORE_OPINION_ARN=<printed ARN>` in the hosted environment and redeploy. Lessons recall needs D26's Memory permissions on the same role; without them the runtime still answers, with no lessons.
4. Check: trigger a blocked order, then `GET /api/agentcore` shows the invocation with `ok: true` and an X-Ray trace ID.

## IAM handoff for team4-agent-canvas

```json
{
  "Sid": "InvokeWatchdogOpinionRuntime",
  "Effect": "Allow",
  "Action": "bedrock-agentcore:InvokeAgentRuntime",
  "Resource": [
    "arn:aws:bedrock-agentcore:us-east-1:<hosting-account-id>:runtime/aaron_watchdog_opinion-<suffix>",
    "arn:aws:bedrock-agentcore:us-east-1:<hosting-account-id>:runtime/aaron_watchdog_opinion-<suffix>/runtime-endpoint/*"
  ]
}
```

`<suffix>` is the ID AgentCore assigns at creation; the deploy prints the full ARNs. Not applied anywhere (D25). AgentCore Runtime also accepts a resource-based policy (`PutResourcePolicy`), so the hosted role could call the runtime in Aaron's participant account without a second deploy: that needs this statement with that runtime's ARN plus a runtime policy naming the `team4-agent-canvas` role. Neither is set up.

## Roadmap, not built: AgentCore Gateway

Expose the desk and watchdog APIs as MCP tools through an AgentCore Gateway, so agents outside the canvas (or a hosted orchestrator) call `POST /api/watchdog/review` (dry-run verdict), `GET /api/funds/{id}/watchdog` (stop state, lessons) and the desk's strategy and test records through one authenticated MCP endpoint. Targets would be an OpenAPI spec of those routes with outbound auth through the existing worker tokens; the gate stays deterministic and in the backend. Nothing here is deployed.

## Limits

- The resources are in Aaron's participant account, not the hosting account. The hosted app has no `AGENTCORE_OPINION_ARN` and keeps the in-process path. Adopting it there means rerunning the deploy in the hosting account and granting `team4-agent-canvas` `bedrock-agentcore:InvokeAgentRuntime` on the runtime ARN (D25, D28).
- The opinion explains a verdict; it cannot change one. Nothing on the order path waits on AgentCore except the second opinion itself, which runs after the gate.
- Recalled lessons are whatever Memory's semantic strategy has extracted so far. Right after the first blocks it can be empty, and the payload says "none recalled yet".
