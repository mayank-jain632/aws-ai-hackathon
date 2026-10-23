"""The watchdog on AWS: Bedrock Guardrail scans, AgentCore Memory, CloudWatch, EventBridge.

On when AWS credentials exist and WATCHDOG_AWS is not "0" (tests and MOCK_AGENTS=1 keep it
off). Resources come from `scripts/watchdog_aws.py` and are found by name at runtime, or by
WATCHDOG_GUARDRAIL_ID / WATCHDOG_MEMORY_ID when set. Names follow D25 (owner-named, Owner=aaron):

- Guardrail `aaron-watchdog`: prompt-attack filter plus a denied topic for evading trading
  limits. ApplyGuardrail screens agent-written strategy rationales and memos.
- AgentCore Memory `aaron_watchdog_lessons`: every block and near miss becomes an event; a
  semantic strategy distills them into firm-wide long-term records that agents in any fund
  can recall, without any fund reading another fund's files.
- CloudWatch namespace `Team4/Watchdog`: reviewed, blocked and near-miss counts by rule, and
  a FirmWideHalt gauge that the provisioned alarm watches.
- EventBridge source `team4.watchdog` on the default bus: blocks, moderator events and stop
  changes, routed by the provisioned rule into a CloudWatch Logs audit trail.

Metrics, events and memory writes go through one background thread so an order never waits
on AWS. A failed AWS call is logged and dropped; it never changes a verdict.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import queue
import re
import threading
from datetime import UTC, datetime

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from backend.app.agents import base

log = logging.getLogger("desk.watchdog.aws")

NAMESPACE = "Team4/Watchdog"
EVENT_SOURCE = "team4.watchdog"
GUARDRAIL_NAME = "aaron-watchdog"
MEMORY_NAME = "aaron_watchdog_lessons"
LESSONS_NAMESPACE = "/watchdog/lessons"
SCAN_CHARS = 20_000
CONFIG = Config(retries={"total_max_attempts": 3, "mode": "adaptive"}, connect_timeout=3, read_timeout=10)
AWS_ERRORS = (BotoCoreError, ClientError)


def enabled() -> bool:
    return os.getenv("WATCHDOG_AWS", "1") != "0" and not base.mock_mode()


@functools.cache
def client(service: str):
    import boto3

    return boto3.client(service, region_name=base.region(), config=CONFIG)


# --------------------------------------------------------------------- background sender

OUTBOX: queue.Queue = queue.Queue(maxsize=1000)
WORKER: list[threading.Thread] = []
WORKER_LOCK = threading.Lock()
FOUND: dict[str, object] = {}


def found(name: str, lookup):
    """Cache a resource lookup only once it succeeds, so provisioning later needs no restart."""
    if name not in FOUND:
        value = lookup()
        if value is None:
            return None
        FOUND[name] = value
    return FOUND[name]


def drain() -> None:
    while True:
        job = OUTBOX.get()
        try:
            job()
        except AWS_ERRORS as error:
            log.warning("watchdog AWS call failed: %s", error)
        finally:
            OUTBOX.task_done()


def send(job) -> None:
    """Queue an AWS write off the request path. Drops it when AWS is off or the queue is full."""
    if not enabled():
        return
    with WORKER_LOCK:
        if not WORKER:
            WORKER.append(threading.Thread(target=drain, name="watchdog-aws", daemon=True))
            WORKER[0].start()
    try:
        OUTBOX.put_nowait(job)
    except queue.Full:
        log.warning("watchdog AWS outbox full; dropping a write")


def metrics(data: list[dict]) -> None:
    send(lambda: client("cloudwatch").put_metric_data(Namespace=NAMESPACE, MetricData=data))


def event(detail_type: str, detail: dict) -> None:
    entry = {
        "Source": EVENT_SOURCE,
        "DetailType": detail_type,
        "Detail": json.dumps(detail, default=str),
        "EventBusName": "default",
    }
    send(lambda: client("events").put_events(Entries=[entry]))


def metric(name: str, value: float, **dimensions: str) -> dict:
    return {
        "MetricName": name,
        "Value": value,
        "Unit": "Count",
        "Dimensions": [{"Name": k, "Value": str(v)[:250]} for k, v in dimensions.items()],
    }


def publish_verdict(verdict, fund: str) -> None:
    data = [metric("OrdersReviewed", 1, Decision=verdict.decision, Risk=verdict.risk)]
    data += [metric("OrdersBlocked", 1, Rule=rule) for rule in verdict.blocked_by]
    data += [metric("NearMisses", 1, Rule=rule) for rule in verdict.near_misses]
    metrics(data)
    if verdict.decision == "block":
        order = verdict.order
        event(
            "Order blocked",
            {
                "fund": fund,
                "client": verdict.client,
                "risk": verdict.risk,
                "symbol": order.symbol,
                "side": order.side,
                "notional": order.notional,
                "rules": verdict.blocked_by,
                "reason": verdict.reason,
                "agent": order.agent_id,
            },
        )


def publish_moderator_event(moderator_event, fund: str) -> None:
    metrics([metric("ModeratorEvents", 1, Kind=moderator_event.kind, Severity=moderator_event.severity)])
    event("Moderator event", {"fund": fund, **moderator_event.model_dump()})


def publish_halt(state: dict) -> None:
    metrics([{**metric("FirmWideHalt", 1 if state["halted"] else 0), "Unit": "None"}])
    event("Firm-wide stop changed", {k: state.get(k) for k in ["halted", "reason", "by", "time"]})


# ------------------------------------------------------------------------- guardrail


def guardrail() -> tuple[str, str] | None:
    """(id, numbered version) of the watchdog guardrail, or None when it is not provisioned."""
    return found("guardrail", find_guardrail)


def find_guardrail() -> tuple[str, str] | None:
    if os.getenv("WATCHDOG_GUARDRAIL_ID"):
        return os.environ["WATCHDOG_GUARDRAIL_ID"], os.getenv("WATCHDOG_GUARDRAIL_VERSION", "1")
    bedrock = client("bedrock")
    found = [g for g in bedrock.list_guardrails().get("guardrails", []) if g["name"] == GUARDRAIL_NAME]
    if not found:
        return None
    versions = bedrock.list_guardrails(guardrailIdentifier=found[0]["id"]).get("guardrails", [])
    numbered = sorted(int(v["version"]) for v in versions if v["version"].isdigit())
    return (found[0]["id"], str(numbered[-1])) if numbered else None


def scan_text(text: str) -> dict | None:
    """Screen agent-written text for prompt injection and limit evasion. None when off."""
    if not enabled() or not text.strip():
        return None
    try:
        target = guardrail()
        if not target:
            return None
        response = client("bedrock-runtime").apply_guardrail(
            guardrailIdentifier=target[0],
            guardrailVersion=target[1],
            source="INPUT",
            content=[{"text": {"text": text[:SCAN_CHARS]}}],
            outputScope="INTERVENTIONS",
        )
    except AWS_ERRORS as error:
        log.warning("guardrail scan failed: %s", error)
        return None
    findings = []
    for assessment in response.get("assessments", []):
        for f in assessment.get("contentPolicy", {}).get("filters", []):
            if f.get("action") == "BLOCKED" or f.get("detected"):
                findings.append(f"{f['type'].lower().replace('_', ' ')} ({f.get('confidence', '').lower()} confidence)")
        for t in assessment.get("topicPolicy", {}).get("topics", []):
            if t.get("action") == "BLOCKED" or t.get("detected"):
                findings.append(f"denied topic {t['name']}")
    return {"intervened": response.get("action") == "GUARDRAIL_INTERVENED", "findings": findings}


# ------------------------------------------------------------------------- memory


def memory_id() -> str | None:
    return found("memory", find_memory)


def find_memory() -> str | None:
    if os.getenv("WATCHDOG_MEMORY_ID"):
        return os.environ["WATCHDOG_MEMORY_ID"]
    control = client("bedrock-agentcore-control")
    for page in control.get_paginator("list_memories").paginate():
        for m in page.get("memories", []):
            if m["id"].startswith(MEMORY_NAME) and m.get("status") == "ACTIVE":
                return m["id"]
    return None


def actor(fund: str) -> str:
    return "fund-" + (re.sub(r"[^a-zA-Z0-9-]+", "-", fund).strip("-").lower() or "board")


def remember(fund: str, text: str) -> None:
    """Append one watchdog finding to long-term memory, off the request path."""

    def write():
        mid = memory_id()
        if not mid:
            return
        client("bedrock-agentcore").create_event(
            memoryId=mid,
            actorId=actor(fund),
            sessionId="watchdog-" + datetime.now(UTC).strftime("%Y%m%d"),
            eventTimestamp=datetime.now(UTC),
            payload=[{"conversational": {"content": {"text": text[:8000]}, "role": "ASSISTANT"}}],
        )

    send(write)


def recall(query: str, top_k: int = 5) -> list[str]:
    """Firm-wide lessons the memory has distilled so far. Empty when off or not ready."""
    if not enabled():
        return []
    try:
        mid = memory_id()
        if not mid:
            return []
        response = client("bedrock-agentcore").retrieve_memory_records(
            memoryId=mid,
            namespace=LESSONS_NAMESPACE,
            searchCriteria={"searchQuery": query, "topK": top_k},
            maxResults=top_k,
        )
    except AWS_ERRORS as error:
        log.warning("memory recall failed: %s", error)
        return []
    return [r["content"]["text"] for r in response.get("memoryRecordSummaries", []) if r.get("content", {}).get("text")]
