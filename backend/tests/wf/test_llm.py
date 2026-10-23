import pytest
from pydantic import BaseModel

from backend.app.wf.llm import Llm, StructuredOutputError, cache_key


class Out(BaseModel):
    x: int


class FakeClient:
    def __init__(self, texts, stop="end_turn"):
        self.texts = list(texts)
        self.stop = stop
        self.calls = []

    def converse(self, **kw):
        self.calls.append(kw)
        text = self.texts.pop(0)
        return {
            "output": {"message": {"content": [{"text": text}]}},
            "stopReason": self.stop,
            "usage": {"inputTokens": 3, "outputTokens": 4},
        }


def mk(tmp_path, texts, **kw):
    c = FakeClient(texts)
    return Llm("m", client=c, cache_dir=tmp_path, **kw), c


def test_cache_hit_on_identical_request(tmp_path):
    llm, c = mk(tmp_path, ['{"x": 1}'])
    assert llm.structured("s", "u", Out).x == 1
    assert llm.structured("s", "u", Out).x == 1
    assert len(c.calls) == 1 and llm.cache_hits == 1 and llm.calls == 1


def test_key_varies():
    base = cache_key("m", "s", "u", 0.0, 4000, "S")
    assert base != cache_key("m2", "s", "u", 0.0, 4000, "S")
    assert base != cache_key("m", "s2", "u", 0.0, 4000, "S")
    assert base != cache_key("m", "s", "u", 0.5, 4000, "S")
    assert base != cache_key("m", "s", "u", None, 4000, "S")


def test_temperature_only_when_set(tmp_path):
    llm, c = mk(tmp_path, ['{"x": 1}'], temperature=None)
    llm.structured("s", "u", Out)
    assert "temperature" not in c.calls[0]["inferenceConfig"]
    llm2, c2 = mk(tmp_path / "b", ['{"x": 1}'], temperature=0.0)
    llm2.structured("s", "u", Out)
    assert c2.calls[0]["inferenceConfig"]["temperature"] == 0.0


def test_retry_then_success(tmp_path):
    llm, c = mk(tmp_path, ["not json", '{"x": 2}'])
    assert llm.structured("s", "u", Out).x == 2
    assert len(c.calls) == 2
    assert "did not validate" in c.calls[1]["messages"][-1]["content"][0]["text"]


def test_raises_after_second_failure(tmp_path):
    llm, _ = mk(tmp_path, ["nope", '{"x": "a"}'])
    with pytest.raises(StructuredOutputError):
        llm.structured("s", "u", Out)


def test_max_tokens_retry_doubles_capped(tmp_path):
    c = FakeClient(["{", '{"x": 1}'], stop="max_tokens")
    llm = Llm("m", client=c, cache_dir=tmp_path, max_tokens=6000)
    llm.complete("s", [{"role": "user", "content": [{"text": "u"}]}])
    assert [k["inferenceConfig"]["maxTokens"] for k in c.calls] == [6000, 8000]
