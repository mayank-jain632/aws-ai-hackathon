"""Run the walk-forward experiment: pipeline -> engine -> baselines -> statistics.

    uv run python -m backend.app.wf.runner --window dev --out reports/wf/dev1
    uv run python -m backend.app.wf.runner --window test --out reports/wf/test1

Stages are stateless, so every decision date runs in parallel (pipeline.run_all) and is cached
on disk. Ablations and baselines re-run only the deterministic engine.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.agents import pm
from backend.app.wf import baselines, evaluate, market, orders
from backend.app.wf.calendar import decision_dates
from backend.app.wf.config import WfConfig
from backend.app.wf.engine import EngineResult, run_engine
from backend.app.wf.llm import Llm
from backend.app.wf.pipeline import run_all, write_manifest
from backend.app.wf.pit import PitData
from backend.app.wf.schemas import DecisionOrders, DecisionRecord

log = logging.getLogger("wf.runner")
N_RANDOM = 500
STANCE_SIGN = {"long": 1.0, "neutral": 0.0, "avoid": -1.0}


def split_dates(dates: list[str], cfg: WfConfig, window: str) -> list[str]:
    if window == "dev":
        return dates[: cfg.dev_decisions]
    if window == "test":
        return dates[cfg.dev_decisions :]
    return dates


def window_end(dates: list[str], all_dates: list[str], cfg: WfConfig, window: str) -> str:
    """Dev ends at the first test decision (inclusive); test and all end at the mark date."""
    if window == "dev":
        return all_dates[cfg.dev_decisions]
    return cfg.mark_end


def _clear_protective(d: DecisionOrders) -> DecisionOrders:
    intents = [i.model_copy(update={"stop_price": None, "target_price": None}) for i in d.intents]
    return d.model_copy(update={"intents": intents})


def pipeline_variants(records: list[DecisionRecord], cfg: WfConfig) -> dict[str, list[DecisionOrders]]:
    """Same LLM outputs, different execution: used for the execution/strategy attribution."""
    full = [r.orders for r in records]
    naive = [orders.weights_only_orders(r.decision_date, r.plan, cfg, r.contaminated) for r in records]
    return {
        "pipeline": full,
        "pipeline_no_protective": [_clear_protective(d) for d in full],
        "pipeline_naive_execution": naive,
    }


def seed_baseline(records: list[DecisionRecord], cfg: WfConfig) -> list[DecisionOrders]:
    universe = list(cfg.universe)
    weights = {
        r.decision_date: pm.seed_weights(pm.seed_scores(r.memos, universe)) for r in records
    }
    return baselines.from_target_weights(weights)


def run_all_strategies(
    records: list[DecisionRecord],
    bars: dict,
    rf: pd.Series,
    cfg: WfConfig,
    dates: list[str],
    end: str,
) -> dict[str, EngineResult]:
    tickers, ref, start = list(cfg.universe), cfg.reference, dates[0]
    closes = pd.DataFrame({t: b["close"] for t, b in bars.items()})
    specs = {
        **pipeline_variants(records, cfg),
        "mechanical_seed": seed_baseline(records, cfg),
        "equal_weight_buy_hold": baselines.equal_weight_buy_hold(dates, tickers),
        "equal_weight_weekly": baselines.equal_weight_weekly(dates, tickers),
        "spy_buy_hold": baselines.spy_buy_hold(dates, ref),
        "momentum_12_1_top5": baselines.momentum_rule(closes, dates, tickers),
    }
    return {name: run_engine(bars, d, cfg, rf, start, end) for name, d in specs.items()}


def random_totals(bars: dict, rf: pd.Series, cfg: WfConfig, dates: list[str], end: str) -> list[float]:
    out = []
    for seed in range(N_RANDOM):
        dec = baselines.random_policy(dates, list(cfg.universe), seed, n_names=5)
        eq = run_engine(bars, dec, cfg, rf, dates[0], end).equity
        out.append(float(eq.iloc[-1] / eq.iloc[0] - 1))
    return out


def analyst_scores(records: list[DecisionRecord], universe: list[str]) -> dict[str, pd.DataFrame]:
    """Signed conviction per analyst (and the strategist's weight) as date x ticker frames."""
    rows: dict[str, dict[str, dict[str, float]]] = {}
    for r in records:
        for m in r.memos:
            slot = rows.setdefault(m.analyst, {}).setdefault(r.decision_date, {})
            for v in m.views:
                slot[v.ticker] = STANCE_SIGN[v.stance] * v.confidence
        rows.setdefault("strategy_weight", {})[r.decision_date] = {
            p.ticker: p.target_weight for p in r.plan.plans
        }
    return {k: pd.DataFrame(v).T.reindex(columns=universe).fillna(0.0) for k, v in rows.items()}


def research_ic(records: list[DecisionRecord], bars: dict, cfg: WfConfig, dates: list[str]) -> dict:
    closes = pd.DataFrame({t: bars[t]["close"] for t in cfg.universe})
    scores = analyst_scores(records, list(cfg.universe))
    out = {}
    for horizon, name in ((5, "1w"), (20, "4w")):
        fwd = evaluate.forward_returns(closes, dates, horizon)
        for analyst, frame in scores.items():
            ic = evaluate.rank_ic(frame, fwd)
            out[f"{analyst}@{name}"] = {"mean_ic": ic.mean, "t_stat": ic.t_stat, "hit_rate": ic.hit_rate, "n": ic.n}
    return out


def significance(results: dict[str, EngineResult], rand: list[float]) -> dict:
    strat = results["pipeline"]
    out = {}
    for base in ("equal_weight_buy_hold", "spy_buy_hold", "mechanical_seed", "momentum_12_1_top5"):
        ci = evaluate.paired_excess_ci(strat.weekly_returns, results[base].weekly_returns)
        sd = evaluate.sharpe_diff_ci(strat.weekly_returns, results[base].weekly_returns)
        out[f"vs_{base}"] = {
            "excess_weekly_mean": ci.mean, "excess_lo": ci.lo, "excess_hi": ci.hi, "p_le_zero": ci.p_le_zero,
            "sharpe_diff": sd.mean, "sharpe_diff_lo": sd.lo, "sharpe_diff_hi": sd.hi,
        }
    total = float(strat.equity.iloc[-1] / strat.equity.iloc[0] - 1)
    out["random_policy_percentile"] = evaluate.random_policy_percentile(total, rand)
    out["random_policy_n"] = len(rand)
    return out


def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (np.floating, np.integer)):
        return float(obj)
    return obj


