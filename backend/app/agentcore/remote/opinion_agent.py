"""Watchdog second-opinion agent, hosted on Amazon Bedrock AgentCore Runtime.

Deployed by `scripts/agentcore_deploy.py` as a standalone code package; it imports nothing
from the backend. The backend sends the reviewer instructions, the flagged order's context,
the lessons recalled from AgentCore Memory and the JSON schema to answer in. This agent runs
the model loop on AgentCore: one Bedrock Converse call (gpt-5.6-luna, no temperature),
validation against the schema's required fields, and one corrective retry. The verdict is
already final before this runs; the agent can only explain it.

Started through `opentelemetry-instrument`, so AgentCore Observability records the
invocation span and the Converse call beneath it.
"""

import json
import os
import re
import time

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp

try:
    from opentelemetry import trace

    TRACER = trace.get_tracer("team4.watchdog.opinion")
except ImportError:  # the package still runs without the distro
    TRACER = None

app = BedrockAgentCoreApp()
MODEL_ID = os.getenv("MODEL_ID", "us.openai.gpt-5.6-luna")
BEDROCK = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))


def extract_json(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    return json.loads(raw)


def prompt_for(payload: dict) -> str:
    lessons = payload.get("lessons") or []
    recalled = "\n".join(f"- {line}" for line in lessons) or "- none recalled yet"
    return (
        "Flagged order and context:\n"
        f"{json.dumps(payload['context'], indent=2)}\n\n"
        "Lessons the watchdog has recorded on earlier runs (from AgentCore Memory):\n"
        f"{recalled}\n\n"
        "Reply with only a JSON object matching this schema:\n"
        f"{json.dumps(payload['schema'])}"
    )


def review(payload: dict) -> dict:
    schema = payload["schema"]
    required = schema.get("required", [])
    messages = [{"role": "user", "content": [{"text": prompt_for(payload)}]}]
    usage = {"inputTokens": 0, "outputTokens": 0}
    for attempt in range(2):
        response = BEDROCK.converse(
            modelId=MODEL_ID,
            system=[{"text": payload["system"]}],
            messages=messages,
            inferenceConfig={"maxTokens": 1500},
        )
        for key in usage:
            usage[key] += response.get("usage", {}).get(key, 0)
        text = "".join(part.get("text", "") for part in response["output"]["message"]["content"])
        try:
            opinion = extract_json(text)
            missing = [key for key in required if key not in opinion]
            if missing:
                raise ValueError(f"missing fields {missing}")
            return {"opinion": opinion, "attempts": attempt + 1, "usage": usage}
        except ValueError as error:
            messages += [
                {"role": "assistant", "content": [{"text": text or "(empty)"}]},
                {"role": "user", "content": [{"text": f"That did not validate ({error}). Reply again with only the JSON object."}]},
            ]
    raise ValueError("model output did not validate after 2 attempts")


@app.entrypoint
def invoke(payload, context=None):
    started = time.time()
    if TRACER:
        with TRACER.start_as_current_span("watchdog.second_opinion") as span:
            span.set_attribute("watchdog.fund", str(payload.get("fund", "")))
            span.set_attribute("watchdog.verdict", str(payload["context"].get("verdict", "")))
            span.set_attribute("watchdog.rules", ",".join(payload["context"].get("rules", [])))
            span.set_attribute("watchdog.lessons_recalled", len(payload.get("lessons") or []))
            result = review(payload)
            span.set_attribute("gen_ai.usage.input_tokens", result["usage"]["inputTokens"])
            span.set_attribute("gen_ai.usage.output_tokens", result["usage"]["outputTokens"])
    else:
        result = review(payload)
    session = getattr(context, "session_id", None) if context else None
    return {**result, "model": MODEL_ID, "session_id": session, "seconds": round(time.time() - started, 2)}


if __name__ == "__main__":
    app.run()
