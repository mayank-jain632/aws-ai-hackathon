# AgentCore: watchdog second opinion on AgentCore Runtime (D28)

The canvas stays on EC2. One pipeline agent runs on Amazon Bedrock AgentCore: the watchdog's second opinion on blocked and near-miss paper orders (`backend/app/watchdog/opinion.py`, D17).

## How a flagged order reaches AgentCore

1. `paper.submit` runs the deterministic gate. A block or near miss is written to the fund's `feedback.jsonl`; the verdict is final.
2. `opinion.second_opinion` builds the order's context, then calls `backend.app.agentcore.second_opinion` when `AGENTCORE_OPINION_ARN` is set and mock mode is off.
3. The backend recalls lessons from the watchdog's AgentCore Memory `aaron_watchdog_lessons` (D26, `watchdog/aws.py`), then calls `InvokeAgentRuntime` with the reviewer instructions, the context, those lessons and the answer schema. It starts a W3C `traceparent`, so the X-Ray trace ID is known before the call, and uses one runtime session per fund per day.
4. Runtime agent `aaron_watchdog_opinion` (`backend/app/agentcore/remote/opinion_agent.py`) makes the Converse call (`us.openai.gpt-5.6-luna`, no temperature), checks the schema's required fields, retries once and returns. It runs under `opentelemetry-instrument`, so AgentCore Observability records its span and the Bedrock call.
5. The backend validates the reply against `SecondOpinion`. Any AWS error or invalid reply returns None, and the existing in-process Bedrock path runs. The opinion's `source` says which path answered (`agentcore:...` or `bedrock:...`).

Every invocation, successful or not, goes to `.local/agentcore/invocations.jsonl` with its session ID, X-Ray trace ID and console link. People can read it at `GET /api/agentcore`, together with links to the runtime, GenAI Observability and the runtime log group.

## Run it

```sh
AWS_PROFILE=team4-toolkit uv run python scripts/agentcore_deploy.py --account <id>            # preview
AWS_PROFILE=team4-toolkit uv run python scripts/agentcore_deploy.py --account <id> --apply    # deploy or update
AWS_PROFILE=team4-toolkit AGENTCORE_OPINION_ARN=<printed ARN> uv run python scripts/watchdog_demo.py --fast
```

The demo's $40,000 MSFT block produces a hosted second opinion; its line reads `Second opinion (agentcore:aaron_watchdog_opinion-...)`.

The deploy packages Linux arm64 wheels for Python 3.12 (`bedrock-agentcore`, `aws-opentelemetry-distro`, `boto3`) with the agent file, uploads the zip to the owner's bucket, creates the execution role and runtime, and turns on CloudWatch Transaction Search. All resources are tagged `Project=AWS-Hackathon`, `Owner=aaron`, `Team=4`. The inventory is in ignored `.local/agentcore/resources.json`.

Cleanup previews by default, checks the account and every ownership tag, and then removes only the inventoried runtime, log group, bucket and role:

```sh
AWS_PROFILE=team4-toolkit uv run python scripts/agentcore_cleanup.py --apply
```

## Limits

- The resources are in Aaron's participant account, not the hosting account. The hosted app has no `AGENTCORE_OPINION_ARN` and keeps the in-process path. Adopting it there means rerunning the deploy in the hosting account and granting `team4-agent-canvas` `bedrock-agentcore:InvokeAgentRuntime` on the runtime ARN (D25, D28).
- The opinion explains a verdict; it cannot change one. Nothing on the order path waits on AgentCore except the second opinion itself, which runs after the gate.
- Recalled lessons are whatever Memory's semantic strategy has extracted so far. Right after the first blocks it can be empty, and the payload says "none recalled yet".
