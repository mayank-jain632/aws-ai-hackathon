"""Gate evaluation on the leakage-safe walk-forward engine (hub D22).

`evaluate_with_wf` has the same input and the same result shape as `Desk.evaluate` in
`backend/app/desk.py` (verdict, checks, metrics.portfolio / metrics.baseline, policy_hash), so the
rest of the desk (execution checks, audit, UI) works unchanged. What differs is the engine and
the honesty fields it adds:

    engine        "wf"
    label         model-clean | contaminated | unknown-cutoff, from the AUTHORING model's cutoff
    assumptions   monthly rebalance to the frozen weights, next-open fills, slippage, price return
    leakage       one plain-English statement of what the evaluator could and could not see

The evaluator input is weights and dates only; prices come from the point-in-time snapshot in
`data/wf`. Nothing here calls a model. The verdict is computed in code from human thresholds.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.app.wf import market
from backend.app.wf.adapters.evaluators import WfEvaluator
from backend.app.wf.model_cutoffs import training_cutoff
from backend.app.wf.runspec import clean_start

REFERENCE = "SPY"


def available_end(data_dir=None) -> str:
    bars = market.load_bars(data_dir=data_dir, tickers=[REFERENCE])
    return bars[REFERENCE].index.max().date().isoformat()


def window_label(cutoff: str, author_model: str | None) -> tuple[str, str | None]:
    """(label, model training cutoff). Clean only if the window starts after cutoff + buffer."""
    model_cutoff = training_cutoff(author_model)
    if model_cutoff is None:
        return "unknown-cutoff", None
    return ("model-clean" if cutoff >= clean_start(model_cutoff) else "contaminated"), model_cutoff


def leakage_statement(label: str, cutoff: str, author_model: str | None, model_cutoff: str | None) -> str:
    base = (
        "The evaluator received only frozen weights and dates; prices come from a point-in-time "
        "snapshot and no research reaches it. "
    )
    if label == "model-clean":
        return base + (
            f"The authoring model ({author_model}) uses the team-supplied training-cutoff assumption {model_cutoff}; "
            f"this window starts {cutoff}, after that cutoff plus a buffer month, so the model-clean label is conditional on that assumption. "
            "The cutoff is not independently verified and this does not prove absence of model memory."
        )
    if label == "contaminated":
        return base + (
            f"The authoring model ({author_model}, team-supplied training-cutoff assumption {model_cutoff}) may have seen this "
            f"window (starts {cutoff}); treat the result as an in-sample illustration, not evidence."
        )
    return base + (
        f"The authoring model ({author_model or 'not recorded'}) has no documented training cutoff, so "
        "this result is NOT labelled model-clean and cannot rule out memory of the test period."
    )


def _checks(weights: Mapping[str, float], policy: Any, portfolio: dict, benchmark: dict) -> dict:
    return {
        "drawdown": abs(portfolio["max_drawdown"]) <= policy.max_drawdown,
        "sharpe": portfolio["sharpe"] >= policy.min_sharpe,
        "excess_return": portfolio["total_return"] - benchmark["total_return"] >= policy.min_excess_return,
        "mandate": not (set(weights) - set(policy.universe)) and max(weights.values()) <= policy.max_position,
    }


def evaluate_with_wf(
    strategy_id: str,
    record: Mapping[str, Any],
    policy: Any,
    *,
    now: str,
    policy_hash: str,
    author_model: str | None = None,
    evaluator: WfEvaluator | None = None,
    data_dir=None,
) -> dict:
    cutoff, end, weights = record["cutoff"], record["end"], dict(record["weights"])
    last = available_end(data_dir)
    if end > last:
        raise ValueError(f"Snapshot ends {last}; refusing to silently shorten the test")
    result = (evaluator or WfEvaluator(data_dir=data_dir)).evaluate(weights, cutoff, end)
    portfolio, benchmark = result.portfolio.model_dump(), result.benchmark.model_dump()
    checks = _checks(weights, policy, portfolio, benchmark)
    label, model_cutoff = window_label(cutoff, author_model)
    return {
        "strategy_id": strategy_id,
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "metrics": {"portfolio": portfolio, "baseline": benchmark},
        "cutoff": cutoff,
        "end": end,
        "policy_hash": policy_hash,
        "time": now,
        "engine": "wf",
        "label": label,
        "author_model": author_model,
        "model_training_cutoff": model_cutoff,
        "assumptions": result.assumptions,
        "leakage": leakage_statement(label, cutoff, author_model, model_cutoff),
        "limitations": (
            "Leakage-safe walk-forward engine on a point-in-time snapshot: monthly rebalance to the frozen "
            "weights, next-open fills, slippage, price returns without dividends. Retro-scored and "
            "approximate. No statistical-significance claim; see the leakage field for the model-memory caveat."
        ),
    }