def write_outputs(out: Path, results: dict[str, EngineResult], rf: pd.Series, stats: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    table = evaluate.attribution_table(results, float(rf.mean()))
    table.to_csv(out / "attribution.csv")
    pd.DataFrame({k: v.equity for k, v in results.items()}).to_csv(out / "equity.csv")
    (out / "stats.json").write_text(json.dumps(_json_safe(stats), indent=1))
    (out / "summary.md").write_text(
        "# Walk-forward results\n\n```\n" + table.round(4).to_string() + "\n```\n\n```json\n"
        + json.dumps(_json_safe(stats), indent=1) + "\n```\n"
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--window", choices=["dev", "test", "all"], default="dev")
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--no-random", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)

    cfg, out = WfConfig(), Path(args.out)
    bars = market.load_bars(tickers=[*cfg.universe, cfg.reference])
    index = bars[cfg.reference].index
    all_dates = decision_dates(index, cfg.first_decision, cfg.last_decision)
    dates = split_dates(all_dates, cfg, args.window)
    end = window_end(dates, all_dates, cfg, args.window)
    log.info("%s window: %d decisions %s..%s, mark to %s", args.window, len(dates), dates[0], dates[-1], end)

    llm = Llm(cfg.model_id, temperature=cfg.temperature, max_tokens=cfg.max_tokens)
    records = run_all(PitData(), llm, cfg, dates, out, workers=args.workers)
    write_manifest(out, cfg, notes=[f"window={args.window}", f"llm={llm.stats()}"])

    rf = market.rf_annual_pct(index)
    results = run_all_strategies(records, bars, rf, cfg, dates, end)
    rand = [] if args.no_random else random_totals(bars, rf, cfg, dates, end)
    stats = {"window": args.window, "decisions": len(dates), "llm": llm.stats(),
             "significance": significance(results, rand) if rand else {},
             "research_ic": research_ic(records, bars, cfg, dates)}
    write_outputs(out / f"results_{args.window}", results, rf, stats)
    log.info("wrote %s", out / f"results_{args.window}")


if __name__ == "__main__":
    main()
