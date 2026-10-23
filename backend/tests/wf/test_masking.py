import re

import pytest

from backend.app.wf import analysts
from backend.app.wf.config import WfConfig
from backend.app.wf.llm import StubLlm
from backend.app.wf.masking import MaskedPit, Masker
from backend.app.wf.pipeline import run_decision
from backend.app.wf.schemas import DecisionRecord
from backend.tests.wf.conftest_helpers import UNIVERSE, FakePit, src

CFG = WfConfig(universe=tuple(UNIVERSE))
AS_OF = "2025-10-03"
M = Masker(UNIVERSE)

PLANTED = (
    "Apple (AAPL) iPhone demand and Tim Cook; Microsoft Azure + Copilot; NVIDIA CUDA, "
    "Jensen Huang, CIK 0001045810, accession 0000320193-25-000079; Caterpillar and CAT shares"
)


class PlantedPit(FakePit):
    def evidence(self, analyst, as_of, universe):
        s = src(f"{analyst}-1", as_of).model_copy(
            update={"title": "Apple's iPhone beats", "excerpt": PLANTED}
        )
        return f"digest: {PLANTED}", [s]


def test_codes_are_deterministic_and_reversible():
    a, b = Masker(UNIVERSE), Masker(UNIVERSE)
    for t in UNIVERSE:
        code = a.encode(t)
        assert re.fullmatch(r"S\d\d", code) and code == b.encode(t)
        assert a.decode_ticker(code) == t
    assert len({a.encode(t) for t in UNIVERSE}) == len(UNIVERSE)
    assert Masker(UNIVERSE, seed=1).encode("AAPL") is not None


def test_code_order_is_not_alphabetical():
    full = Masker()
    codes = [full.encode(t) for t in sorted(full._code)]
    assert codes != sorted(codes)


def test_unknown_code_raises():
    with pytest.raises(KeyError):
        M.decode_ticker("S99")


def test_word_boundaries():
    out = M.encode("category and CAT and scatter; AAPL.O and PG&E")
    assert "category" in out and "scatter" in out
    assert "CAT" not in out.replace("category", "") and "AAPL" not in out
    assert "PG&E" in out or "S" in out  # PG as a whole word before '&' is masked, not an error


def test_longest_first_alias():
    m = Masker(UNIVERSE)
    assert m.encode("Procter & Gamble Company") == f"{m.encode('PG')} Company"
    assert m.encode("Exxon Mobil Corporation") == f"{m.encode('XOM')} Corporation"
    assert m.encode("JPMorgan Chase & Co.") == f"{m.encode('JPM')} & Co."


def test_ambiguous_aliases_only_match_capitalised():
    assert M.encode("open the windows to chase the tide") == "open the windows to chase the tide"
    assert "S" in M.encode("Windows and Azure")


def test_cik_and_accession_prefix_scrubbed():
    out = M.encode("filing 0000320193-25-000079 for CIK 320193 and 0001045810")
    assert "320193" not in out and "1045810" not in out and "-25-000079" in out


def test_planted_text_fully_masked():
    out = M.encode(PLANTED)
    assert M.leaks(out) == []
    for word in ("Apple", "iPhone", "Cook", "Microsoft", "Azure", "Nvidia", "CUDA", "Huang"):
        assert word.lower() not in out.lower()


def code_responder(schema, system, user):
    codes = re.search(r"Universe: ([^.\n]+?)\.", user)
    toks = [t.strip() for t in codes.group(1).split(",")] if codes else []
    if schema == "_MemoDraft":
        sid = next(ln[1 : ln.index("]")] for ln in user.splitlines() if ln.startswith("["))
        views = [{"ticker": t, "stance": "long", "confidence": 0.5, "note": "n", "sources": [sid]} for t in toks]
        return {"headline": "h", "body": "b", "views": views}
    if schema == "TradePlan":
        plans = [{"ticker": t, "target_weight": 0.2, "stop_pct": 0.05, "target_pct": 0.1,
                  "rationale": "r", "changes_my_mind": "c", "memo_sources": []} for t in toks]
        return {"decision_date": "x", "strategy_name": "s", "summary": "s", "plans": plans}
    return {"decision_date": "x", "orders": [
        {"ticker": t, "entry": "limit", "limit_offset_atr": 0.5} for t in toks]}


def test_run_research_protocol_and_no_leak_in_prompts():
    llm = StubLlm(code_responder)
    memos, _, abstained = analysts.run_research(PlantedPit(), llm, AS_OF, UNIVERSE, M)
    assert abstained == [] and len(memos) == 5
    assert all(v.ticker in UNIVERSE for m in memos for v in m.views)
    for _, _, user in llm.log:
        assert M.leaks(user) == [], user
        assert not any(t in user for t in UNIVERSE)


def test_run_decision_masked_roundtrip():
    llm = StubLlm(code_responder)
    rec = run_decision(PlantedPit(), llm, CFG, AS_OF, masker=M)
    assert isinstance(rec, DecisionRecord) and rec.masked
    assert {p.ticker for p in rec.plan.plans} == set(UNIVERSE)
    assert {i.ticker for i in rec.orders.intents} >= set(UNIVERSE)
    for schema, _, user in llm.log:
        assert not any(t in user for t in UNIVERSE), schema


class IdPit(PlantedPit):
    def evidence(self, analyst, as_of, universe):
        digest, srcs = super().evidence(analyst, as_of, universe)
        return digest, [s.model_copy(update={"id": f"px:AAPL:{as_of}:{analyst}"}) for s in srcs]


def test_masked_pit_scrubs_ticker_in_source_ids():
    llm = StubLlm(code_responder)
    pit = MaskedPit(IdPit(), M)
    _memos, sources, abstained = analysts.run_research(pit, llm, AS_OF, UNIVERSE, M)
    assert abstained == [] and sources
    assert all("AAPL" not in s.id for s in sources)
    assert pit.execution_context(AS_OF, UNIVERSE)["AAPL"]["last_close"] == 100.0
    for _, _, user in llm.log:
        assert "AAPL" not in user and M.leaks(user) == []
