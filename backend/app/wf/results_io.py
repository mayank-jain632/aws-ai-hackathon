"""Writers for the standard run directory ``reports/wf/runs/<spec_hash>/`` (hub D22)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from backend.app.wf.engine import EngineResult
from backend.app.wf.interfaces import TargetBook
from backend.app.wf.results import RunResult
from backend.app.wf.schemas import DecisionOrders

DEFAULT_RUNS_ROOT = Path(__file__).resolve().parents[3] / "reports" / "wf" / "runs"
SCHEMA_NAME = "result.schema.json"


def equity_frame(results: Mapping[str, EngineResult]) -> pd.DataFrame:
    return pd.DataFrame({k: v.equity for k, v in results.items()})


def fills_frame(results: Mapping[str, EngineResult]) -> pd.DataFrame:
    parts = [r.fills.assign(strategy=name) for name, r in results.items() if len(r.fills)]
    cols = ["strategy", "date", "ticker", "side", "shares", "price", "kind", "slippage_cost"]
    return pd.concat(parts)[cols] if parts else pd.DataFrame(columns=cols)


def _summary_md(result: RunResult) -> str:
    rows = pd.DataFrame({k: v.model_dump() for k, v in result.metrics.items()}).T
    return (
        f"# Run {result.spec.name}\n\n"
        f"- spec_hash: `{result.spec_hash}`\n- label: **{result.label}**\n"
        f"- model: {result.spec.model_id} (training cutoff {result.spec.model_training_cutoff})\n"
        f"- window: {result.spec.window.first_decision} .. {result.spec.window.last_decision}, "
        f"marked to {result.spec.window.mark_end} ({len(result.decisions)} decisions)\n"
        f"- git_sha: {result.git_sha}\n\n## Metrics\n\n```\n{rows.round(4).to_string()}\n```\n\n"
        f"## Significance\n\n```json\n{json.dumps(result.significance, indent=1)}\n```\n"
    )


def write_run(
    run_dir: Path,
    result: RunResult,
    results: Mapping[str, EngineResult],
    books: Mapping[str, TargetBook],
    orders: Mapping[str, DecisionOrders],
) -> Path:
    """Write spec.json, result.json, equity.csv, fills.csv, decisions/<date>.json, summary.md."""
    (run_dir / "decisions").mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(result.spec.model_dump_json(indent=2))
    (run_dir / "result.json").write_text(result.model_dump_json(indent=2))
    equity_frame(results).to_csv(run_dir / "equity.csv")
    fills_frame(results).to_csv(run_dir / "fills.csv", index=False)
    skipped = results["strategy"].skipped if "strategy" in results else pd.DataFrame()
    for date, book in books.items():
        o = orders.get(date)
        day_skips = skipped[skipped["date"] == pd.Timestamp(date)] if len(skipped) else skipped
        payload = {
            "date": date,
            "book": book.model_dump(mode="json"),
            "orders": o.model_dump(mode="json") if o else None,
            "skipped": json.loads(day_skips.to_json(orient="records", date_format="iso")) if len(day_skips) else [],
        }
        (run_dir / "decisions" / f"{date}.json").write_text(json.dumps(payload, indent=1))
    (run_dir / "summary.md").write_text(_summary_md(result))
    return run_dir


def write_schema(path: Path | None = None) -> Path:
    """Export ``RunResult``'s JSON schema so other lanes consume results without our code."""
    out = path or DEFAULT_RUNS_ROOT / SCHEMA_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(RunResult.model_json_schema(), indent=2, sort_keys=True))
    return out
