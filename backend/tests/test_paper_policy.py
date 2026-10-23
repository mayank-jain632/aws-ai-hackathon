import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app import paper
from backend.app.desk import Desk, PaperCriteria
from backend.app.funds import Mandate


def test_agents_freeze_criteria_under_mandate_before_testing(tmp_path):
    mandate = Mandate(name="Fund", mode="paper").model_dump()
    desk = Desk(SimpleNamespace(registry=tmp_path / "agents.json", context=json.dumps({"mandate": mandate})))
    criteria = PaperCriteria(min_sharpe=-5, min_excess_return=-1, max_order_notional=100, max_daily_orders=5, rationale="Choose low paper criteria before observing any evaluation result.")
    configured = desk.configure_paper_policy(criteria, "strategy-agent")
    assert configured["policy"]["max_position"] == mandate["max_position"] / 100
    assert configured["policy"]["max_drawdown"] == mandate["max_drawdown"] / 100
    assert configured["policy"]["trading_allowed"] == mandate["trading_allowed"]
    assert configured["origin"]["type"] == "agent" and desk.state["stop"] is False
    desk.state["tests"]["observed"] = {"verdict": "FAIL"}
    assert desk.configure_paper_policy(criteria, "strategy-agent")["policy_version"] == configured["policy_version"]
    with pytest.raises(ValueError, match="frozen"):
        desk.configure_paper_policy(criteria.model_copy(update={"min_sharpe": -10}), "strategy-agent")
    assert desk.state["policy_version"] == configured["policy_version"]
    desk.manager.context = json.dumps({"mandate": {**mandate, "mode": "historical"}})
    assert desk.configure_paper_policy(criteria, "strategy-agent")["policy_version"] == configured["policy_version"]


def test_current_alpaca_snapshot_preserves_feed_timestamp_and_staleness(monkeypatch):
    from backend.app.watchdog import market

    old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    calls = []
    def get(base, path, params=None):
        calls.append((base, path, params))
        return {"is_open": False, "timestamp": datetime.now(UTC).isoformat()} if path == "/v2/clock" else {"AAPL": {"latestTrade": {"p": 100, "t": old}, "latestQuote": {"ap": 101, "bp": 99, "t": old}}}
    monkeypatch.setattr(market, "get", get)
    result = paper.market_snapshot(["AAPL", "MSFT"])
    assert result["feed"] == "iex" and result["cache_used"] is False
    assert result["symbols"]["AAPL"]["trade_age_seconds"] >= 7200
    assert result["symbols"]["AAPL"]["latest_quote"]["t"] == old
    assert result["symbols"]["MSFT"]["missing"] is True
    assert all(path in {"/v2/clock", "/v2/stocks/snapshots"} for _, path, _ in calls)
    assert calls[0][2]["feed"] == "iex"
    monkeypatch.setattr(market, "get", lambda *a, **k: (_ for _ in ()).throw(ValueError("unavailable")))
    with pytest.raises(ValueError, match="unavailable"):
        paper.market_snapshot(["AAPL"])


@pytest.mark.parametrize("mode", ["paper", "historical"])
@pytest.mark.parametrize("source", ["human", "moderator"])
def test_paper_configuration_preserves_explicit_stop_and_does_not_rearm_after_clear(tmp_path, source, mode):
    mandate = Mandate(name="Standing paper fund", mode=mode).model_dump()
    assert mandate["mode"] == mode and mandate["trading_allowed"] and not mandate["approval_required"]
    manager = SimpleNamespace(registry=tmp_path / "agents.json", context=json.dumps({"mandate": mandate}))
    desk = Desk(manager)
    desk.state.update(stop=True, stop_source=source)
    desk.save()
    desk = Desk(manager)
    criteria = PaperCriteria(min_sharpe=-5, min_excess_return=-1, max_order_notional=100, max_daily_orders=5, rationale="Choose paper criteria before observing evaluation results.")
    desk.configure_paper_policy(criteria, "strategy")
    assert desk.state["stop"] is True and desk.state["stop_source"] == source
    desk.state.update(stop=False, stop_source="human")
    desk.configure_paper_policy(criteria.model_copy(update={"max_daily_orders": 6}), "strategy")
    assert desk.state["stop"] is False
    desk.set_policy(desk.policy())
    assert desk.state["stop"] is False


def test_legacy_explicit_stop_survives_old_automatic_policy_stop_source(tmp_path):
    mandate = Mandate(name="Standing paper fund").model_dump()
    manager = SimpleNamespace(registry=tmp_path / "agents.json", context=json.dumps({"mandate": mandate}))
    desk = Desk(manager)
    desk.state.update(stop=True, stop_source="human_policy")
    desk.state["events"] = [{"check": "human_stop", "result": {"stopped": True}}, {"check": "human_policy", "result": "Old automatic policy stop"}]
    desk.save()
    loaded = Desk(manager)
    loaded.authorize_initial_paper()
    assert loaded.state["stop"] is True and loaded.state["stop_source"] == "human"
