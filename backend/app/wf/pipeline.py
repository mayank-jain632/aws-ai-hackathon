"""Per-date pipeline: research -> strategy -> execution -> orders, plus the parallel runner."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.agents import execution, strategy
from backend.app.schema import Memo
from backend.app.wf import analysts, orders
from backend.app.wf.config import WfConfig
from backend.app.wf.schemas import (
    DecisionRecord,
    ExecutionPlan,
    Manifest,
    OrderDraft,
    TickerPlan,
    TradePlan,
)

log = logging.getLogger("wf.pipeline")

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data" / "wf"


class ContaminatedDateError(ValueError):
    pass


def _guard(cfg: WfConfig, as_of: str, allow: bool) -> bool:
    """Returns the contaminated flag for this date; refuses early dates unless allowed."""
    early = as_of < cfg.clean_start
    if early and not allow:
        raise ContaminatedDateError(
            f"{as_of} is before clean_start {cfg.clean_start} (model cutoff {cfg.model_training_cutoff}); "
            "pass allow_contaminated=True for an explicitly labelled control run"
        )
    return early


# ------------------------------------------------------------------ masked-mode helpers


def _code_maps(
    masker: Any, universe: Sequence[str]
) -> tuple[dict[str, str], dict[str, str]]:
    to_code = {t: masker.encode(t) for t in universe}
    return to_code, {c: t for t, c in to_code.items()}


def _mask_memos(memos: list[Memo], to_code: dict[str, str]) -> list[Memo]:
    out = []
    for m in memos:
        views = [
            v.model_copy(update={"ticker": to_code.get(v.ticker, v.ticker)})
            for v in m.views
        ]
        out.append(m.model_copy(update={"views": views}))
    return out


def _unmask_plan(plan: TradePlan, to_ticker: dict[str, str]) -> TradePlan:
    plans: list[TickerPlan] = [
        p.model_copy(update={"ticker": to_ticker.get(p.ticker, p.ticker)})
        for p in plan.plans
    ]
    return plan.model_copy(update={"plans": plans})


def _unmask_exec(ep: ExecutionPlan, to_ticker: dict[str, str]) -> ExecutionPlan:
    drafts: list[OrderDraft] = [
        d.model_copy(update={"ticker": to_ticker.get(d.ticker, d.ticker)})
        for d in ep.orders
    ]
    return ep.model_copy(update={"orders": drafts})


# ------------------------------------------------------------------------ one decision


def _plan_and_execute(
    llm, cfg, as_of, memos, universe, ctx, masker
) -> tuple[TradePlan, ExecutionPlan, list[str]]:
    if masker is None:
        plan, notes = strategy.run_with_notes(llm, cfg, as_of, memos, universe, ctx)
        return plan, execution.run(llm, cfg, as_of, plan, ctx), notes
    to_code, to_ticker = _code_maps(masker, universe)
    codes = list(to_code.values())
    mctx = {to_code[t]: c for t, c in ctx.items() if t in to_code}
    mplan, notes = strategy.run_with_notes(
        llm, cfg, as_of, _mask_memos(memos, to_code), codes, mctx
    )
    mexec = execution.run(llm, cfg, as_of, mplan, mctx)
    return _unmask_plan(mplan, to_ticker), _unmask_exec(mexec, to_ticker), notes


def run_decision(
    pit: Any,
    llm: Any,
    cfg: WfConfig,
    as_of: str,
    universe: Sequence[str] | None = None,
    masker: Any = None,
    contaminated: bool = False,
) -> DecisionRecord:
    uni = list(universe or cfg.universe)
    if as_of < cfg.clean_start and not contaminated:
        raise ContaminatedDateError(
            f"{as_of} is before clean_start {cfg.clean_start}; mark contaminated=True"
        )
    memos, sources, abstained = analysts.run_research(pit, llm, as_of, uni, masker)
    ctx = pit.execution_context(as_of, uni)
    plan, exec_plan, notes = _plan_and_execute(llm, cfg, as_of, memos, uni, ctx, masker)
    decision_orders = orders.to_decision_orders(
        as_of, plan, exec_plan, ctx, cfg, contaminated, uni
    )
    return DecisionRecord(
        decision_date=as_of,
        contaminated=contaminated,
        model_id=getattr(llm, "model_id", cfg.model_id),
        memos=memos,
        abstained_analysts=abstained,
        sources=sources,
        plan=plan,
        execution=exec_plan,
        orders=decision_orders,
        masked=masker is not None,
        notes=notes,
    )


# ------------------------------------------------------------------------- all dates


def _record_path(out_dir: Path, as_of: str) -> Path:
    return out_dir / "decisions" / f"{as_of}.json"


def _write_record(out_dir: Path, rec: DecisionRecord) -> None:
    path = _record_path(out_dir, rec.decision_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(rec.model_dump_json(indent=2))
    tmp.replace(path)


def run_all(
    pit: Any,
    llm: Any,
    cfg: WfConfig,
    dates: Sequence[str],
    out_dir: str | Path,
    workers: int = 8,
    universe: Sequence[str] | None = None,
    masker: Any = None,
    allow_contaminated: bool = False,
    force: bool = False,
) -> list[DecisionRecord]:
    out = Path(out_dir)
    flags = {
        d: _guard(cfg, d, allow_contaminated) for d in dates
    }  # refuse before any work
    records: dict[str, DecisionRecord] = {}
    todo: list[str] = []
    for d in dates:
        path = _record_path(out, d)
        if path.exists() and not force:
            records[d] = DecisionRecord.model_validate_json(path.read_text())
        else:
            todo.append(d)
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {
            pool.submit(run_decision, pit, llm, cfg, d, universe, masker, flags[d]): d
            for d in todo
        }
        for fut in as_completed(futs):
            d = futs[fut]
            try:
                rec = fut.result()
            except Exception as exc:  # noqa: BLE001 collect, finish other dates, then raise
                log.error("decision %s failed: %s", d, exc)
                failures[d] = f"{type(exc).__name__}: {exc}"
                continue
            _write_record(out, rec)
            records[d] = rec
    if failures:
        raise RuntimeError(
            f"{len(failures)} decision date(s) failed (rerun resumes): {json.dumps(failures)[:1500]}"
        )
    return [records[d] for d in sorted(records)]


# ------------------------------------------------------------------------- manifest


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def prompt_hashes(cfg: WfConfig) -> dict[str, str]:
    hashes = {
        "analysts.house_style_and_suffix": _sha(
            analysts.HOUSE_STYLE + analysts.SYSTEM_SUFFIX
        ),
        "strategy.SYSTEM": _sha(strategy.build_system(cfg)),
        "execution.SYSTEM": _sha(execution.SYSTEM),
    }
    hashes.update({f"persona.{k}": _sha(v) for k, v in analysts.PERSONAS.items()})
    return hashes


def _git_sha() -> str | None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return res.stdout.strip() or None
    except Exception:  # noqa: BLE001 tolerate missing git
        return None


def data_hashes(data_dir: Path = DATA_DIR) -> dict[str, str]:
    if not data_dir.exists():
        return {}
    return {
        str(p.relative_to(data_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(data_dir.rglob("*"))
        if p.is_file()
    }


def write_manifest(
    out_dir: str | Path,
    cfg: WfConfig,
    run_id: str | None = None,
    contaminated: bool = False,
    notes: Sequence[str] = (),
    data_dir: Path = DATA_DIR,
) -> Manifest:
    out = Path(out_dir)
    hashes = prompt_hashes(cfg)
    manifest = Manifest(
        run_id=run_id or out.name,
        created=datetime.now(UTC).isoformat(timespec="seconds"),
        config=cfg.model_dump(),
        git_sha=_git_sha(),
        data_hashes=data_hashes(data_dir),
        prompt_hash=_sha(json.dumps(hashes, sort_keys=True)),
        window={
            "model_training_cutoff": cfg.model_training_cutoff,
            "clean_start": cfg.clean_start,
            "first_decision": cfg.first_decision,
            "last_decision": cfg.last_decision,
            "mark_end": cfg.mark_end,
            "dev_decisions": cfg.dev_decisions,
        },
        contaminated=contaminated,
        notes=[*notes, *(f"prompt:{k}={v}" for k, v in sorted(hashes.items()))],
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifest
