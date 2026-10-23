"""Fund charts: recorded desk data plus same-engine recomputation. No network."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app import agent as runtime
from backend.app.agent import ROOT
from backend.app.charts import build_charts
from backend.app.desk import OrderInput, Policy, StrategyInput, desk_for
from backend.app.main import app
from backend.app.scores import sources as src

RECORD = {"name": "Growth fund", "capital": 250000}
WF_DIR = ROOT / "data" / "wf" / "prices"
TEAM_DIR = ROOT / "reports" / "wf" / "final" / "results_all" / "equity.csv"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_DIR", str(tmp_path / "watchdog-global"))
    monkeypatch.setattr(src, "WF_ROOT", tmp_path / "no-walk-forward")


def make(tmp_path):
    manager = SimpleNamespace(registry=tmp_path / "agents.json", paused=False, agents={})
    desk = desk_for(manager)
    desk.set_policy(
        Policy(
            universe=["AAPL", "MSFT"], max_position=0.7, max_drawdown=0.5, min_sharpe=-100,
            min_excess_return=-1, max_order_notional=1000, max_daily_orders=10, trading_allowed=True,
        )
    )
    return manager, desk


def run_test(desk, cutoff, end):
    sid = desk.register(
        StrategyInput(
            name="Pair", weights={"AAPL": 0.5, "MSFT": 0.5}, cutoff=cutoff, end=end,
            rationale="Equal split of two large caps for a chart test.", memo_paths=["macro.md"], changes_my_mind="n/a",
        ),
        "strategist",
    )["id"]
    desk.evaluate(sid)
    return sid


def check_shape(charts, first_value):
    bt = charts.backtest
    n = len(bt.dates)
    assert 2 < n <= 320
    for arr in (bt.portfolio, bt.benchmark, bt.drawdown, bt.benchmark_drawdown, bt.equal_weight):
        assert len(arr) == n
    assert bt.portfolio[0] == pytest.approx(first_value)
    assert bt.benchmark[0] == pytest.approx(first_value)
    assert max(bt.drawdown) <= 0 and max(bt.benchmark_drawdown) <= 0
    assert min(bt.drawdown) == pytest.approx(bt.metrics.portfolio.max_drawdown, abs=1e-3)
    months = [m.month for m in bt.monthly]
    assert months == sorted(months) and len(set(months)) == len(months)
    assert bt.consistent and bt.note
    assert bt.thresholds.max_position == 0.7 and bt.thresholds.max_drawdown == 0.5


@pytest.mark.skipif(not WF_DIR.is_dir(), reason="data/wf absent")
def test_wf_strategy_recomputes_consistently(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_ENGINE", "wf")
    manager, desk = make(tmp_path)
    sid = run_test(desk, "2025-10-06", "2026-06-30")
    charts = build_charts("f1", RECORD, manager)
    assert charts.strategy.id == sid and charts.strategy.engine == "wf"
    assert charts.strategy.verdict in ("PASS", "FAIL")
    assert [s.id for s in charts.strategies] == [sid]
    assert charts.allocation.weights == {"AAPL": 0.5, "MSFT": 0.5}
    check_shape(charts, 250000)
    assert charts.backtest.checks is not None


def test_legacy_strategy_recomputes_consistently(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_ENGINE", "legacy")
    manager, desk = make(tmp_path)
    sid = run_test(desk, "2024-06-01", "2025-06-30")
    charts = build_charts("f1", RECORD, manager, sid)
    assert charts.strategy.engine == "legacy"
    check_shape(charts, 250000)


def test_no_strategy_returns_nulls_and_notes(tmp_path):
    manager, _ = make(tmp_path)
    charts = build_charts("f1", RECORD, manager)
    assert charts.strategy is None and charts.backtest is None and charts.allocation is None
    assert charts.strategies == [] and charts.orders == [] and charts.team is None
    assert any("No strategy" in n for n in charts.notes) and any("orders" in n for n in charts.notes)


def test_untested_strategy_gives_null_backtest(tmp_path):
    manager, desk = make(tmp_path)
    sid = desk.register(
        StrategyInput(
            name="Pair", weights={"AAPL": 0.5, "MSFT": 0.5}, cutoff="2024-06-01", end="2025-06-30",
            rationale="Equal split of two large caps for a chart test.", memo_paths=["macro.md"], changes_my_mind="n/a",
        ),
        "strategist",
    )["id"]
    charts = build_charts("f1", RECORD, manager, sid)
    assert charts.strategy.verdict is None and charts.backtest is None
    assert any("no recorded test" in n for n in charts.notes)


def test_recompute_failure_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_ENGINE", "legacy")
    manager, desk = make(tmp_path)
    sid = run_test(desk, "2024-06-01", "2025-06-30")
    desk.state["strategies"][sid]["end"] = "2031-01-01"
    charts = build_charts("f1", RECORD, manager, sid)
    assert charts.backtest is None and any("could not be recomputed" in n for n in charts.notes)


def test_orders_are_mapped_oldest_first(tmp_path):
    manager, desk = make(tmp_path)
    for oid, time in (("order-bbbbbb", "2026-01-02T00:00:00"), ("order-aaaaaa", "2026-01-01T00:00:00")):
        body = OrderInput(strategy_id="s", symbol="AAPL", side="buy", notional=5, client_order_id=oid)
        desk.state["orders"][oid] = {**body.model_dump(), "time": time, "status": "filled"}
    charts = build_charts("f1", RECORD, manager)
    assert [o.client_order_id for o in charts.orders] == ["order-aaaaaa", "order-bbbbbb"]
    assert charts.orders[0].status == "filled" and charts.orders[0].notional == 5


@pytest.mark.skipif(not TEAM_DIR.is_file(), reason="reports/wf/final absent")
def test_team_series_scaled_to_capital(tmp_path, monkeypatch):
    monkeypatch.setattr(src, "WF_ROOT", ROOT / "reports" / "wf")
    manager, _ = make(tmp_path)
    team = build_charts("f1", RECORD, manager).team
    assert team is not None and team.series["pipeline"][0] == pytest.approx(250000)
    assert set(team.series) == {"pipeline", "equal_weight_buy_hold", "spy_buy_hold"}
    assert all(len(v) == len(team.dates) for v in team.series.values())


def test_route_auth_and_unknown_strategy(tmp_path, monkeypatch):
    from backend.app import funds

    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    monkeypatch.setattr(runtime, "LOCAL", tmp_path / ".local/agent")
    monkeypatch.setattr(funds, "ROOT", tmp_path)
    monkeypatch.setenv("WATCHDOG_INTERVAL_SECONDS", "0")
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    with TestClient(app, base_url="http://localhost") as http:
        ok = http.get("/api/funds/general/charts")
        assert ok.status_code == 200 and ok.json()["backtest"] is None
        assert http.get("/api/funds/nope/charts").status_code == 404
        assert http.get("/api/funds/general/charts?strategy_id=nope").status_code == 404
        token = app.state.manager.token
        assert http.get("/api/funds/general/charts", headers={"X-Agent-Token": token, "X-Agent-ID": "dexter"}).status_code == 403
