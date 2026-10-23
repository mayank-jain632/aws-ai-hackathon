"""AgentCore Runtime second opinion (D28), against a fake boto3 client. Nothing here reaches AWS."""

import io
import json
import re
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from backend.app import agentcore
from backend.app.agents import base
from backend.app.watchdog import aws, opinion, store

ARN = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/aaron_watchdog_opinion-AbC123"
CONTEXT = {
    "client": "Calder Family Trust",
    "risk_band": "conservative",
    "order": {"side": "buy", "symbol": "MSFT", "notional": 40000.0, "client_order_id": "calder-msft-0001"},
    "verdict": "block",
    "rules": ["position_size", "order_size"],
    "watchdog_reason": "Buying $40,000 of MSFT would make it 40.0% of capital.",
    "recent_orders_from_same_agent_and_strategy": [],
    "strategy_rationale": "",
    "strategy_weights": {"MSFT": 0.25},
}
DESK = SimpleNamespace(manager=SimpleNamespace(fund_id="a" * 16, context=json.dumps({"mandate": {"name": "Calder Family Trust"}})))
OPINION = {"foul_play": False, "concern": "medium", "explanation": "A sizing mistake.", "suggested_fix": "Size to the 25% cap."}


class FakeRuntime:
    def __init__(self, body=None, error=None):
        self.calls, self.body, self.error = [], body, error

    def invoke_agent_runtime(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"runtimeSessionId": kwargs["runtimeSessionId"], "statusCode": 200, "response": io.BytesIO(json.dumps(self.body).encode())}


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTCORE_OPINION_ARN", ARN)
    monkeypatch.setenv("AGENTCORE_LOG", str(tmp_path / "invocations.jsonl"))
    monkeypatch.setattr(base, "mock_mode", lambda: False)
    monkeypatch.setattr(aws, "recall", lambda desk, query, top_k=5: ["Conservative clients get blocked on single orders over 10% of equity."])
    agentcore.RECENT.clear()

    def use(fake):
        monkeypatch.setattr(agentcore, "client", lambda: fake)
        return fake

    return use


def test_off_without_runtime_arn(monkeypatch):
    monkeypatch.delenv("AGENTCORE_OPINION_ARN", raising=False)
    monkeypatch.setattr(agentcore, "client", lambda: pytest.fail("must not call AWS"))
    assert agentcore.second_opinion("system", CONTEXT, opinion.SecondOpinion, DESK) is None


def test_invokes_runtime_with_lessons_schema_and_trace(hosted):
    fake = hosted(FakeRuntime({"opinion": OPINION, "model": "us.openai.gpt-5.6-luna", "attempts": 1, "usage": {"inputTokens": 700, "outputTokens": 400}}))
    result = agentcore.second_opinion(opinion.SYSTEM, CONTEXT, opinion.SecondOpinion, DESK)

    call = fake.calls[0]
    assert call["agentRuntimeArn"] == ARN
    assert len(call["runtimeSessionId"]) >= 33 and call["runtimeSessionId"].startswith("watchdog-opinion-fund-aaaaaaaaaaaaaaaa-")
    trace_hex = re.fullmatch(r"00-([0-9a-f]{32})-[0-9a-f]{16}-01", call["traceParent"]).group(1)
    payload = json.loads(call["payload"])
    assert payload["system"] == opinion.SYSTEM and payload["context"] == CONTEXT
    assert payload["lessons"] == ["Conservative clients get blocked on single orders over 10% of equity."]
    assert set(payload["schema"]["required"]) == {"foul_play", "concern", "explanation", "suggested_fix"}

    assert result["explanation"] == "A sizing mistake." and result["source"] == "agentcore:aaron_watchdog_opinion-AbC123:us.openai.gpt-5.6-luna"
    assert result["agentcore"]["xray_trace_id"] == f"1-{trace_hex[:8]}-{trace_hex[8:]}"
    logged = agentcore.recent()[-1]
    assert logged["ok"] and logged["xray_trace_id"] == result["agentcore"]["xray_trace_id"] and logged["lessons_recalled"] == 1


@pytest.mark.parametrize(
    "fake",
    [
        FakeRuntime({"opinion": {"foul_play": False}, "model": "m"}),
        FakeRuntime(error=ClientError({"Error": {"Code": "RuntimeClientError", "Message": "init timeout"}}, "InvokeAgentRuntime")),
    ],
)
def test_bad_reply_or_aws_error_falls_back(hosted, fake):
    hosted(fake)
    assert agentcore.second_opinion(opinion.SYSTEM, CONTEXT, opinion.SecondOpinion, DESK) is None
    assert agentcore.recent()[-1]["ok"] is False


def test_memory_failure_sends_no_lessons_instead_of_raising(hosted, monkeypatch):
    def broken(desk, query, top_k=5):
        raise RuntimeError("memory down")

    monkeypatch.setattr(aws, "recall", broken)
    fake = hosted(FakeRuntime({"opinion": OPINION, "model": "us.openai.gpt-5.6-luna"}))
    assert agentcore.second_opinion(opinion.SYSTEM, CONTEXT, opinion.SecondOpinion, DESK)["explanation"] == "A sizing mistake."
    assert json.loads(fake.calls[0]["payload"])["lessons"] == []


def test_status_route_is_people_only(hosted, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.main import app

    hosted(FakeRuntime({"opinion": OPINION, "model": "us.openai.gpt-5.6-luna"}))
    agentcore.second_opinion(opinion.SYSTEM, CONTEXT, opinion.SecondOpinion, DESK)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    with TestClient(app, base_url="http://localhost") as http:
        body = http.get("/api/agentcore").json()
        assert body["enabled"] and body["runtime_arn"] == ARN and body["invocations"][-1]["ok"]
        assert "aaron_watchdog_opinion-AbC123" in body["links"]["runtime"]
        assert http.get("/api/agentcore", headers={"x-agent-token": "TOKEN"}).status_code == 403


def test_opinion_prefers_runtime_then_local_bedrock(hosted, monkeypatch):
    monkeypatch.setattr(opinion, "context_for", lambda desk, entry: CONTEXT)
    monkeypatch.setattr(store, "fund_label", lambda desk: "Calder Family Trust")
    monkeypatch.setattr(base, "run_structured", lambda *a: opinion.SecondOpinion(**{**OPINION, "explanation": "local"}))

    hosted(FakeRuntime({"opinion": OPINION, "model": "us.openai.gpt-5.6-luna"}))
    assert opinion.second_opinion(DESK, {})["source"].startswith("agentcore:")

    hosted(FakeRuntime(error=ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "InvokeAgentRuntime")))
    local = opinion.second_opinion(DESK, {})
    assert local["explanation"] == "local" and local["source"].startswith("bedrock:")
