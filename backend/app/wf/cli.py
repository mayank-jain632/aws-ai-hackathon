"""Command line for the pluggable harness.

    uv run python -m backend.app.wf.cli run --spec specs/<file>.json [--workers N]
    uv run python -m backend.app.wf.cli replay <run_dir>
    uv run python -m backend.app.wf.cli list-components
    uv run python -m backend.app.wf.cli schema
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from backend.app.wf import registry
from backend.app.wf.harness import replay, run_spec
from backend.app.wf.results_io import write_schema
from backend.app.wf.runspec import RunSpec

log = logging.getLogger("wf.cli")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _load_builtin_components() -> None:
    """Import the adapters package (when present) so its registry names exist."""
    try:
        import backend.app.wf.adapters  # noqa: F401
    except ModuleNotFoundError as exc:
        if exc.name != "backend.app.wf.adapters":
            raise
        log.warning("backend.app.wf.adapters not installed; only module:Class refs resolve")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wf")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run a spec")
    run.add_argument("--spec", required=True)
    run.add_argument("--workers", type=int, default=8)
    run.add_argument("--out-root", default=None)
    run.add_argument("--allow-contaminated", action="store_true")
    rep = sub.add_parser("replay", help="re-run a stored run and compare equity to 1e-9")
    rep.add_argument("run_dir")
    rep.add_argument("--workers", type=int, default=8)
    rep.add_argument("--allow-contaminated", action="store_true")
    sub.add_parser("list-components")
    sch = sub.add_parser("schema", help="write the RunResult JSON schema")
    sch.add_argument("--path", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    _load_builtin_components()
    if args.cmd == "run":
        spec = RunSpec.model_validate_json(Path(args.spec).read_text())
        res = run_spec(
            spec, now_iso=_now(), clock=_now, workers=args.workers, allow_contaminated=args.allow_contaminated,
            out_root=Path(args.out_root) if args.out_root else None,
        )
        print(f"{res.spec_hash} label={res.label} strategy_return={res.metrics['strategy'].total_return:.4f}")
    elif args.cmd == "replay":
        diff = replay(args.run_dir, workers=args.workers, allow_contaminated=args.allow_contaminated)
        print(f"replay OK, max abs equity diff {diff:.3e}")
    elif args.cmd == "list-components":
        for kind in ("decider", "execution", "evaluator"):
            print(f"{kind}: {', '.join(registry.known(kind)) or '(none)'}")
    else:
        print(write_schema(Path(args.path) if args.path else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
