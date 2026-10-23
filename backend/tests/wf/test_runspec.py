from __future__ import annotations

import json

import pytest

from backend.app.wf.config import WfConfig
from backend.app.wf.runspec import RunSpec, clean_start, from_wfconfig, label_for
from backend.tests.wf.harness_stubs import make_spec


def test_hash_ignores_name_notes_and_key_order() -> None:
    a = make_spec()
    b = a.model_copy(update={"name": "other", "notes": "hi"})
    shuffled = json.loads(a.model_dump_json())
    reordered = RunSpec.model_validate(dict(reversed(list(shuffled.items()))))
    assert a.spec_hash() == b.spec_hash() == reordered.spec_hash()


@pytest.mark.parametrize(
    "change",
    [
        {"seed": 1},
        {"temperature": 0.5},
        {"model_id": "x"},
        {"model_training_cutoff": "2023-07"},
        {"universe": ("A",)},
        {"reference": "QQQ"},
        {"baselines": ("spy_buy_hold",)},
        {"execution": {"ref": "t_drift", "params": {}}},
        {"decider": {"ref": "t_const", "params": {"weights": {"A": 0.4}}}},
        {"evaluator": {"ref": "e", "params": {}}},
    ],
)
def test_hash_changes_with_result_affecting_fields(change) -> None:
    a = make_spec()
    changed = RunSpec.model_validate({**json.loads(a.model_dump_json()), **change})
    assert changed.spec_hash() != a.spec_hash()


def test_hash_changes_with_window_and_engine_and_limits() -> None:
    a = make_spec()
    d = json.loads(a.model_dump_json())
    for path, value in [("window", {**d["window"], "mark_end": "2024-04-11"}),
                        ("engine", {**d["engine"], "slippage_bps": 6.0}),
                        ("limits", {**d["limits"], "max_weight": 0.3})]:
        assert RunSpec.model_validate({**d, path: value}).spec_hash() != a.spec_hash()


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValueError):
        RunSpec.model_validate({**json.loads(make_spec().model_dump_json()), "bogus": 1})


@pytest.mark.parametrize(
    ("cutoff", "first", "expected"),
    [
        ("2025-08", "2025-09-30", "contaminated"),
        ("2025-08", "2025-10-01", "model-clean"),
        ("2025-08", "2025-10-03", "model-clean"),
        ("2025-08-15", "2025-09-15", "contaminated"),
        ("2025-08-15", "2025-09-16", "model-clean"),
        (None, "2030-01-01", "unknown-cutoff"),
        ("garbage", "2030-01-01", "unknown-cutoff"),
    ],
)
def test_label_for_boundaries(cutoff, first, expected) -> None:
    spec = make_spec(first=first, last="2031-01-01", end="2031-01-10", cutoff=cutoff)
    assert label_for(spec) == expected


def test_clean_start_one_full_month_after_month_cutoff() -> None:
    assert clean_start("2025-08") == "2025-10-01"
    assert clean_start(None) is None


def test_from_wfconfig_reproduces_frozen_experiment_and_label() -> None:
    cfg = WfConfig()
    spec = from_wfconfig(cfg, decider_ref="frozen_weights", execution_ref="target_weight_execution")
    assert spec.window.first_decision == cfg.first_decision and spec.universe == cfg.universe
    assert spec.engine.slippage_bps == cfg.slippage_bps and spec.model_training_cutoff == "2025-08"
    assert label_for(spec) == "model-clean"
    back = spec.to_wfconfig()
    assert back.clean_start == cfg.clean_start and back.max_weight == cfg.max_weight
