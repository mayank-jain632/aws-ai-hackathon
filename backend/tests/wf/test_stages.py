import pytest

from backend.app.agents import execution, strategy
from backend.app.wf import analysts
from backend.app.wf.config import WfConfig
from backend.app.wf.llm import StubLlm
from backend.app.wf.orders import to_decision_orders, weights_only_orders
from backend.app.wf.schemas import ExecutionPlan, OrderDraft, TickerPlan, TradePlan
from backend.tests.wf.conftest_helpers import UNIVERSE, FakePit, responder

CFG = WfConfig()
AS_OF = "2025-10-03"


def test_analyst_no_evidence_abstains_without_fixture_text():
    pit = FakePit(empty={"macro"})
    memos, _, abstained = analysts.run_research(
        pit, StubLlm(responder), AS_OF, UNIVERSE
    )
    assert abstained == ["macro"]
    m = next(m for m in memos if m.analyst == "macro")
    assert [v.confidence for v in m.views] == [0.0] * 3 and {
        v.stance for v in m.views
    } == {"neutral"}
    assert all("Abstained" in m.body for m in [m])


def test_failing_llm_abstains():
    def boom(*a):
        raise RuntimeError("down")

    memos, sources, abstained = analysts.run_research(
        FakePit(), StubLlm(boom), AS_OF, UNIVERSE
    )
    assert len(abstained) == 5 and sources == []
    assert all(v.confidence == 0 for m in memos for v in m.views)


def test_views_filtered_to_universe_and_evidence():
    memos, sources, abstained = analysts.run_research(
        FakePit(), StubLlm(responder), AS_OF, UNIVERSE
    )
    assert abstained == []
    for m in memos:
        assert [v.ticker for v in m.views] == ["AAPL"]
        assert m.views[0].sources == [f"{m.analyst}-1"]
    assert len(sources) == 5


def test_lookahead_raises():
    with pytest.raises(AssertionError):
        analysts.run_research(FakePit(late=True), StubLlm(responder), AS_OF, UNIVERSE)


class RotMasker:
    def encode(self, text):
        return text.replace("AAPL", "T01").replace("MSFT", "T02").replace("NVDA", "T03")

    def decode_ticker(self, code):
        return {"T01": "AAPL", "T02": "MSFT", "T03": "NVDA"}[code]


def test_masker_round_trip():
    seen = []

    def r(schema, system, user):
        seen.append(user)
        out = responder(schema, system, user)
        if schema == "_MemoDraft":
            out["views"][0]["ticker"] = "T01"
        return out

    memos, _, _ = analysts.run_research(
        FakePit(), StubLlm(r), AS_OF, UNIVERSE, RotMasker()
    )
    assert all("AAPL" not in u for u in seen)
    assert all(any("T01" in u for u in [x]) for x in seen)
    assert all(m.views[0].ticker == "AAPL" for m in memos)


def tp(t, w, stop=0.05, target=0.1):
    return TickerPlan(
        ticker=t,
        target_weight=w,
        stop_pct=stop,
        target_pct=target,
        rationale="r",
        changes_my_mind="c",
    )


def test_validate_plan_clamps_scales_dedupes():
    plan = TradePlan(
        decision_date=AS_OF,
        strategy_name="s",
        summary="",
        plans=[
            tp("AAPL", 0.9, stop=0.5, target=0.01),
            tp("AAPL", 0.1),
            tp("XXX", 0.1),
            tp("MSFT", 0.25),
            tp("NVDA", 0.25),
        ]
        + [tp("JPM", 0.25), tp("XOM", 0.25)],
    )
    out, notes = strategy.validate_plan(plan, CFG, list(CFG.universe))
    ws = {p.ticker: p.target_weight for p in out.plans}
    assert "XXX" not in ws and len(out.plans) == 5
    assert sum(ws.values()) <= 1 + 1e-9
    assert ws["AAPL"] == pytest.approx(0.25 / 1.25)
    a = out.plans[0]
    assert a.stop_pct == CFG.max_stop_pct and a.target_pct is None
    assert notes


def test_validate_execution_fills_defaults_and_clamps():
    plan = TradePlan(
        decision_date=AS_OF,
        strategy_name="s",
        summary="",
        plans=[tp("AAPL", 0.2), tp("MSFT", 0.2)],
    )
    ep = ExecutionPlan.model_construct(
        decision_date="x",
        orders=[
            OrderDraft.model_construct(
                ticker="AAPL",
                entry="limit",
                limit_offset_atr=None,
                skip_if_gap_pct=0.9,
                note="",
            )
        ],
        notes="",
    )
    out, notes = execution.validate_execution(ep, plan, AS_OF)
    d = {o.ticker: o for o in out.orders}
    assert d["MSFT"].entry == "market_open"
    assert d["AAPL"].limit_offset_atr == 0.5 and d["AAPL"].skip_if_gap_pct == 0.2
    assert out.decision_date == AS_OF and notes


def test_to_decision_orders_math():
    plan = TradePlan(
        decision_date=AS_OF,
        strategy_name="s",
        summary="",
        plans=[
            tp("AAPL", 0.2, stop=0.05, target=0.10),
            tp("MSFT", 0.1, stop=0.08, target=None),
            tp("NVDA", 0.1),
        ],
    )
    ep = ExecutionPlan(
        decision_date=AS_OF,
        orders=[
            OrderDraft(
                ticker="AAPL", entry="limit", limit_offset_atr=0.5, skip_if_gap_pct=0.03
            ),
            OrderDraft(ticker="NVDA", entry="skip"),
        ],
    )
    ctx = {
        "AAPL": {"last_close": 200.0, "atr14": 4.0},
        "MSFT": {"last_close": 400.0, "atr14": 8.0},
        "NVDA": {"last_close": 100.0},
    }
    cfg = WfConfig(universe=("AAPL", "MSFT", "NVDA", "JPM"))
    o = to_decision_orders(AS_OF, plan, ep, ctx, cfg, False)
    i = {x.ticker: x for x in o.intents}
    assert i["AAPL"].stop_price == 190.0 and i["AAPL"].target_price == 220.0
    assert i["AAPL"].limit_price == 198.0 and i["AAPL"].skip_if_gap_pct == 0.03
    assert (
        i["MSFT"].entry == "market_open"
        and i["MSFT"].stop_price == 368.0
        and i["MSFT"].target_price is None
    )
    assert i["NVDA"].entry == "skip" and i["NVDA"].stop_price is None
    assert i["JPM"].target_weight == 0.0 and i["JPM"].entry == "market_open"
    w = weights_only_orders(AS_OF, plan, cfg)
    assert (
        all(x.stop_price is None and x.entry == "market_open" for x in w.intents)
        and len(w.intents) == 4
    )
