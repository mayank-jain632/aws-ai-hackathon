"""Memorization audit: named run vs masked run of the same pipeline (hub D15 rule 4).

    uv run python -m backend.app.wf.audit --window clean   --out reports/wf/audit_clean
    uv run python -m backend.app.wf.audit --window control --out reports/wf/audit_control

clean   : all 55 weekly decisions after the model cutoff (dev + test). Expectation: no gap.
control : 17 weekly decisions 2025-03-07..2025-06-27, BEFORE the cutoff (contaminated positive
          control, allow_contaminated=True). If the model leans on memory, named IC should beat
          masked IC here; this shows the test can detect leakage when it exists.

Per (series, horizon) we take the per-date rank IC of the signed analyst conviction (and of the
strategist weight) against the 1-week (5 session) and 4-week (20 session) forward returns, for
the named and the masked run, then a paired moving-block bootstrap (evaluate.paired_excess_ci,
block 4, 2000 resamples, seed 0) of the per-date difference (named IC - masked IC).

VERDICT RULE (mechanical, applied to the 95% CI [lo, hi] of the mean difference):
    lo > 0  -> "named better: possible memory effect"
    hi < 0  -> "masked better"
    else    -> "no detectable memory effect"
Nothing is tuned and nothing is hand-set. "No detectable effect" with few dates means low power,
not proof of absence; compare with the control window's verdicts.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.wf import evaluate, market
from backend.app.wf.calendar import decision_dates
from backend.app.wf.config import WfConfig
from backend.app.wf.masking import MaskedPit, Masker
from backend.app.wf.pipeline import run_all, write_manifest
from backend.app.wf.runner import analyst_scores, split_dates
from backend.app.wf.schemas import DecisionRecord

log = logging.getLogger("wf.audit")

HORIZONS: dict[str, int] = {"1w": 5, "4w": 20}
CONTROL_FIRST, CONTROL_LAST = "2025-03-07", "2025-06-27"
WEIGHT_GAP = 0.05
VERDICT_NAMED = "named better: possible memory effect"
VERDICT_MASKED = "masked better"
VERDICT_NONE = "no detectable memory effect"


def verdict(ci: evaluate.BootCI) -> str:
    if ci.lo > 0:
        return VERDICT_NAMED
    if ci.hi < 0:
        return VERDICT_MASKED
    return VERDICT_NONE


def window_dates(window: str, index: pd.DatetimeIndex, cfg: WfConfig) -> list[str]:
    if window == "control":
        return decision_dates(index, CONTROL_FIRST, CONTROL_LAST)
    all_dates = decision_dates(index, cfg.first_decision, cfg.last_decision)
    return split_dates(all_dates, cfg, "all")


def ic_series(
    records: list[DecisionRecord], closes: pd.DataFrame, universe: list[str], dates: list[str]
) -> dict[str, dict[str, pd.Series]]:
    """{series_name: {horizon_name: per-date rank IC}} for the analysts and strategy_weight."""
    scores = analyst_scores(records, universe)
    out: dict[str, dict[str, pd.Series]] = {k: {} for k in scores}
    for hname, h in HORIZONS.items():
        fwd = evaluate.forward_returns(closes, dates, h)
        for name, frame in scores.items():
            out[name][hname] = evaluate.rank_ic(frame, fwd).ic
    return out


def compare_row(named: pd.Series, masked: pd.Series) -> dict[str, Any]:
    ci = evaluate.paired_excess_ci(named, masked)
    return {
        "n_dates": ci.n,
        "named_ic": float(named.mean()) if len(named) else 0.0,
        "masked_ic": float(masked.mean()) if len(masked) else 0.0,
        "diff": ci.mean,
        "ci_lo": ci.lo,
        "ci_hi": ci.hi,
        "verdict": verdict(ci),
    }


def compare_runs(
    named: list[DecisionRecord],
    masked: list[DecisionRecord],
    closes: pd.DataFrame,
    universe: list[str],
    dates: list[str],
) -> list[dict[str, Any]]:
    a = ic_series(named, closes, universe, dates)
    b = ic_series(masked, closes, universe, dates)
    rows = []
    for name in sorted(a):
        for hname in HORIZONS:
            try:
                row = compare_row(a[name][hname], b[name][hname])
            except ValueError as exc:  # fewer than two aligned dates
                log.warning("%s@%s skipped: %s", name, hname, exc)
                continue
            rows.append({"series": name, "horizon": hname, **row})
    return rows


def agreement(
    named: list[DecisionRecord], masked: list[DecisionRecord], universe: list[str]
) -> dict[str, float]:
    """Decision-level agreement of the strategist's target weights, named vs masked."""
    frames = [analyst_scores(r, universe)["strategy_weight"] for r in (named, masked)]
    common = frames[0].index.intersection(frames[1].index)
    diff = (frames[0].loc[common] - frames[1].loc[common]).abs()
    return {
        "n_dates": len(common),
        "mean_abs_weight_diff": float(diff.to_numpy().mean()) if len(common) else 0.0,
        "share_weight_diff_gt_5pts": float((diff > WEIGHT_GAP).to_numpy().mean()) if len(common) else 0.0,
    }


