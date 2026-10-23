import random
import re

import numpy as np
import pandas as pd

from backend.app.wf import audit, evaluate
from backend.app.wf.config import WfConfig
from backend.app.wf.llm import StubLlm
from backend.tests.wf.conftest_helpers import FakePit
from backend.tests.wf.test_masking import code_responder

UNI = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM"]
CFG = WfConfig(universe=tuple(UNI), first_decision="2025-10-03", last_decision="2025-12-19", dev_decisions=2)


def make_bars() -> dict:
    days = pd.bdate_range("2025-08-01", "2026-02-27")
    rng = np.random.default_rng(3)
    bars = {}
    for t in [*UNI, "SPY"]:
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days))))
        bars[t] = pd.DataFrame({"close": close}, index=days)
    return bars


BARS = make_bars()
CLOSES = pd.DataFrame({t: BARS[t]["close"] for t in UNI})


def _memo_scores(as_of: str, toks: list[str], mode: str, user: str) -> list[float]:
    if mode == "same":  # identical in named and masked runs
        rng = random.Random(as_of)
    elif UNI[0] in toks:  # named run: oracle
        fwd = evaluate.forward_returns(CLOSES, [as_of], 5).loc[as_of]
        order = fwd.rank().to_numpy()
        return [0.05 + 0.15 * float(r) for r in order]
    else:  # masked run: noise
        rng = random.Random(user)
    return [rng.random() for _ in toks]


def stub(mode: str) -> StubLlm:
    def responder(schema, system, user):
        out = code_responder(schema, system, user)
        if schema != "_MemoDraft":
            return out
        as_of = re.search(r"cutoff\): (\d{4}-\d\d-\d\d)", user).group(1)
        toks = [v["ticker"] for v in out["views"]]
        for v, s in zip(out["views"], _memo_scores(as_of, toks, mode, user), strict=True):
            v["confidence"] = min(1.0, s)
        return out

    return StubLlm(responder)


def run(mode: str, tmp_path):
    return audit.run_audit(FakePit(), stub(mode), CFG, "clean", tmp_path, BARS, workers=2)


def row(res, series="technical", horizon="1w"):
    return next(r for r in res["rows"] if r["series"] == series and r["horizon"] == horizon)


def test_oracle_named_vs_random_masked_is_named_better(tmp_path):
    res = run("oracle", tmp_path)
    r = row(res)
    assert r["named_ic"] > 0.9 and r["diff"] > 0.3
    assert r["verdict"] == audit.VERDICT_NAMED
    assert (tmp_path / "named" / "decisions").exists() and (tmp_path / "masked" / "decisions").exists()
    assert "named better" in (tmp_path / "audit.md").read_text()
    assert (tmp_path / "audit.json").exists()


def test_identical_runs_have_no_detectable_effect(tmp_path):
    res = run("same", tmp_path)
    for r in res["rows"]:
        assert r["diff"] == 0 and r["verdict"] == audit.VERDICT_NONE
    ag = res["agreement"]
    assert ag["mean_abs_weight_diff"] == 0 and ag["share_weight_diff_gt_5pts"] == 0


def test_ci_math_on_hand_series():
    idx = [f"2025-10-{d:02d}" for d in range(1, 9)]
    ones, zeros = pd.Series([1.0] * 8, index=idx), pd.Series([0.0] * 8, index=idx)
    r = audit.compare_row(ones, zeros)
    assert (r["diff"], r["ci_lo"], r["ci_hi"], r["n_dates"]) == (1.0, 1.0, 1.0, 8)
    assert r["verdict"] == audit.VERDICT_NAMED
    assert audit.compare_row(zeros, ones)["verdict"] == audit.VERDICT_MASKED
    alt = pd.Series([1.0, -1.0, 0.0, 1.0, -1.0, 0.0, 1.0, -1.0], index=idx)
    mixed = audit.compare_row(alt, zeros)
    assert abs(mixed["diff"]) < 1e-12 and mixed["ci_lo"] < 0 < mixed["ci_hi"]
    assert mixed["verdict"] == audit.VERDICT_NONE


def test_verdict_rule_boundaries():
    ci = evaluate.BootCI
    assert audit.verdict(ci(0.1, 0.0001, 0.2, 5, 0.1)) == audit.VERDICT_NAMED
    assert audit.verdict(ci(0.1, 0.0, 0.2, 5, 0.1)) == audit.VERDICT_NONE
    assert audit.verdict(ci(-0.1, -0.2, -0.0001, 5, 0.1)) == audit.VERDICT_MASKED


def test_control_window_dates_are_the_17_pre_cutoff_fridays():
    idx = pd.bdate_range("2025-01-01", "2025-12-31")
    dates = audit.window_dates("control", idx, CFG)
    assert dates[0] == "2025-03-07" and dates[-1] == "2025-06-27" and len(dates) == 17
