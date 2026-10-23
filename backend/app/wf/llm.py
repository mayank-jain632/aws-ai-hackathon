"""Strict Bedrock Converse wrapper for the walk-forward backtest.

No mock mode, no fixture fallback. Every reply is cached on disk (raw text, stop reason,
usage) keyed by the full request, so a re-run replays byte-identically and costs nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from backend.app.agents.base import (
    StructuredOutputError,
    _extract_json,
    _format_instructions,
)

log = logging.getLogger("wf.llm")

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "wf" / "llm"
MAX_TOKENS_CAP = 8000
REGION = "us-east-1"

__all__ = ["CACHE_DIR", "Llm", "StructuredOutputError", "StubLlm"]


def make_client(region: str = REGION):
    import boto3
    from botocore.config import Config

    cfg = Config(retries={"max_attempts": 10, "mode": "adaptive"}, read_timeout=300, max_pool_connections=64)
    return boto3.client("bedrock-runtime", region_name=region, config=cfg)


def cache_key(
    model_id: str,
    system: str,
    user: str,
    temperature: float | None,
    max_tokens: int,
    schema: str,
) -> str:
    payload = json.dumps(
        [model_id, system, user, temperature, max_tokens, schema], ensure_ascii=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class Llm:
    """Thread-safe cached Converse client. `temperature=None` omits the parameter."""

    def __init__(
        self,
        model_id: str,
        temperature: float | None = 0.0,
        max_tokens: int = 4000,
        client=None,
        cache_dir: Path | None = CACHE_DIR,
    ) -> None:
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = client
        self.cache_dir = cache_dir
        self._lock = threading.Lock()
        self.calls = 0
        self.cache_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def _get_client(self):
        with self._lock:
            if self._client is None:
                self._client = make_client()
            return self._client

    def _path(self, key: str) -> Path | None:
        return (
            None
            if self.cache_dir is None
            else Path(self.cache_dir) / f"{key[:2]}" / f"{key}.json"
        )

    def _read_cache(self, key: str) -> dict | None:
        path = self._path(key)
        if path is None or not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            log.warning("unreadable cache entry %s, ignoring", path)
            return None

    def _write_cache(self, key: str, entry: dict) -> None:
        path = self._path(key)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(entry))
        tmp.replace(path)

    def _call(
        self, system: str, messages: list[dict], max_tokens: int, schema: str
    ) -> dict:
        key = cache_key(
            self.model_id,
            system,
            json.dumps(messages, ensure_ascii=False),
            self.temperature,
            max_tokens,
            schema,
        )
        hit = self._read_cache(key)
        if hit is not None:
            with self._lock:
                self.cache_hits += 1
            return hit
        inference: dict = {"maxTokens": max_tokens}
        if self.temperature is not None:
            inference["temperature"] = self.temperature
        resp = self._get_client().converse(
            modelId=self.model_id,
            system=[{"text": system}],
            messages=messages,
            inferenceConfig=inference,
        )
        text = "".join(p.get("text", "") for p in resp["output"]["message"]["content"])
        usage = resp.get("usage", {})
        entry = {"text": text, "stop_reason": resp.get("stopReason"), "usage": usage}
        self._write_cache(key, entry)
        with self._lock:
            self.calls += 1
            self.input_tokens += int(usage.get("inputTokens", 0))
            self.output_tokens += int(usage.get("outputTokens", 0))
        return entry

    def complete(self, system: str, messages: list[dict], schema: str = "") -> str:
        """One call; if the reply was cut off at max_tokens, retry once with a larger budget."""
        budget = self.max_tokens
        entry = self._call(system, messages, budget, schema)
        if entry["stop_reason"] == "max_tokens" and budget < MAX_TOKENS_CAP:
            entry = self._call(
                system, messages, min(budget * 2, MAX_TOKENS_CAP), schema
            )
        return entry["text"]

    def structured[T: BaseModel](self, system: str, user: str, model_cls: type[T]) -> T:
        messages = [
            {
                "role": "user",
                "content": [{"text": user + _format_instructions(model_cls)}],
            }
        ]
        last: Exception | None = None
        for attempt in range(2):
            text = self.complete(system, messages, model_cls.__name__)
            try:
                return model_cls.model_validate(_extract_json(text))
            except (ValueError, ValidationError) as exc:
                last = exc
                log.warning(
                    "structured %s attempt %d failed: %s",
                    model_cls.__name__,
                    attempt + 1,
                    str(exc)[:200],
                )
                messages = [
                    *messages,
                    {"role": "assistant", "content": [{"text": text}]},
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": f"That reply did not validate. Error:\n{str(exc)[:1500]}\n\n"
                                "Reply again with only the corrected JSON object."
                            }
                        ],
                    },
                ]
        raise StructuredOutputError(
            f"{model_cls.__name__} did not validate after 2 attempts: {last}"
        )

    def stats(self) -> dict:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class StubLlm:
    """Deterministic fake. `responder(schema_name, system, user)` returns a dict/JSON str/BaseModel,
    or raises to simulate failure."""

    def __init__(
        self, responder: Callable[[str, str, str], object], model_id: str = "stub"
    ) -> None:
        self.responder = responder
        self.model_id = model_id
        self._lock = threading.Lock()
        self.calls = 0
        self.cache_hits = 0
        self.log: list[tuple[str, str, str]] = []

    def structured[T: BaseModel](self, system: str, user: str, model_cls: type[T]) -> T:
        with self._lock:
            self.calls += 1
            self.log.append((model_cls.__name__, system, user))
        out = self.responder(model_cls.__name__, system, user)
        if isinstance(out, model_cls):
            return out
        if isinstance(out, BaseModel):
            out = out.model_dump()
        if isinstance(out, str):
            out = json.loads(out)
        return model_cls.model_validate(out)

    def stats(self) -> dict:
        return {"calls": self.calls, "cache_hits": self.cache_hits}
