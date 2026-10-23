from __future__ import annotations

from types import MappingProxyType

import pytest

from backend.app.wf.adapters.evaluators import ReferenceEvaluator, WfEvaluator
from backend.app.wf.interfaces import Evaluator
from backend.tests.wf._adapter_fakes import AB, syn_closes, syn_dir

CUT, END = "2024-01-02", "2024-12-20"
W = MappingProxyType({"AAA": 0.6, "BBB": 0.4})


@pytest.fixture()
def ref(tmp_path):
    return ReferenceEvaluator(universe=AB, closes=syn_closes(syn_dir(tmp_path)), rf_annual_pct=4.0)


@pytest.fixture()
def wf(tmp_path):
    return WfEvaluator(costs_bps=0.0, data_dir=syn_dir(tmp_path), universe=AB)


def test_both_satisfy_protocol_and_accept_mappings(ref, wf) -> None:
    for ev in (ref, wf):
        assert isinstance(ev, Evaluator)
        res = ev.evaluate(W, CUT, END)
        assert res.portfolio.total_return != 0 and res.equal_weight is not None and res.assumptions


@pytest.mark.parametrize("fixture", ["ref", "wf"])
def test_unknown_ticker_rejected(request, fixture) -> None:
    ev = request.getfixturevalue(fixture)
    with pytest.raises(ValueError, match="outside the universe"):
        ev.evaluate({"AAA": 0.5, "ZZZZ": 0.5}, CUT, END)


def test_reference_assumptions_and_equity(ref) -> None:
    res = ref.evaluate(W, CUT, END)
    assert any("monthly rebalance" in a for a in res.assumptions) and any("2025-06-30" in a for a in res.assumptions)
    assert set(res.equity) >= {"dates", "portfolio", "equal_weight", "spy"}


def test_wf_costs_reduce_return(tmp_path) -> None:
    d = syn_dir(tmp_path)
    free = WfEvaluator(costs_bps=0.0, data_dir=d, universe=AB).evaluate(W, CUT, END)
    costly = WfEvaluator(costs_bps=50.0, data_dir=d, universe=AB).evaluate(W, CUT, END)
    assert costly.portfolio.total_return < free.portfolio.total_return
    assert free.equity["dates"][0] == "2024-01-02" and free.equity["portfolio"][0] == 1.0


def test_wf_rejects_unnormalised_overweight_when_not_normalising(tmp_path) -> None:
    ev = WfEvaluator(data_dir=syn_dir(tmp_path), universe=AB, normalize=False)
    with pytest.raises(ValueError, match="> 1"):
        ev.evaluate({"AAA": 0.8, "BBB": 0.8}, CUT, END)
