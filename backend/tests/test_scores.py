"""Scores and reasoning view (D23): honest rings, recorded reasoning, read-only."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app import agent as runtime
from backend.app.desk import Policy, ReviewInput, StrategyInput, desk_for
from backend.app.funds import Mandate
from backend.app.main import app
from backend.app.scores import build_scorecard
from backend.app.scores import sources as src
from backend.app.watchdog import feedback

MEMO = """# Macro memo
CPI cooled on 2022-12-13 https://fred.stlouisfed.org/series/CPIAUCSL
Apple 10-K filed 2022-10-28 https://www.sec.gov/Archives/edgar/data/320193/aapl-10k.htm
"""


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_DIR", str(tmp_path / "watchdog-global"))
    monkeypatch.setattr(src, "WF_ROOT", tmp_path / "no-walk-forward")


def empty_fund(tmp_path):
    return SimpleNamespace(registry=tmp_path / "agents.json", paused=False, agents={})


def evaluated_fund(tmp_path):
    manager = empty_fund(tmp_path)
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "macro.md").write_text(MEMO)
    desk = desk_for(manager)
    desk.set_policy(
        Policy(
            universe=["AAPL", "MSFT"],
            max_position=0.7,
            max_drawdown=0.5,
            min_sharpe=-100,
            min_excess_return=-1,
            max_order_notional=1000,
            max_daily_orders=10,
            trading_allowed=True,
        )
    )
    sid = desk.register(
        StrategyInput(
            name="Quality tilt",
            weights={"AAPL": 0.5, "MSFT": 0.5},
            cutoff="2023-01-01",
            end="2023-06-30",
            rationale="Both names carry the strongest cited fundamentals.",
            memo_paths=["macro.md", "missing.md"],
            changes_my_mind="Cut if CPI re-accelerates.",
        ),
        "strategist",
    )["id"]
    desk.review(
        ReviewInput(strategy_id=sid, verdict="APPROVE", critique="Checked concentration and that every input predates the cutoff."),
        "reviewer",
    )
    desk.evaluate(sid)
    return manager, desk, sid


def by_key(card):
    return {s.key: s for s in card.scores}


def test_rings_without_data_say_not_produced_and_name_the_owner(tmp_path):
    card = build_scorecard("f1", Mandate(name="Empty fund").model_dump(), empty_fund(tmp_path))
    assert len(card.scores) == 8
    for score in card.scores:
        assert score.status == "not_produced"
        assert score.value is None and score.raw == "" and score.formula == ""
        assert score.owner and score.missing
    statuses = {s.id: s.status for s in card.sources}
    assert statuses["desk"] == "empty"
    assert statuses["walk_forward"] == "not_on_main"


def test_scored_rings_show_raw_formula_source_and_recorded_reasoning(tmp_path):
    manager, desk, sid = evaluated_fund(tmp_path)
    mandate = Mandate(name="Growth", universe=["AAPL", "MSFT", "NVDA"], max_position=40).model_dump()
    rings = by_key(build_scorecard("f1", mandate, manager))

    backtest = rings["backtest"]
    test = desk.state["tests"][sid]
    assert backtest.status == "scored"
    assert backtest.value == 100 * sum(test["checks"].values()) / 4
    assert backtest.raw.startswith(test["verdict"]) and "÷ 4" in backtest.formula
    assert backtest.source.location.endswith("desk.json")
    assert backtest.factors[0].reasoning == test["limitations"]

    fit = rings["mandate_fit"]
    position = next(f for f in fit.factors if f.key == "position")
    assert position.status == "fail" and "cap 40%" in position.value
    assert fit.value == 100 * sum(f.status == "pass" for f in fit.factors if f.weight) / sum(1 for f in fit.factors if f.weight)

    strategy = rings["strategy"]
    review = next(f for f in strategy.factors if f.key == "review")
    assert review.status == "pass" and review.reasoning.startswith("Checked concentration")
    assert review.agents[0].id == "reviewer"
    memos = next(f for f in strategy.factors if f.key == "memos")
    assert memos.status == "fail" and memos.value == "1 of 2 found"
    kinds = {c.kind: c for c in memos.provenance.citations}
    assert kinds["fred"].date == "2022-12-13" and kinds["sec"].url.startswith("https://www.sec.gov/")

    for key in ("confidence", "significance", "execution", "watchdog", "sensitivity"):
        assert rings[key].status == "not_produced", key


def test_orders_and_watchdog_verdicts_feed_execution_and_gate(tmp_path):
    manager, desk, sid = evaluated_fund(tmp_path)
    desk.state["orders"]["order-1"] = {
        "strategy_id": sid, "symbol": "AAPL", "side": "buy", "notional": 500.0, "client_order_id": "order-1",
        "time": "2026-10-23T18:00:00+00:00", "status": "filled", "broker_id": "b-1", "filled_qty": "2", "filled_avg_price": "250",
    }
    desk.state["orders"]["order-2"] = {
        "strategy_id": sid, "symbol": "MSFT", "side": "buy", "notional": 500.0, "client_order_id": "order-2",
        "time": "2026-10-23T18:01:00+00:00", "status": "unknown", "reason": "Alpaca timed out",
    }
    for kind in ("approve", "block"):
        feedback.append(desk, {"kind": kind, "rules": [] if kind == "approve" else ["position_size"], "reason": f"{kind} reason", "symbol": "AAPL", "side": "buy", "notional": 500.0, "strategy_id": sid})
    rings = by_key(build_scorecard("f1", Mandate(name="Growth").model_dump(), manager))
    assert rings["execution"].value == 50.0 and rings["execution"].raw == "1 of 2 paper orders filled at Alpaca"
    assert rings["watchdog"].value == 50.0
    blocked = next(f for f in rings["watchdog"].factors if f.status == "fail")
    assert blocked.reasoning == "block reason" and "position_size" in blocked.value


def write_walk_forward(root):
    """Minimal fixture in the walk-forward run's shapes. Fixture numbers, not results."""
    run = root / "final"
    (run / "results_test").mkdir(parents=True)
    (run / "decisions").mkdir()
    (run / "manifest.json").write_text(json.dumps({"run_id": "final", "created": "2026-10-23T18:00:00+00:00"}))
    sig = {"excess_weekly_mean": 0.001, "excess_lo": -0.001, "excess_hi": 0.003, "p_le_zero": 0.2, "sharpe_diff": 0.1, "sharpe_diff_lo": -0.1, "sharpe_diff_hi": 0.3}
    (run / "results_test" / "stats.json").write_text(json.dumps({"window": "test", "decisions": 3, "significance": {"vs_spy_buy_hold": sig}, "research_ic": {}}))
    (run / "results_test" / "attribution.csv").write_text(",total_return,costs,n_fills,n_skipped\npipeline,0.01,10,3,1\n")
    (run / "decisions" / "2026-10-16.json").write_text(json.dumps({
        "decision_date": "2026-10-16",
        "memos": [{"analyst": "macro", "views": [{"ticker": "AAPL", "stance": "long", "confidence": 0.8, "note": "Rates easing.", "sources": ["fred:DGS10"]}]}],
        "sources": [{"id": "fred:DGS10", "kind": "fred", "title": "10y yield", "date": "2026-10-16", "url": None, "excerpt": "4.1%"}],
        "plan": {"strategy_name": "Fixture", "plans": [{"ticker": "AAPL", "target_weight": 0.5, "conviction": 0.6, "rationale": "Macro tailwind.", "changes_my_mind": "Yield above 5%.", "memo_sources": ["fred:DGS10"]}]},
    }))
    (root / "audit_clean").mkdir()
    (root / "audit_clean" / "audit.json").write_text(json.dumps({"n_dates": 3, "rows": [
        {"series": "macro", "horizon": "1w", "n_dates": 3, "named_ic": 0.1, "masked_ic": 0.1, "diff": 0.0, "ci_lo": -0.1, "ci_hi": 0.1, "verdict": "no detectable memory effect"},
        {"series": "strategy_weight", "horizon": "1w", "n_dates": 3, "named_ic": 0.1, "masked_ic": 0.2, "diff": -0.1, "ci_lo": -0.2, "ci_hi": -0.01, "verdict": "masked better"},
    ]}))


