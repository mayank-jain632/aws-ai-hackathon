"""Run a RunSpec end to end: decide (parallel, cached) -> closed-loop engine -> baselines -> result.

    phase 1  Decider.decide(ctx)         every date in a thread pool when ``decider.stateless``;
                                         TargetBooks cached in <run_dir>/books/<date>.json
    phase 2  engine closed loop          at each decision close the engine hands its own
                                         PortfolioSnapshot to ``ExecutionPolicy.plan``
    then     baselines through the same engine, statistics, the standard result files.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.agents import pm
from backend.app.wf import baselines as bl
from backend.app.wf import market, registry
from backend.app.wf.calendar import decision_dates
from backend.app.wf.engine import EngineResult, run_engine
from backend.app.wf.interfaces import DecisionContext, PortfolioSnapshot, TargetBook
from backend.app.wf.pipeline import _git_sha, data_hashes
from backend.app.wf.results import (
    PRIMARY,
    RunResult,
    analyst_ic,
    decision_index,
    memos_of,
    significance_vs,
    strategy_metrics,
)
from backend.app.wf.results_io import DEFAULT_RUNS_ROOT, equity_frame, write_run
from backend.app.wf.runspec import RunSpec, clean_start, label_for
from backend.app.wf.schemas import DecisionOrders

log = logging.getLogger("wf.harness")
REPLAY_TOL = 1e-9


class ContaminatedRunError(ValueError):
    pass


class ReplayMismatch(AssertionError):
    pass


class _LocalBoundPit:
    """`PitData` (or any date-taking PIT) bound to one decision date."""

    def __init__(self, pit, as_of: str) -> None:
        self._pit, self.as_of = pit, as_of

    def evidence(self, analyst, universe):
        return self._pit.evidence(analyst, self.as_of, universe)

    def execution_context(self, tickers):
        return self._pit.execution_context(self.as_of, tickers)

    def last_close(self, ticker):
        return self._pit.last_close(self.as_of, ticker)


def _bound_pit_cls():
    try:
        found = importlib.util.find_spec("backend.app.wf.adapters.pit_view")
    except ModuleNotFoundError:
        found = None
    if found is None:
        return _LocalBoundPit
    return importlib.import_module("backend.app.wf.adapters.pit_view").BoundPit


BoundPit = _bound_pit_cls()


@dataclass(frozen=True)
class Simulation:
    results: dict[str, EngineResult]
    books: dict[str, TargetBook]
    orders: dict[str, DecisionOrders]
    dates: list[str]
    closes: pd.DataFrame
    rf: pd.Series


def _validate_book(book: TargetBook, date: str, universe: Sequence[str]) -> TargetBook:
    if book.decision_date != date:
        raise ValueError(f"book dated {book.decision_date} returned for {date}")
    bad = sorted(set(book.weights) - set(universe))
    if bad or any(w < 0 for w in book.weights.values()) or sum(book.weights.values()) > 1 + 1e-9:
        raise ValueError(f"invalid book on {date}: tickers outside universe {bad}, negative or >1 total weight")
    return book


def _validate_orders(o: DecisionOrders, date: str, universe: Sequence[str]) -> DecisionOrders:
    bad = sorted({i.ticker for i in o.intents} - set(universe))
    if o.date != date or bad:
        raise ValueError(f"invalid orders for {date}: dated {o.date}, tickers outside universe {bad}")
    return o


def _ctx(spec, pit, date: str, snap: PortfolioSnapshot, start: str | None) -> DecisionContext:
    return DecisionContext(
        as_of=date, universe=spec.universe, pit=BoundPit(pit, date), portfolio=snap,
        cfg=spec.to_wfconfig(), contaminated=start is not None and date < start,
    )


def _phase1(spec, decider, pit, dates, cache: Path, workers: int, start: str | None) -> dict[str, TargetBook]:
    cache.mkdir(parents=True, exist_ok=True)
    cash = spec.engine.start_cash
    books: dict[str, TargetBook] = {}
    todo = []
    for d in dates:
        path = cache / f"{d}.json"
        if path.exists():
            books[d] = _validate_book(TargetBook.model_validate_json(path.read_text()), d, spec.universe)
        else:
            todo.append(d)

    def work(d: str) -> TargetBook:
        snap = PortfolioSnapshot(as_of=d, equity=cash, cash=cash)
        return _validate_book(decider.decide(_ctx(spec, pit, d, snap, start)), d, spec.universe)

    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {pool.submit(work, d): d for d in todo}
        for fut in as_completed(futs):
            d = futs[fut]
            try:
                books[d] = fut.result()
            except Exception as exc:  # noqa: BLE001 finish the other dates, then raise
                log.error("decide %s failed: %s", d, exc)
                failures[d] = f"{type(exc).__name__}: {exc}"
                continue
            (cache / f"{d}.json").write_text(books[d].model_dump_json(indent=1))
    if failures:
        raise RuntimeError(f"{len(failures)} decision date(s) failed (rerun resumes): {failures}")
    return books


def _baseline_orders(name: str, spec, dates, closes, books) -> list[DecisionOrders] | None:
    tickers = list(spec.universe)
    if name == "equal_weight_buy_hold":
        return bl.equal_weight_buy_hold(dates, tickers)
    if name == "equal_weight_weekly":
        return bl.equal_weight_weekly(dates, tickers)
    if name == "spy_buy_hold":
        return bl.spy_buy_hold(dates, spec.reference)
    if name == "momentum_12_1_top5":
        return bl.momentum_rule(closes, dates, tickers)
    if name == "mechanical_seed":
        memos = {d: memos_of(b) for d, b in books.items()}
        if not any(memos.values()):
            log.warning("baseline mechanical_seed skipped: no analyst memos in TargetBook.provenance")
            return None
        w = {d: pm.seed_weights(pm.seed_scores(m, tickers)) for d, m in memos.items()}
        return bl.from_target_weights(w)
    raise ValueError(f"unknown baseline {name!r}")


def simulate(
    spec: RunSpec, run_dir: Path, *, pit, bars: dict[str, pd.DataFrame], rf: pd.Series,
    workers: int = 8, allow_contaminated: bool = False,
) -> Simulation:
    decider = registry.resolve("decider", spec.decider)
    execution = registry.resolve("execution", spec.execution)
    cfg, w = spec.to_wfconfig(), spec.window
    start = clean_start(spec.model_training_cutoff)
    dates = decision_dates(bars[spec.reference].index, w.first_decision, w.last_decision)
    if not dates:
        raise ValueError("no decision dates in the window")
    early = [d for d in dates if start is not None and d < start]
    if early and not allow_contaminated:
        raise ContaminatedRunError(f"{len(early)} decision(s) before clean start {start}; pass allow_contaminated")
    books = _phase1(spec, decider, pit, dates, run_dir / "books", workers, start) if decider.stateless else {}
    orders: dict[str, DecisionOrders] = {}

    def decision_fn(date: str, snap: PortfolioSnapshot) -> DecisionOrders | None:
        ctx = _ctx(spec, pit, date, snap, start)
        if date not in books:  # stateful decider: decide in the loop with the real account state
            books[date] = _validate_book(decider.decide(ctx), date, spec.universe)
        orders[date] = _validate_orders(execution.plan(ctx, books[date]), date, spec.universe)
        return orders[date]

    results = {PRIMARY: run_engine(bars, [], cfg, rf, dates[0], w.mark_end, decision_fn, dates)}
    closes = pd.DataFrame({t: b["close"] for t, b in bars.items()})
    for name in spec.baselines:
        dec = _baseline_orders(name, spec, dates, closes, books)
        if dec is not None:
            results[name] = run_engine(bars, dec, cfg, rf, dates[0], w.mark_end)
    return Simulation(results, dict(sorted(books.items())), orders, dates, closes, rf)


def _default_inputs(spec: RunSpec, pit, bars, rf):
    if bars is None:
        bars = market.load_bars(tickers=[*spec.universe, spec.reference])
    if rf is None:
        rf = market.rf_annual_pct(bars[spec.reference].index)
    if pit is None:
        from backend.app.wf.pit import PitData

        pit = PitData()
    return pit, bars, rf


def run_spec(
    spec: RunSpec, *, now_iso: str, pit=None, bars=None, out_root: Path | None = None, workers: int = 8,
    allow_contaminated: bool = False, rf: pd.Series | None = None, clock: Callable[[], str] | None = None,
) -> RunResult:
    """Run ``spec`` and write ``<out_root>/<spec_hash>/``. ``now_iso`` is the start time; ``clock``
    (optional) supplies the finish time. Re-running resumes from the cached TargetBooks."""
    pit, bars, rf = _default_inputs(spec, pit, bars, rf)
    run_dir = Path(out_root or DEFAULT_RUNS_ROOT) / spec.spec_hash()
    sim = simulate(spec, run_dir, pit=pit, bars=bars, rf=rf, workers=workers, allow_contaminated=allow_contaminated)
    rf_mean = float(rf.mean())
    universe = list(spec.universe)
    result = RunResult(
        spec_hash=spec.spec_hash(), spec=spec, label=label_for(spec), started_at=now_iso,
        finished_at=clock() if clock else now_iso, git_sha=_git_sha(),
        data_hashes=data_hashes(Path(pit.data_dir)) if getattr(pit, "data_dir", None) else {},
        metrics={k: strategy_metrics(r, rf_mean) for k, r in sim.results.items()},
        significance=significance_vs(sim.results),
        analyst_ic=analyst_ic(sim.books, sim.closes, universe),
        decisions=decision_index(sim.books, sim.orders),
    )
    write_run(run_dir, result, sim.results, sim.books, sim.orders)
    log.info("wrote %s (label %s)", run_dir, result.label)
    return result


def _resolve_run_dir(target: str | Path, out_root: Path | None) -> Path:
    p = Path(target)
    return p if p.is_dir() else Path(out_root or DEFAULT_RUNS_ROOT) / str(target)


def replay(
    target: str | Path, *, pit=None, bars=None, out_root: Path | None = None, workers: int = 8,
    rf: pd.Series | None = None, allow_contaminated: bool = False,
) -> float:
    """Re-run a stored run from its cached TargetBooks and compare every stored equity column.

    Returns the max abs difference; raises ReplayMismatch above 1e-9. Nothing is written."""
    run_dir = _resolve_run_dir(target, out_root)
    spec = RunSpec.model_validate_json((run_dir / "spec.json").read_text())
    pit, bars, rf = _default_inputs(spec, pit, bars, rf)
    sim = simulate(spec, run_dir, pit=pit, bars=bars, rf=rf, workers=workers, allow_contaminated=allow_contaminated)
    stored = pd.read_csv(run_dir / "equity.csv", index_col=0, parse_dates=True)
    new = equity_frame(sim.results)
    if list(stored.columns) != list(new.columns) or not stored.index.equals(new.index):
        raise ReplayMismatch(f"shape differs: stored {list(stored.columns)} vs new {list(new.columns)}")
    diff = float(np.abs(stored.to_numpy() - new.to_numpy()).max())
    if not diff <= REPLAY_TOL:
        raise ReplayMismatch(f"equity differs from stored run by up to {diff:.3e}")
    return diff
