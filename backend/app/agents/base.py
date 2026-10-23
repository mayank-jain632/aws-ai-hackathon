"""Shared plumbing for the agents.

- `mock_mode()`: True when MOCK_AGENTS=1, or when boto3 finds no AWS credentials. In
  mock mode every agent serves the fixture (`data/fixtures/run_2023-01-01.json`).
- `run_structured(system_prompt, user_prompt, model_cls)`: one Bedrock Converse call
  (same shape as `backend/agent.py`, no temperature), asks for JSON matching the
  pydantic schema, parses the first JSON object in the reply, validates, retries once
  with the validation error fed back. Raises `StructuredOutputError` after that.
- `assert_no_lookahead(sources, cutoff)`: hard guard every analyst passes.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re

from pydantic import BaseModel, ValidationError

from backend.app.schema import Source

log = logging.getLogger("desk.agents")


DEFAULT_MODEL_ID = "us.openai.gpt-5.6-luna"


class StructuredOutputError(RuntimeError):
    pass


def model_id() -> str:
    return os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)


def region() -> str:
    return os.getenv("AWS_REGION", "us-east-1")


@functools.lru_cache(maxsize=1)
def mock_mode() -> bool:
    """Cached per process. MOCK_AGENTS=1 forces mock; missing credentials imply it."""
    if os.getenv("MOCK_AGENTS", "").lower() in {"1", "true", "yes", "on"}:
        log.info("MOCK_AGENTS set: agents serve fixture memos and weights")
        return True
    try:
        import boto3

        creds = boto3.Session().get_credentials()
    except Exception as exc:  # noqa: BLE001 deliberate fallback to fixture/mock
        log.warning("boto3 credential lookup failed (%s); falling back to mock agents", exc)
        return True
    if creds is None:
        log.warning("no AWS credentials found; falling back to mock agents (set MOCK_AGENTS=1 to silence)")
        return True
    return False


@functools.lru_cache(maxsize=1)
def _client():
    import boto3

    return boto3.client("bedrock-runtime", region_name=region())


def converse(system_prompt: str, messages: list[dict], max_tokens: int = 4000) -> str:
    """One Converse call. `messages` are Converse-shaped. No temperature (model rejects it)."""
    resp = _client().converse(
        modelId=model_id(),
        system=[{"text": system_prompt}],
        messages=messages,
        inferenceConfig={"maxTokens": max_tokens},
    )
    return "".join(part.get("text", "") for part in resp["output"]["message"]["content"])


def _extract_json(text: str) -> dict:
    """First {...} object in a reply, tolerating ``` fences and prose around it."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])


def _format_instructions(model_cls: type[BaseModel]) -> str:
    schema = json.dumps(model_cls.model_json_schema())
    return (
        "\n\nRespond with ONE JSON object and nothing else: no prose before or after, "
        "no markdown fence. It must validate against this JSON schema:\n" + schema
    )


def run_structured[T: BaseModel](system_prompt: str, user_prompt: str, model_cls: type[T]) -> T:
    """Ask for JSON matching `model_cls`, validate, retry once with the error. Sync."""
    messages = [{"role": "user", "content": [{"text": user_prompt + _format_instructions(model_cls)}]}]
    last_err: Exception | None = None
    for attempt in range(2):
        text = converse(system_prompt, messages)
        try:
            return model_cls.model_validate(_extract_json(text))
        except (ValueError, ValidationError) as exc:
            last_err = exc
            log.warning("structured output attempt %d failed: %s", attempt + 1, str(exc)[:300])
            messages = messages + [
                {"role": "assistant", "content": [{"text": text}]},
                {
                    "role": "user",
                    "content": [
                        {
                            "text": "That reply did not validate. Error:\n"
                            f"{str(exc)[:1500]}\n\nReply again with only the corrected JSON object."
                        }
                    ],
                },
            ]
    raise StructuredOutputError(f"model output did not validate after 2 attempts: {last_err}")


def assert_no_lookahead(sources: list[Source], cutoff: str) -> None:
    """Every Source an agent cites must be dated on or before the cutoff. Hard fail."""
    late = [(s.id, s.date) for s in sources if s.date > cutoff]
    assert not late, f"look-ahead: sources dated after {cutoff}: {late}"


def smoke_test() -> str:
    """One Converse call. Returns the reply text or raises with the boto error."""
    return converse("You are a smoke test.", [{"role": "user", "content": [{"text": "Reply with the single word: ready"}]}], max_tokens=20)


if __name__ == "__main__":
    print("model:", model_id(), "region:", region())
    print("reply:", smoke_test())