def test_walk_forward_fills_empty_rings_as_firm_wide(tmp_path):
    write_walk_forward(tmp_path / "wf")
    rings = by_key(build_scorecard("f1", Mandate(name="Empty").model_dump(), empty_fund(tmp_path), wf_root=tmp_path / "wf"))
    assert rings["confidence"].scope == "firm" and rings["confidence"].value == 60.0
    plan = rings["confidence"].factors[0]
    assert plan.reasoning.startswith("Macro tailwind.") and plan.provenance.citations[0].kind == "fred"
    assert rings["significance"].value == 80.0
    assert rings["execution"].value == 75.0
    assert rings["sensitivity"].value == 50.0
    assert rings["mandate_fit"].status == "not_produced"


def test_building_the_card_writes_nothing(tmp_path):
    manager, _, _ = evaluated_fund(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    build_scorecard("f1", Mandate(name="Growth").model_dump(), manager)
    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_route_is_human_only_and_scoped_to_a_fund(tmp_path, monkeypatch):
    from backend.app import funds

    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    monkeypatch.setattr(runtime, "LOCAL", tmp_path / ".local/agent")
    monkeypatch.setattr(funds, "ROOT", tmp_path)
    monkeypatch.setenv("WATCHDOG_INTERVAL_SECONDS", "0")
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    with TestClient(app, base_url="http://localhost") as http:
        card = http.get("/api/funds/general/scores")
        assert card.status_code == 200
        assert {s["key"] for s in card.json()["scores"]} >= {"mandate_fit", "backtest", "watchdog", "sensitivity"}
        assert http.get("/api/funds/nope/scores").status_code == 404
        assert http.get("/api/funds/general/scores?strategy_id=nope").status_code == 404
        token = app.state.manager.token
        assert http.get("/api/funds/general/scores", headers={"X-Agent-Token": token, "X-Agent-ID": "dexter"}).status_code == 403


def test_synthesis_records_fill_fund_rings_when_present(tmp_path):
    """synthesis.json in the shapes on branch chaithu/synthesis-layer. Fixture numbers."""
    manager, _, sid = evaluated_fund(tmp_path)
    runs = [
        {"id": "s1", "time": "2026-10-23T18:00:00+00:00", "kind": "synthesis", "agent": "strategist", "strategy_id": sid,
         "memos": ["macro", "fundamentals"], "memo_paths": ["macro.md"], "model_used": False, "model_note": "",
         "seed": {"conviction": {"AAPL": 1.2, "MSFT": -0.4}, "seed_weights": {"AAPL": 0.7, "MSFT": 0.3}, "dropped": {"NVDA": "net avoid -0.60"}, "clamped": []}},
        {"id": "s2", "time": "2026-10-23T18:05:00+00:00", "kind": "significance", "strategy_id": sid, "horizon_days": 182, "n_windows": 10,
         "hit_rate_vs_spy": 0.7, "hit_rate_vs_equal": 0.6, "mean_excess_vs_spy": 0.02, "mean_excess_vs_equal": 0.01, "t_stat_vs_spy": 2.0,
         "p_value_vs_spy": 0.04, "ci95_excess_vs_spy": [0.001, 0.04], "worst_drawdown": -0.12, "limitations": "Overlapping windows."},
    ]
    (tmp_path / "synthesis.json").write_text(json.dumps(runs))
    rings = by_key(build_scorecard("f1", Mandate(name="Growth").model_dump(), manager))
    confidence = rings["confidence"]
    assert confidence.scope == "fund" and confidence.value == pytest.approx(50 * (1 + (0.5 * 1.2 + 0.5 * -0.4) / 2), abs=0.05)
    assert {f.label for f in confidence.factors} >= {"AAPL", "MSFT", "NVDA (dropped)"}
    from backend.app.synthesis.significance import walk_forward

    real = walk_forward(sid, {"AAPL": 0.5, "MSFT": 0.5}, horizon_days=182)
    one_sided = real.p_value_vs_spy / 2 if real.t_stat_vs_spy > 0 else 1 - real.p_value_vs_spy / 2
    sig = rings["significance"]
    assert sig.scope == "fund" and sig.value == pytest.approx(100 * (1 - one_sided), abs=0.05)
    assert f"t = {real.t_stat_vs_spy:.2f}" in sig.raw and "95% CI" in sig.raw and "hit rate" in sig.raw
    lo, hi = real.ci95_excess_vs_spy
    assert sig.raw.endswith("includes zero" if lo <= 0 <= hi else "excludes zero")
    assert "s2" in sig.factors[0].provenance.record and "not recorded" in sig.factors[0].provenance.record
    beat = sum(w.excess_vs_spy > 0 for w in real.windows)
    assert rings["sensitivity"].value == pytest.approx(round(100 * beat / real.n_windows, 1))
    assert len(rings["sensitivity"].factors) == real.n_windows
    assert next(s for s in build_scorecard("f1", Mandate(name="Growth").model_dump(), manager).sources if s.id == "synthesis").status == "present"


def test_strategy_without_a_synthesis_record_has_no_significance(tmp_path):
    manager, _, _ = evaluated_fund(tmp_path)
    rings = by_key(build_scorecard("f1", Mandate(name="Growth").model_dump(), manager))
    assert rings["significance"].status == "not_produced"
    assert "synthesis layer has no record" in rings["significance"].missing
    assert "Lane 2b" in rings["significance"].owner and rings["significance"].value is None


def test_plan_files_give_context_before_any_strategy(tmp_path):
    manager = empty_fund(tmp_path)
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "fund-plan.md").write_text("# Plan\nObjective: balanced growth under a 15% drawdown cap.\n")
    fit = by_key(build_scorecard("f1", Mandate(name="Planned").model_dump(), manager))["mandate_fit"]
    assert fit.status == "not_produced" and fit.value is None
    assert fit.factors[0].reasoning.startswith("# Plan") and fit.factors[0].weight is None