def render_md(result: dict[str, Any]) -> str:
    lines = [
        f"# Memorization audit: {result['window']} window",
        "",
        (
            f"{result['n_dates']} weekly decisions ({result['first']} to {result['last']}); "
            f"model {result['model_id']}; contaminated control: {result['contaminated']}."
        ),
        (
            "IC = rank correlation of conviction with forward return. Difference = named IC "
            "minus masked IC, with a paired block-bootstrap 95% interval."
        ),
        "",
        "| series | horizon | dates | named IC | masked IC | difference | 95% CI | verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in result["rows"]:
        lines.append(
            f"| {r['series']} | {r['horizon']} | {r['n_dates']} | {r['named_ic']:+.3f} | "
            f"{r['masked_ic']:+.3f} | {r['diff']:+.3f} | [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}] | "
            f"{r['verdict']} |"
        )
    ag = result["agreement"]
    lines += [
        "",
        (
            "Strategist weights, named vs masked: mean absolute difference "
            f"{ag['mean_abs_weight_diff']:.3f}; share of ticker-weeks differing by more than 5 "
            f"points {ag['share_weight_diff_gt_5pts']:.1%} ({ag['n_dates']} dates)."
        ),
        "",
        (
            "Verdict rule: CI lower bound > 0 is named better; CI upper bound < 0 is masked "
            "better; otherwise no detectable memory effect (low power with few dates is not "
            "proof of absence)."
        ),
        "",
    ]
    return "\n".join(lines)


def run_audit(
    pit: Any, llm: Any, cfg: WfConfig, window: str, out: Path, bars: dict, workers: int = 8
) -> dict[str, Any]:
    universe = list(cfg.universe)
    index = bars[cfg.reference].index
    dates = window_dates(window, index, cfg)
    contaminated = window == "control"
    runs = {}
    masker = Masker(universe)
    for label, run_masker, run_pit in (
        ("named", None, pit),
        ("masked", masker, MaskedPit(pit, masker)),
    ):
        run_dir = out / label
        runs[label] = run_all(run_pit, llm, cfg, dates, run_dir, workers=workers,
                              masker=run_masker, allow_contaminated=contaminated)
        write_manifest(run_dir, cfg, contaminated=contaminated,
                       notes=[f"audit_window={window}", f"masked={run_masker is not None}"])
    closes = pd.DataFrame({t: bars[t]["close"] for t in universe})
    result = {
        "window": window, "n_dates": len(dates), "first": dates[0], "last": dates[-1],
        "model_id": getattr(llm, "model_id", cfg.model_id), "contaminated": contaminated,
        "rows": compare_runs(runs["named"], runs["masked"], closes, universe, dates),
        "agreement": agreement(runs["named"], runs["masked"], universe),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit.json").write_text(json.dumps(result, indent=1))
    (out / "audit.md").write_text(render_md(result))
    return result


def main() -> None:
    from backend.app.wf.llm import Llm
    from backend.app.wf.pit import PitData

    p = argparse.ArgumentParser()
    p.add_argument("--window", choices=["clean", "control"], required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    cfg = WfConfig()
    bars = market.load_bars(tickers=[*cfg.universe, cfg.reference])
    llm = Llm(cfg.model_id, temperature=cfg.temperature, max_tokens=cfg.max_tokens)
    result = run_audit(PitData(), llm, cfg, args.window, Path(args.out), bars, args.workers)
    log.info("wrote %s (%d rows); llm=%s", args.out, len(result["rows"]), llm.stats())


if __name__ == "__main__":
    main()
