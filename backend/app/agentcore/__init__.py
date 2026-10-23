"""Amazon Bedrock AgentCore Runtime client for the watchdog second opinion (D28).

When AGENTCORE_OPINION_ARN is set (and MOCK_AGENTS is off), `opinion.second_opinion` sends
the flagged order's context to the `aaron_watchdog_opinion` agent on AgentCore Runtime
instead of calling Bedrock in-process. The payload carries the reviewer instructions, the
JSON schema to answer in, and lessons recalled from the watchdog's AgentCore Memory (D26), so
the hosted agent reads what earlier runs learned. Any failure returns None and the caller
keeps its local Bedrock path. Every invocation, with its runtime session ID and trace ID, is
kept in memory and appended to `.local/agentcore/invocations.jsonl` for the status route.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import secrets
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from backend.app.agents import base

log = logging.getLogger("desk.agentcore")

CONFIG = Config(retries={"total_max_attempts": 2, "mode": "standard"}, connect_timeout=5, read_timeout=120)
ROOT = Path(__file__).resolve().parents[3]
RECENT: deque[dict] = deque(maxlen=50)


def runtime_arn() -> str | None:
    return os.getenv("AGENTCORE_OPINION_ARN") or None


def enabled() -> bool:
    return bool(runtime_arn()) and not base.mock_mode()


def region() -> str:
    arn = runtime_arn() or ""
    return arn.split(":")[3] if arn.count(":") >= 5 else base.region()


def log_path() -> Path:
    return Path(os.getenv("AGENTCORE_LOG", ROOT / ".local/agentcore/invocations.jsonl"))


@functools.cache
def client():
    import boto3

    return boto3.client("bedrock-agentcore", region_name=region(), config=CONFIG)


def session_for(fund: str) -> str:
    """One runtime session per fund per day, so each fund's opinions group in the trace view."""
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", fund).strip("-").lower() or "board"
    return f"watchdog-opinion-{slug}-{datetime.now(UTC):%Y%m%d}".ljust(33, "0")[:100]


def remember(record: dict) -> dict:
    RECENT.append(record)
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
    except OSError as error:  # a read-only checkout must not break the opinion
        log.warning("could not append AgentCore invocation log: %s", error)
    return record


def recent(limit: int = 20) -> list[dict]:
    path = log_path()
    if path.exists():
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        return rows[-limit:]
    return list(RECENT)[-limit:]


def recalled_lessons(context: dict) -> list[str]:
    """Lessons from the watchdog's AgentCore Memory (D26). Any failure means no lessons, never an error."""
    from backend.app.watchdog import aws

    order = context.get("order", {})
    rules = ", ".join(context.get("rules", []))
    try:
        return aws.recall(f"{order.get('side', '')} {order.get('symbol', '')} blocked on {rules}: lessons about these limits")
    except Exception as error:  # noqa: BLE001 a failed recall must not break the review
        log.warning("AgentCore Memory recall failed, sending no lessons: %s", error)
        return []


def second_opinion(system: str, context: dict, model_cls, fund: str) -> dict | None:
    """The hosted agent's opinion validated against `model_cls`, or None to use the local path."""
    if not enabled():
        return None
    lessons = recalled_lessons(context)
    session = session_for(fund)
    payload = {"system": system, "context": context, "lessons": lessons, "schema": model_cls.model_json_schema(), "fund": fund}
    record = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "runtime_arn": runtime_arn(),
        "session_id": session,
        "fund": fund,
        "order": context.get("order"),
        "lessons_recalled": len(lessons),
    }
    trace_hex = f"{int(time.time()):08x}{secrets.token_hex(12)}"
    record["xray_trace_id"] = f"1-{trace_hex[:8]}-{trace_hex[8:]}"
    started = time.monotonic()
    try:
        response = client().invoke_agent_runtime(
            agentRuntimeArn=runtime_arn(),
            runtimeSessionId=session,
            traceParent=f"00-{trace_hex}-{secrets.token_hex(8)}-01",
            payload=json.dumps(payload, default=str).encode(),
            contentType="application/json",
            accept="application/json",
        )
        body = json.loads(response["response"].read())
        opinion = model_cls.model_validate(body["opinion"]).model_dump()
    except (BotoCoreError, ClientError, ValueError, KeyError, TypeError) as error:
        remember({**record, "ok": False, "error": f"{type(error).__name__}: {str(error)[:300]}", "ms": round((time.monotonic() - started) * 1000)})
        log.warning("AgentCore second opinion failed, using the local path: %s", error)
        return None
    trace = {
        "session_id": response.get("runtimeSessionId", session),
        "xray_trace_id": record["xray_trace_id"],
        "trace_url": f"https://{region()}.console.aws.amazon.com/cloudwatch/home?region={region()}#xray:traces/{record['xray_trace_id']}",
        "status": response.get("statusCode"),
        "model": body.get("model"),
        "attempts": body.get("attempts"),
        "usage": body.get("usage"),
        "ms": round((time.monotonic() - started) * 1000),
        "lessons_recalled": len(lessons),
    }
    remember({**record, "ok": True, **trace})
    return {**opinion, "source": f"agentcore:{runtime_arn().rsplit('/', 1)[-1]}:{body.get('model')}", "agentcore": trace}


def status() -> dict:
    arn = runtime_arn()
    links = {}
    if arn:
        runtime_id = arn.rsplit("/", 1)[-1]
        console = f"https://{region()}.console.aws.amazon.com"
        links = {
            "runtime": f"{console}/bedrock-agentcore/agents/{runtime_id}",
            "observability": f"{console}/cloudwatch/home?region={region()}#gen-ai-observability/agent-core",
            "logs": f"{console}/cloudwatch/home?region={region()}#logsV2:log-groups/log-group/$252Faws$252Fbedrock-agentcore$252Fruntimes$252F{runtime_id}-DEFAULT",
        }
    return {"enabled": enabled(), "runtime_arn": arn, "region": region(), "links": links, "invocations": recent()}