def test_truncated_write_file_activity_still_credits_the_author():
    long_call = json.dumps({"path": "macro.md", "content": "x" * 20000})[:12000]
    agents = {"r1": {"id": "r1", "name": "Macro researcher", "role": "research", "activity": [{"kind": "tool", "label": "write_file", "detail": long_call, "time": "t"}]}}
    assert src.file_authors(src.tool_calls(agents)) == {"macro.md": ["r1"]}


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    """Hosted login and fund sharing, as in test_sharing.py."""
    import backend.app.funds as funds_module
    from backend.app import main
    from backend.app.agent import AgentManager

    monkeypatch.setenv("APP_ACCESS_PASSWORD", "test-signing-secret")
    monkeypatch.setenv("APP_DEMO_ACCOUNTS", json.dumps({"owner@example.com": "demo-test-pass", "peer@example.com": "peer-test-pass"}))
    monkeypatch.delenv("APP_ORIGIN_TOKEN", raising=False)
    monkeypatch.setenv("WATCHDOG_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(funds_module, "ROOT", tmp_path)
    monkeypatch.setattr(main, "AgentManager", lambda: AgentManager(root=tmp_path / ".local"))
    with TestClient(main.app, base_url="https://localhost") as client:
        yield client


def login(client, email, password):
    assert client.post("/login", data={"email": email, "password": password}, follow_redirects=False).status_code == 303


def test_non_member_gets_the_same_refusal_as_other_fund_routes(hosted):
    login(hosted, "owner@example.com", "demo-test-pass")
    fund = hosted.post("/api/funds", json={"name": "Private fund"}).json()["id"]
    assert hosted.get(f"/api/funds/{fund}/scores").status_code == 200
    login(hosted, "peer@example.com", "peer-test-pass")
    scores, agents = hosted.get(f"/api/funds/{fund}/scores"), hosted.get(f"/api/funds/{fund}/agents")
    assert (scores.status_code, scores.text) == (agents.status_code, agents.text) == (403, "Fund access denied")
    login(hosted, "owner@example.com", "demo-test-pass")
    assert hosted.post(f"/api/funds/{fund}/members", json={"email": "peer@example.com"}).status_code == 200
    login(hosted, "peer@example.com", "peer-test-pass")
    assert hosted.get(f"/api/funds/{fund}/scores").status_code == 200
