import copy
import json

from backend.app.agent import AgentManager
from backend.app.funds import FundStore, Mandate
from backend.app.presentation import fund_presentation


def test_display_snapshot_changes_only_requested_fund_metrics(tmp_path):
    store = FundStore(AgentManager(root=tmp_path), root=tmp_path)
    first = store.create(Mandate(name="Presentation", capital=100000), "local")
    other = store.create(Mandate(name="Other", capital=100000), "local")
    records = copy.deepcopy(store.records)
    desk = copy.deepcopy(store.runtime(first["id"]).desk.state)
    folder = tmp_path / "presentation"
    folder.mkdir()
    path = folder / "illustrative-fund-metrics.json"
    row = {
        "fund_id": first["id"],
        "starting_capital": 100000,
        "nav": 102000,
        "cash": 51000,
        "invested": 51000,
        "pnl": 2000,
        "return_pct": 2,
        "position_count": 4,
    }
    path.write_text(json.dumps({"enabled": True, "funds": [row]}))
    result = store.detail(first["id"])
    assert result["metrics"]["nav"] == 102000
    assert result["metrics"]["cash"] == 51000
    assert result["metrics"]["positions"] == 4
    assert result["metrics_source"] == "presentation_snapshot"
    assert store.detail(other["id"])["metrics"]["nav"] == 100000
    assert store.records == records
    assert store.runtime(first["id"]).desk.state == desk
    path.write_text(json.dumps({"enabled": False, "funds": [row]}))
    assert store.detail(first["id"])["metrics"]["nav"] == 100000


def test_bad_or_unbalanced_snapshot_is_ignored(tmp_path):
    folder = tmp_path / "presentation"
    folder.mkdir()
    path = folder / "illustrative-fund-metrics.json"
    path.write_text("not json")
    assert fund_presentation(tmp_path, "one", 100000) == {}
    row = {
        "fund_id": "one",
        "starting_capital": 100000,
        "nav": 102000,
        "cash": 51000,
        "invested": 50000,
        "pnl": 2000,
        "return_pct": 2,
        "position_count": 4,
    }
    path.write_text(json.dumps({"enabled": True, "funds": [row]}))
    assert fund_presentation(tmp_path, "one", 100000) == {}
