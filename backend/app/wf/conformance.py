"""Reusable conformance checks for components plugged into the wf harness (hub D22).

    report = check_decider(MyDecider(), make_pit, dates, universe, data_dir=DATA_DIR)
    assert_conforms(report)

``make_pit(data_dir)`` builds a `PitData`-like object (date-taking API) on a data directory; the
checks call it on the real directory and on a copy whose every row dated after ``as_of`` is
sentinel garbage, then bind each with `BoundPit`. Any difference in output is leakage.

Deciders and execution policies: future-poison, determinism, schema, static import lint.
Execution policies also: orders never sell more than held nor spend more than cash plus
proceeds (a tiny engine run). Evaluators: reject unknown tickers, deterministic, sane output,
and unchanged when every row after ``end`` is poisoned.
"""

from __future__ import annotations

import ast
import inspect
import logging
import math
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.wf import baselines, market
from backend.app.wf.adapters.pit_view import BoundPit
from backend.app.wf.config import WfConfig
from backend.app.wf.engine import run_engine
from backend.app.wf.interfaces import DecisionContext, PortfolioSnapshot, TargetBook
from backend.app.wf.schemas import DecisionOrders

log = logging.getLogger("wf.conformance")
SENTINEL = 9.99e12
EPS = 1e-9
FORBIDDEN_MODULE_PARTS = ("wf.market", "prices_full")
FORBIDDEN_NAMES = {"last_close", "prices_full"}
EQUITY = 1_000_000.0


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class ConformanceReport:
    component: str
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def summary(self) -> str:
        lines = [f"{'PASS' if c.passed else 'FAIL'} {c.name}: {c.detail}" for c in self.checks]
        return f"{self.component}: {'conforms' if self.passed else 'DOES NOT CONFORM'}\n" + "\n".join(lines)


def assert_conforms(report: ConformanceReport) -> None:
    """pytest-friendly: raises AssertionError listing every failed check."""
    if not report.passed:
        raise AssertionError(report.summary())


