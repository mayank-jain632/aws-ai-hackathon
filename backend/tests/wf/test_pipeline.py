import hashlib

import pytest

from backend.app.wf.config import WfConfig
from backend.app.wf.llm import StubLlm
from backend.app.wf.pipeline import (
    ContaminatedDateError,
    run_all,
    run_decision,
    write_manifest,
)
from backend.tests.wf.conftest_helpers import UNIVERSE, FakePit, responder

CFG = WfConfig(universe=tuple(UNIVERSE))
DATES = ["2025-10-03", "2025-10-10", "2025-10-17"]


def test_end_to_end_and_resume(tmp_path):
    llm = StubLlm(responder)
    recs = run_all(FakePit(), llm, CFG, DATES, tmp_path, workers=3)
    assert [r.decision_date for r in recs] == DATES
    r = recs[0]
    assert r.abstained_analysts == [] and len(r.memos) == 5
    i = {x.ticker: x for x in r.orders.intents}
    assert i["AAPL"].stop_price == 95.0 and i["AAPL"].limit_price == 99.0
    assert i["MSFT"].target_weight == 0.0 and i["NVDA"].target_weight == 0.0
    n = llm.calls
    assert n == 3 * 7
    again = run_all(FakePit(), llm, CFG, DATES, tmp_path)
    assert llm.calls == n and [x.decision_date for x in again] == DATES
    run_all(FakePit(), llm, CFG, DATES[:1], tmp_path, force=True)
    assert llm.calls == n + 7


def test_contaminated_guard(tmp_path):
    with pytest.raises(ContaminatedDateError):
        run_all(FakePit(), StubLlm(responder), CFG, ["2024-06-07"], tmp_path)
    with pytest.raises(ContaminatedDateError):
        run_decision(
            FakePit(), StubLlm(responder), CFG, "2024-06-07", contaminated=False
        )
    recs = run_all(
        FakePit(),
        StubLlm(responder),
        CFG,
        ["2024-06-07", "2025-10-03"],
        tmp_path,
        allow_contaminated=True,
    )
    assert recs[0].contaminated and recs[0].orders.contaminated
    assert not recs[1].contaminated and not recs[1].orders.contaminated


def test_failed_date_raises_but_keeps_others(tmp_path):
    def r(schema, system, user):
        if schema == "TradePlan" and "2025-10-10" in user:
            raise RuntimeError("x")
        return responder(schema, system, user)

    with pytest.raises(RuntimeError):
        run_all(FakePit(), StubLlm(r), CFG, DATES, tmp_path)
    assert (tmp_path / "decisions" / "2025-10-03.json").exists()
    assert not (tmp_path / "decisions" / "2025-10-10.json").exists()


def test_manifest_hashes(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.csv").write_text("hi")
    m = write_manifest(tmp_path / "run", CFG, data_dir=data)
    assert m.data_hashes == {"a.csv": hashlib.sha256(b"hi").hexdigest()}
    assert m.prompt_hash and any(
        n.startswith("prompt:strategy.SYSTEM=") for n in m.notes
    )
    assert (tmp_path / "run" / "manifest.json").exists()
    assert m.config["model_id"] == CFG.model_id
