"""Shared fakes for the adapter, conformance and reference-comparison tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from backend.app.wf.adapters.pit_view import BoundPit
from backend.app.wf.config import WfConfig
from backend.app.wf.interfaces import DecisionContext, PortfolioSnapshot
from backend.app.wf.llm import StubLlm
from backend.app.wf.pit import PitData
from backend.tests.wf.conftest_helpers import FakePit, responder
from backend.tests.wf.synth import make_data_dir

AB = ["AAA", "BBB"]
CLEAN_DATE = "2025-11-07"
SYN_DATES = ["2024-06-14", "2024-11-12"]


def fake_ctx(
    as_of: str = CLEAN_DATE,
    universe=("AAPL", "MSFT", "NVDA"),
    portfolio: PortfolioSnapshot | None = None,
    pit=None,
    **cfg_kw,
) -> DecisionContext:
    pf = portfolio or PortfolioSnapshot(as_of=as_of, equity=1_000_000.0, cash=1_000_000.0)
    return DecisionContext(
        as_of=as_of, universe=tuple(universe), pit=BoundPit(pit or FakePit(), as_of),
        portfolio=pf, cfg=WfConfig(**cfg_kw),
    )


def stub_llm() -> StubLlm:
    return StubLlm(responder)


def ab_responder(schema: str, system: str, user: str):
    if schema == "_MemoDraft":
        sid = next(ln[1 : ln.index("]")] for ln in user.splitlines() if ln.startswith("["))
        return {"headline": "h", "body": "b", "views": [
            {"ticker": "AAA", "stance": "long", "confidence": 0.8, "note": "n", "sources": [sid]}]}
    if schema == "TradePlan":
        plans = [{"ticker": t, "target_weight": w, "stop_pct": 0.05, "target_pct": 0.1, "rationale": "r",
                  "changes_my_mind": "c", "memo_sources": []} for t, w in (("AAA", 0.25), ("BBB", 0.2))]
        return {"decision_date": "x", "strategy_name": "s", "summary": "sum", "plans": plans}
    return {"decision_date": "x", "orders": [{"ticker": "AAA", "entry": "market_open"}]}


def ab_llm() -> StubLlm:
    return StubLlm(ab_responder)


def syn_dir(tmp_path: Path) -> Path:
    root = tmp_path / "syn"
    return root if root.exists() else make_data_dir(root)


def make_syn_pit(data_dir: Path) -> PitData:
    return PitData(data_dir)


def syn_closes(data_dir: Path) -> pd.DataFrame:
    cols = {t: pd.read_csv(data_dir / "prices" / f"{t}.csv", parse_dates=["date"]).set_index("date")["close"]
            for t in (*AB, "SPY")}
    return pd.DataFrame(cols)


def fake_plan(orders=(), blocked=(), ready=True, skipped=None):
    return SimpleNamespace(orders=list(orders), blocked=list(blocked), ready=ready, skipped=skipped or {})


def planned(symbol: str, side: str, notional: float, current: float):
    return SimpleNamespace(symbol=symbol, side=side, notional=notional, current_value=current)
