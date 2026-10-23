"""End to end run_spec on synthetic bars with in-test components."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from backend.app.wf.harness import (
    ContaminatedRunError,
    ReplayMismatch,
    replay,
    run_spec,
)
from backend.tests.wf import harness_stubs as hs
from backend.tests.wf._synth import random_walk_bars, rf

NOW = "2026-01-01T00:00:00+00:00"


@pytest.fixture
def world():
    hs.DECIDE_CALLS.clear()
    hs.SEEN.clear()
    return random_walk_bars(["A", "B", "SPY"], 80, seed=4), hs.StubPit()


def _run(world, tmp_path, spec=None, **kw):
    data, pit = world
    return run_spec(spec or hs.make_spec(), now_iso=NOW, pit=pit, bars=data, out_root=tmp_path, rf=rf(1.0), **kw)


def test_standard_files_and_result_content(world, tmp_path) -> None:
    res = _run(world, tmp_path)
    run_dir = tmp_path / res.spec_hash
    for f in ("spec.json", "result.json", "equity.csv", "fills.csv", "summary.md"):
        assert (run_dir / f).is_file()
    assert len(list((run_dir / "decisions").glob("*.json"))) == len(res.decisions) >= 8
    assert res.label == "model-clean" and res.started_at == NOW and res.finished_at == NOW
    assert {"strategy", "equal_weight_buy_hold", "spy_buy_hold"} <= set(res.metrics)
    assert "mechanical_seed" not in res.metrics  # no memos -> skipped, not faked
    m = res.metrics["strategy"]
    assert m.n_fills > 0 and m.final_equity == pytest.approx(
        pd.read_csv(run_dir / "equity.csv", index_col=0)["strategy"].iloc[-1]
    )
    assert "vs_equal_weight_buy_hold" in res.significance
    day = json.loads(next((run_dir / "decisions").glob("*.json")).read_text())
    assert day["book"]["weights"] == {"A": 0.5, "B": 0.25} and day["orders"]["intents"]


def test_rerun_is_resumable_and_deterministic(world, tmp_path) -> None:
    first = _run(world, tmp_path)
    n_calls = len(hs.DECIDE_CALLS)
    second = _run(world, tmp_path)
    assert len(hs.DECIDE_CALLS) == n_calls  # all books came from the cache
    assert first.metrics == second.metrics


def test_replay_matches_and_detects_tampering(world, tmp_path) -> None:
    res = _run(world, tmp_path)
    data, pit = world
    run_dir = tmp_path / res.spec_hash
    assert replay(run_dir, pit=pit, bars=data, rf=rf(1.0)) <= 1e-9
    assert replay(res.spec_hash, pit=pit, bars=data, rf=rf(1.0), out_root=tmp_path) <= 1e-9
    eq = pd.read_csv(run_dir / "equity.csv", index_col=0)
    eq.iloc[5, 0] += 1.0
    eq.to_csv(run_dir / "equity.csv")
    with pytest.raises(ReplayMismatch):
        replay(run_dir, pit=pit, bars=data, rf=rf(1.0))


def test_contaminated_dates_refused_unless_allowed(world, tmp_path) -> None:
    spec = hs.make_spec(cutoff="2024-01")  # clean from 2024-03-01, first decision 2024-01-05
    with pytest.raises(ContaminatedRunError):
        _run(world, tmp_path, spec)
    assert _run(world, tmp_path, spec, allow_contaminated=True).label == "contaminated"


def test_unknown_cutoff_is_labelled_not_clean(world, tmp_path) -> None:
    assert _run(world, tmp_path, hs.make_spec(cutoff=None)).label == "unknown-cutoff"


def test_invalid_book_is_rejected(world, tmp_path) -> None:
    from backend.app.wf.interfaces import ComponentSpec

    spec = hs.make_spec(decider=ComponentSpec(ref="t_const", params={"weights": {"ZZZ": 0.5}}))
    with pytest.raises(RuntimeError, match="outside universe"):
        _run(world, tmp_path, spec)


def test_state_dependent_execution_sees_true_state_at_decision_close(tmp_path) -> None:
    dates = pd.bdate_range("2024-01-02", "2024-01-19")
    data = hs.flat_bars(["A", "SPY"], dates, last_close=None)
    data["A"].loc["2024-01-12", ["high", "close"]] = 120.0  # A closes +20% on the second decision day
    spec = hs.make_spec(
        first="2024-01-05", last="2024-01-12", end="2024-01-19",
        universe=("A",), decider={"ref": "t_const", "params": {"weights": {"A": 0.5}}},
        execution={"ref": "t_drift", "params": {"threshold": 0.05}},
    )
    hs.SEEN.clear()
    res = run_spec(spec, now_iso=NOW, pit=hs.StubPit(), bars=data, out_root=tmp_path, rf=rf(0.0))
    s0, s1 = hs.SEEN["2024-01-05"], hs.SEEN["2024-01-12"]
    assert (s0.equity, s0.cash, dict(s0.positions)) == (100_000.0, 100_000.0, {})
    # 500 sh bought at the 2024-01-08 open (100); close 120 -> 40k... 50k cash + 60k stock
    assert s1.equity == pytest.approx(110_000.0) and s1.cash == pytest.approx(50_000.0)
    assert dict(s1.shares) == {"A": pytest.approx(500.0)}
    # weight 60/110 = 0.5454 drifted by 0.045 < 0.05: the policy trades nothing and says why
    assert res.decisions[-1].n_intents == 0 and res.decisions[-1].blocked == ["no drift"]
    assert res.metrics["strategy"].n_blocked == 1 and res.metrics["strategy"].n_fills == 1


def test_lower_threshold_makes_the_state_dependent_policy_trade(tmp_path) -> None:
    dates = pd.bdate_range("2024-01-02", "2024-01-19")
    data = hs.flat_bars(["A", "SPY"], dates)
    data["A"].loc["2024-01-12", ["high", "close"]] = 120.0
    spec = hs.make_spec(
        first="2024-01-05", last="2024-01-12", end="2024-01-19", universe=("A",),
        decider={"ref": "t_const", "params": {"weights": {"A": 0.5}}},
        execution={"ref": "t_drift", "params": {"threshold": 0.02}},
    )
    res = run_spec(spec, now_iso=NOW, pit=hs.StubPit(), bars=data, out_root=tmp_path, rf=rf(0.0))
    assert res.metrics["strategy"].n_fills == 2  # buy, then trim the drifted position


def test_stateful_decider_runs_in_the_loop_with_real_snapshot(world, tmp_path) -> None:
    from backend.app.wf.interfaces import ComponentSpec

    spec = hs.make_spec(decider=ComponentSpec(ref="t_stateful", params={"weights": {"A": 0.5}}))
    _run(world, tmp_path, spec)
    snaps = [v for k, v in hs.SEEN.items() if k.startswith("decide:")]
    assert snaps[0].equity == 100_000.0 and snaps[-1].positions  # later dates see held names