def _run(name: str, fn: Callable[[], str]) -> CheckResult:
    try:
        return CheckResult(name, True, fn() or "ok")
    except AssertionError as exc:
        return CheckResult(name, False, str(exc))
    except Exception as exc:  # noqa: BLE001 a crashing component is a failed check, not a crashed harness
        return CheckResult(name, False, f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------------------ poison


def _poison(src: Path, dst: Path, as_of: str) -> None:
    """Copy ``src`` and overwrite every row that is not visible at ``as_of`` with garbage."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("raw"))
    for p in (dst / "prices").glob("*.csv"):
        df = pd.read_csv(p)
        fut = df["date"] > as_of
        df.loc[fut, ["open", "high", "low", "close", "volume"]] = SENTINEL
        df.to_csv(p, index=False)
    _poison_csv(dst / "fred" / "macro.csv", "available", ">", as_of, ["value"])
    _poison_csv(dst / "sec" / "fundamentals.csv", "filed", ">=", as_of, ["revenue", "net_income", "total_debt"])
    _poison_csv(dst / "sec" / "filings_8k.csv", "filed", ">=", as_of, ["items", "item_titles", "description"], text=True)


def _poison_csv(path: Path, date_col: str, op: str, as_of: str, cols: list[str], text: bool = False) -> None:
    if not path.exists():
        return
    df = pd.read_csv(path)
    mask = df[date_col] > as_of if op == ">" else df[date_col] >= as_of
    for c in (c for c in cols if c in df.columns):
        df[c] = df[c].astype(object) if text else df[c].astype(float)
        df.loc[mask, c] = "SENTINEL 8.01 7.01 5.02" if text else SENTINEL
    df.to_csv(path, index=False)


# ------------------------------------------------------------------------------ context


def _ctx(pit: Any, as_of: str, universe: Sequence[str], cfg: WfConfig, portfolio: PortfolioSnapshot | None = None):
    pf = portfolio or PortfolioSnapshot(as_of=as_of, equity=EQUITY, cash=EQUITY)
    return DecisionContext(
        as_of=as_of, universe=tuple(universe), pit=BoundPit(pit, as_of), portfolio=pf, cfg=cfg,
        contaminated=as_of < cfg.clean_start,
    )


def _holdings(pit: Any, as_of: str, universe: Sequence[str]) -> PortfolioSnapshot:
    """25% in each of the first two universe names, the rest cash."""
    values = {t: 0.25 * EQUITY for t in universe[:2]}
    shares = {t: v / pit.last_close(as_of, t) for t, v in values.items()}
    return PortfolioSnapshot(
        as_of=as_of, equity=EQUITY, cash=EQUITY - sum(values.values()), positions=values, shares=shares
    )


def _dump(obj: Any) -> Any:
    return obj.model_dump() if hasattr(obj, "model_dump") else obj


# ------------------------------------------------------------------------------ lint


def lint_violations(source: str) -> list[str]:
    """Static scan for imports that reach future data (same rules as tests/wf/test_import_lint.py)."""
    bad: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            bad += [f"import {a.name}" for a in node.names if any(p in a.name for p in FORBIDDEN_MODULE_PARTS)]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(p in mod for p in FORBIDDEN_MODULE_PARTS):
                bad.append(f"from {mod} import ...")
            if (mod.endswith("wf") or node.level) and any(a.name == "market" for a in node.names):
                bad.append(f"from {'.' * node.level}{mod} import market")
            if node.level and mod.endswith("market"):
                bad.append(f"from {'.' * node.level}{mod} import ...")
            bad += [f"from {mod} import {a.name}" for a in node.names if a.name in FORBIDDEN_NAMES]
        elif isinstance(node, ast.Attribute) and node.attr == "prices_full":
            bad.append("attribute access .prices_full")
    return bad


def _check_lint(component: Any) -> str:
    module = sys.modules.get(type(component).__module__)
    path = inspect.getsourcefile(module) if module else None
    if path is None:
        raise AssertionError(f"cannot find the source of {type(component).__module__}")
    bad = lint_violations(Path(path).read_text(encoding="utf-8"))
    if bad:
        raise AssertionError(f"{path}: {bad}")
    return f"{Path(path).name} clean"


# ------------------------------------------------------------------------------ schema


def _check_book(book: TargetBook, as_of: str, universe: Sequence[str]) -> None:
    w = book.weights
    assert book.decision_date == as_of, f"decision_date {book.decision_date} != {as_of}"
    assert set(w) <= set(universe), f"tickers outside the universe: {sorted(set(w) - set(universe))}"
    assert all(math.isfinite(v) and v >= 0 for v in w.values()), f"negative or non-finite weight: {w}"
    assert sum(w.values()) <= 1 + EPS, f"weights sum to {sum(w.values()):.6f} > 1"
    assert set(book.stop_pct) | set(book.target_pct) <= set(universe), "stop/target for unknown ticker"
    assert all(0 < v < 1 for v in book.stop_pct.values()), f"stop_pct outside (0,1): {book.stop_pct}"
    assert all(v > 0 for v in book.target_pct.values()), f"target_pct not positive: {book.target_pct}"


def _check_orders(orders: DecisionOrders, as_of: str, universe: Sequence[str], pit: BoundPit) -> None:
    assert orders.date == as_of, f"orders dated {orders.date} != {as_of}"
    if orders.blocked:
        assert not orders.intents, "a blocked plan must have no intents"
    for it in orders.intents:
        assert it.ticker in universe, f"{it.ticker} outside the universe"
        assert 0 <= it.target_weight <= 1, f"{it.ticker} target {it.target_weight} outside [0, 1]"
        close = pit.last_close(it.ticker)
        if it.stop_price is not None:
            assert 0 < it.stop_price < close, f"{it.ticker} stop {it.stop_price} not below close {close}"
        if it.target_price is not None:
            assert it.target_price > close, f"{it.ticker} target {it.target_price} not above close {close}"
    assert sum(i.target_weight for i in orders.intents) <= 1 + 1e-6, "intent targets sum to more than 1"


# ------------------------------------------------------------------- decider / execution


def _poisoned_pit(make_pit: Callable[[Path], Any], data_dir: Path, as_of: str, tmp: Path):
    dst = tmp / f"poison_{as_of}"
    _poison(Path(data_dir), dst, as_of)
    return make_pit(dst)


def _check_poison(
    produce: Callable[[DecisionContext], Any], make_pit, data_dir: Path, dates, universe, cfg
) -> str:
    real = make_pit(Path(data_dir))
    with tempfile.TemporaryDirectory() as td:
        for as_of in dates:
            clean_ctx = _ctx(real, as_of, universe, cfg, _holdings(real, as_of, universe))
            dirty = _poisoned_pit(make_pit, data_dir, as_of, Path(td))
            dirty_ctx = _ctx(dirty, as_of, universe, cfg, _holdings(real, as_of, universe))
            a, b = _dump(produce(clean_ctx)), _dump(produce(dirty_ctx))
            assert a == b, f"{as_of}: output changed when data after the decision date was poisoned"
    return f"{len(list(dates))} date(s) identical under future poison"


def _check_deterministic(produce, make_pit, data_dir, dates, universe, cfg) -> str:
    pit = make_pit(Path(data_dir))
    for as_of in dates:
        ctx = _ctx(pit, as_of, universe, cfg)
        assert _dump(produce(ctx)) == _dump(produce(ctx)), f"{as_of}: two calls differ"
    return "two calls identical"


def check_decider(
    decider: Any, make_pit: Callable[[Path], Any], dates: Sequence[str], universe: Sequence[str],
    *, data_dir: Path, cfg: WfConfig | None = None,
) -> ConformanceReport:
    cfg = cfg or WfConfig()
    dates = list(dates)
    real = make_pit(Path(data_dir))

    def schema() -> str:
        for d in dates:
            _check_book(decider.decide(_ctx(real, d, universe, cfg)), d, universe)
        return f"{len(dates)} book(s) valid"

    checks = (
        _run("future_poison", lambda: _check_poison(decider.decide, make_pit, data_dir, dates, universe, cfg)),
        _run("determinism", lambda: _check_deterministic(decider.decide, make_pit, data_dir, dates, universe, cfg)),
        _run("schema", schema),
        _run("import_lint", lambda: _check_lint(decider)),
    )
    return ConformanceReport(getattr(decider, "name", type(decider).__name__), checks)


def check_execution(
    policy: Any, make_pit: Callable[[Path], Any], dates: Sequence[str], universe: Sequence[str],
    book_factory: Callable[[DecisionContext], TargetBook], *, data_dir: Path, cfg: WfConfig | None = None,
) -> ConformanceReport:
    cfg = cfg or WfConfig()
    dates = list(dates)
    real = make_pit(Path(data_dir))

    def produce(ctx: DecisionContext) -> DecisionOrders:
        return policy.plan(ctx, book_factory(ctx))

    def schema() -> str:
        for d in dates:
            ctx = _ctx(real, d, universe, cfg, _holdings(real, d, universe))
            _check_orders(produce(ctx), d, universe, ctx.pit)
        return f"{len(dates)} order set(s) valid"

    checks = (
        _run("future_poison", lambda: _check_poison(produce, make_pit, data_dir, dates, universe, cfg)),
        _run("determinism", lambda: _check_deterministic(produce, make_pit, data_dir, dates, universe, cfg)),
        _run("schema", schema),
        _run("import_lint", lambda: _check_lint(policy)),
        _run("no_oversell_no_overspend", lambda: _check_feasible(policy, real, dates[0], universe, book_factory, data_dir, cfg)),
    )
    return ConformanceReport(getattr(policy, "name", type(policy).__name__), checks)


# ------------------------------------------------------------------------ engine check


def _ledger_violations(fills: pd.DataFrame, held: Mapping[str, float], start_cash: float) -> list[str]:
    """Replay fills in order: shares may not go negative, cash may not go negative."""
    shares, cash, bad = dict(held), start_cash, []
    for row in fills.sort_values("date", kind="stable").itertuples():
        signed = row.shares if row.side == "buy" else -row.shares
        shares[row.ticker] = shares.get(row.ticker, 0.0) + signed
        cash -= signed * row.price
        if shares[row.ticker] < -1e-6:
            bad.append(f"{row.date:%Y-%m-%d} sold more {row.ticker} than held ({shares[row.ticker]:.4f})")
        if cash < -1e-3:
            bad.append(f"{row.date:%Y-%m-%d} spent more than cash plus proceeds (cash {cash:.2f})")
    return bad


def _check_feasible(policy, real, as_of, universe, book_factory, data_dir, cfg) -> str:
    bars = market.load_bars(Path(data_dir), list(universe))
    sessions = pd.DatetimeIndex(sorted(set().union(*[set(b.index) for b in bars.values()])))
    pos = sessions.get_loc(pd.Timestamp(as_of))
    assert pos >= 5 and pos + 3 < len(sessions), f"{as_of} needs 5 sessions before and 3 after in the data"
    ecfg = cfg.model_copy(update={"start_cash": EQUITY, "slippage_bps": 0.0, "rebalance_band": 0.0})
    rf = pd.Series(0.0, index=sessions)
    d0 = sessions[pos - 5].strftime("%Y-%m-%d")
    init = baselines.from_target_weights({d0: {t: 0.25 for t in universe[:2]}})
    r0 = run_engine(bars, init, ecfg, rf, d0, as_of)
    pf = _portfolio_from(r0, as_of)
    ctx = _ctx(real, as_of, universe, cfg, pf)
    orders = policy.plan(ctx, book_factory(ctx))
    named = {i.ticker: i.target_weight for i in orders.intents}
    implied = sum(named.values()) + sum(pf.weight(t) for t in pf.positions if t not in named)
    assert implied <= 1 + 1e-6, f"orders imply {implied:.4f} of equity invested (> 1: spends more than cash plus proceeds)"
    end = sessions[pos + 3].strftime("%Y-%m-%d")
    r1 = run_engine(bars, [*init, orders], ecfg, rf, d0, end)
    bad = _ledger_violations(r1.fills, {}, EQUITY)
    assert not bad, "; ".join(bad[:3])
    return f"implied invested {implied:.3f}, {len(r1.fills)} fills replayed cleanly"


def _portfolio_from(result, as_of: str) -> PortfolioSnapshot:
    equity = float(result.equity.iloc[-1])
    pos = result.positions[result.positions["date"] == pd.Timestamp(as_of)]
    values = {r.ticker: r.weight * equity for r in pos.itertuples()}
    shares = {r.ticker: r.shares for r in pos.itertuples()}
    return PortfolioSnapshot(
        as_of=as_of, equity=equity, cash=equity - sum(values.values()), positions=values, shares=shares
    )


# ---------------------------------------------------------------------------- evaluator


def _check_rejects_unknown(evaluator: Any, weights: Mapping[str, float], cutoff: str, end: str) -> str:
    try:
        evaluator.evaluate({**weights, "ZZZZ": 0.1}, cutoff, end)
    except ValueError:
        return "unknown ticker rejected"
    raise AssertionError("an unknown ticker was accepted (expected ValueError)")


def _check_eval_deterministic(evaluator: Any, weights: Mapping[str, float], cutoff: str, end: str) -> str:
    first = evaluator.evaluate(dict(weights), cutoff, end)
    again = evaluator.evaluate(dict(reversed(list(weights.items()))), cutoff, end)
    assert first.model_dump() == again.model_dump(), "result depends on call order or weight ordering"
    return "identical across calls and weight ordering"


def _check_eval_output(evaluator: Any, weights: Mapping[str, float], cutoff: str, end: str) -> str:
    res = evaluator.evaluate(dict(weights), cutoff, end)
    for label, m in (("portfolio", res.portfolio), ("benchmark", res.benchmark)):
        vals = (m.total_return, m.cagr, m.max_drawdown, m.sharpe)
        assert all(math.isfinite(v) for v in vals), f"{label} metrics not finite: {vals}"
        assert -1.0 <= m.max_drawdown <= 0.0, f"{label} max_drawdown {m.max_drawdown} outside [-1, 0]"
    assert res.assumptions, "no assumptions listed"
    dates = (res.equity or {}).get("dates", [])
    assert all(cutoff <= d[:10] <= end for d in dates[1:]), "equity dates fall outside [cutoff, end]"
    return "metrics finite, assumptions listed, dates inside the window"


def _check_eval_poison(make_evaluator, data_dir: Path, weights, cutoff: str, end: str) -> str:
    clean = make_evaluator(Path(data_dir)).evaluate(dict(weights), cutoff, end)
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "poison"
        _poison(Path(data_dir), dst, end)
        dirty = make_evaluator(dst).evaluate(dict(weights), cutoff, end)
    assert clean.model_dump() == dirty.model_dump(), "result changed when data after `end` was poisoned"
    return "identical under poison after end"


def check_evaluator(
    evaluator: Any, weights: Mapping[str, float], cutoff: str, end: str,
    *, make_evaluator: Callable[[Path], Any] | None = None, data_dir: Path | None = None,
) -> ConformanceReport:
    """``make_evaluator(data_dir)`` builds the evaluator on a data directory (needed for the
    poison-after-end check; without it that check is reported as skipped, passing)."""
    poison = (
        (lambda: _check_eval_poison(make_evaluator, data_dir, weights, cutoff, end))
        if make_evaluator and data_dir
        else (lambda: "skipped: no make_evaluator/data_dir given")
    )
    checks = (
        _run("rejects_unknown_ticker", lambda: _check_rejects_unknown(evaluator, weights, cutoff, end)),
        _run("determinism", lambda: _check_eval_deterministic(evaluator, weights, cutoff, end)),
        _run("output_sanity", lambda: _check_eval_output(evaluator, weights, cutoff, end)),
        _run("future_poison_after_end", poison),
    )
    return ConformanceReport(getattr(evaluator, "name", type(evaluator).__name__), checks)
