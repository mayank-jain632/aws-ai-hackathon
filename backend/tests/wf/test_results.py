from __future__ import annotations

import json

import pytest

from backend.app.wf.harness import run_spec
from backend.app.wf.interfaces import TargetBook
from backend.app.wf.results import RunResult, analyst_ic, memos_of
from backend.app.wf.results_io import write_schema
from backend.tests.wf import harness_stubs as hs
from backend.tests.wf._synth import random_walk_bars, rf


def _result(tmp_path) -> RunResult:
    data = random_walk_bars(["A", "B", "SPY"], 80, seed=4)
    return run_spec(hs.make_spec(), now_iso="t0", clock=lambda: "t1", pit=hs.StubPit(), bars=data,
                    out_root=tmp_path, rf=rf(1.0))


def test_result_json_validates_against_exported_schema(tmp_path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    res = _result(tmp_path)
    schema_path = write_schema(tmp_path / "result.schema.json")
    schema = json.loads(schema_path.read_text())
    stored = json.loads((tmp_path / res.spec_hash / "result.json").read_text())
    jsonschema.validate(stored, schema)
    assert RunResult.model_validate(stored) == res
    assert res.started_at == "t0" and res.finished_at == "t1"


def test_metrics_have_every_standard_field(tmp_path) -> None:
    m = _result(tmp_path).metrics["strategy"].model_dump()
    assert set(m) == {"total_return", "cagr", "max_drawdown", "sharpe", "final_equity", "costs",
                      "turnover", "n_fills", "n_skipped", "n_blocked"}


def _memo(analyst: str, views: dict[str, str]) -> dict:
    return {"analyst": analyst, "date": "2024-01-05", "headline": "h", "body": "b",
            "views": [{"ticker": t, "stance": s, "confidence": 0.8, "note": "x", "sources": []}
                      for t, s in views.items()]}


def test_analyst_ic_present_only_with_memos() -> None:
    import pandas as pd

    idx = pd.bdate_range("2024-01-02", periods=60)
    closes = pd.DataFrame({"A": range(100, 160), "B": range(160, 100, -1), "C": range(100, 160)}, index=idx, dtype=float)
    dates = ["2024-01-05", "2024-01-12", "2024-01-19", "2024-01-26"]
    plain = {d: TargetBook(decision_date=d, weights={"A": 0.5}) for d in dates}
    assert analyst_ic(plain, closes, ["A", "B", "C"]) == {}
    with_memos = {d: TargetBook(decision_date=d, weights={"A": 0.5}, provenance={"memos": [
        _memo("technical", {"A": "long", "B": "avoid", "C": "long"})]}) for d in dates}
    out = analyst_ic(with_memos, closes, ["A", "B", "C"])
    assert {"technical@1w", "strategy_weight@4w"} <= set(out)
    assert len(memos_of(with_memos[dates[0]])) == 1
