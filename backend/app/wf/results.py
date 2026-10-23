"""The STANDARD result of a run: one pydantic model other lanes can consume (hub D22)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schema import Memo
from backend.app.wf import evaluate
from backend.app.wf.engine import EngineResult
from backend.app.wf.interfaces import TargetBook
from backend.app.wf.runner import STANCE_SIGN
from backend.app.wf.runspec import Label, RunSpec
from backend.app.wf.schemas import DecisionOrders

log = logging.getLogger("wf.results")
PRIMARY = "strategy"
IC_HORIZONS = ((5, "1w"), (20, "4w"))


class StrategyMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_return: float
    cagr: float
    max_drawdown: float
    sharpe: float
    final_equity: float
    costs: float
    turnover: float = Field(description="mean weekly turnover (traded notional / equity)")
    n_fills: int
    n_skipped: int
    n_blocked: int


class AnalystIC(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean_ic: float
    t_stat: float
    hit_rate: float
    n: int


class DecisionIndexEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    contaminated: bool
    n_intents: int
    target_gross: float
    blocked: list[str] = Field(default_factory=list)
    abstained_analysts: list[str] = Field(default_factory=list)


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_hash: str
    spec: RunSpec
    label: Label
    started_at: str
    finished_at: str
    git_sha: str | None = None
    data_hashes: dict[str, str] = Field(default_factory=dict)
    primary: str = PRIMARY
    metrics: dict[str, StrategyMetrics]
    significance: dict[str, Any] = Field(default_factory=dict)
    analyst_ic: dict[str, AnalystIC] = Field(default_factory=dict)
    decisions: list[DecisionIndexEntry] = Field(default_factory=list)


def strategy_metrics(res: EngineResult, rf_mean: float) -> StrategyMetrics:
    m = evaluate.summarize(res.equity, rf_mean)
    blocked = int((res.skipped["reason"] == "blocked").sum()) if len(res.skipped) else 0
    return StrategyMetrics(
        total_return=m.total_return,
        cagr=m.cagr,
        max_drawdown=m.max_drawdown,
        sharpe=m.sharpe,
        final_equity=float(res.equity.iloc[-1]),
        costs=res.costs,
        turnover=float(res.turnover.mean()) if len(res.turnover) else 0.0,
        n_fills=len(res.fills),
        n_skipped=len(res.skipped),
        n_blocked=blocked,
    )


def significance_vs(results: Mapping[str, EngineResult], primary: str = PRIMARY) -> dict[str, Any]:
    """Paired block-bootstrap excess return and Sharpe difference of ``primary`` vs each baseline."""
    out: dict[str, Any] = {}
    base_weekly = results[primary].weekly_returns
    for name, res in results.items():
        if name == primary:
            continue
        try:
            ci = evaluate.paired_excess_ci(base_weekly, res.weekly_returns)
            sd = evaluate.sharpe_diff_ci(base_weekly, res.weekly_returns)
        except ValueError as exc:  # too few weekly returns: report it, never hide it
            log.warning("significance vs %s unavailable: %s", name, exc)
            out[f"vs_{name}"] = {"error": str(exc)}
            continue
        out[f"vs_{name}"] = {
            "excess_weekly_mean": ci.mean, "excess_lo": ci.lo, "excess_hi": ci.hi,
            "p_le_zero": ci.p_le_zero, "n_weeks": ci.n,
            "sharpe_diff": sd.mean, "sharpe_diff_lo": sd.lo, "sharpe_diff_hi": sd.hi,
        }
    return out


def memos_of(book: TargetBook) -> list[Memo]:
    """Analyst memos a decider stored in ``provenance["memos"]`` (JSON dicts); [] when absent."""
    memos = []
    for raw in book.provenance.get("memos", []) or []:
        try:
            memos.append(Memo.model_validate(raw))
        except ValueError as exc:
            log.warning("ignoring malformed memo on %s: %s", book.decision_date, exc)
    return memos


def analyst_scores(books: Mapping[str, TargetBook], universe: list[str]) -> dict[str, pd.DataFrame]:
    rows: dict[str, dict[str, dict[str, float]]] = {}
    for date, book in books.items():
        for m in memos_of(book):
            slot = rows.setdefault(m.analyst, {}).setdefault(date, {})
            for v in m.views:
                slot[v.ticker] = STANCE_SIGN[v.stance] * v.confidence
        rows.setdefault("strategy_weight", {})[date] = dict(book.weights)
    return {k: pd.DataFrame(v).T.reindex(columns=universe).fillna(0.0) for k, v in rows.items()}


def analyst_ic(books: Mapping[str, TargetBook], closes: pd.DataFrame, universe: list[str]) -> dict[str, AnalystIC]:
    """Rank IC per analyst (when memos are present) and for the decider's own weights."""
    if not any(memos_of(b) for b in books.values()):
        return {}
    scores, dates, out = analyst_scores(books, universe), sorted(books), {}
    for horizon, name in IC_HORIZONS:
        fwd = evaluate.forward_returns(closes[universe], dates, horizon)
        for analyst, frame in scores.items():
            ic = evaluate.rank_ic(frame, fwd)
            out[f"{analyst}@{name}"] = AnalystIC(mean_ic=ic.mean, t_stat=ic.t_stat, hit_rate=ic.hit_rate, n=ic.n)
    return out


def decision_index(
    books: Mapping[str, TargetBook], orders: Mapping[str, DecisionOrders]
) -> list[DecisionIndexEntry]:
    out = []
    for date in sorted(books):
        o = orders.get(date)
        out.append(
            DecisionIndexEntry(
                date=date,
                contaminated=bool(o.contaminated) if o else False,
                n_intents=len(o.intents) if o else 0,
                target_gross=float(sum(books[date].weights.values())),
                blocked=list(o.blocked) if o else [],
                abstained_analysts=list(books[date].provenance.get("abstained_analysts", [])),
            )
        )
    return out
