"""Chart data from a fund's recorded desk state, recomputed with the engine that gated it.

Read-only: nothing here writes the desk. The P&L line is a replay of the registered strategy
(no live P&L series exists), recomputed with the engine recorded on the test result and
checked against the recorded total return.
"""

from __future__ import annotations

import csv
import math
from datetime import UTC, datetime

import pandas as pd

from backend.app import backtest as legacy_backtest
from backend.app import data
from backend.app.charts.models import (
    Allocation,
    Backtest,
    FundCharts,
    OrderRow,
    StrategyInfo,
    StrategyRow,
    Team,
)
from backend.app.desk import desk_for
from backend.app.schema import Weight
from backend.app.scores import sources as src

TOLERANCE = 1e-4
TEAM_COLUMNS = ("pipeline", "equal_weight_buy_hold", "spy_buy_hold")


def r6(values) -> list[float]:
    return [round(float(v), 6) for v in values]


def tested(desk) -> list[dict]:
    rows = [s for sid, s in desk.state["strategies"].items() if sid in desk.state["tests"]]
    return sorted(rows, key=lambda s: s.get("created_at") or "", reverse=True)


def pick_strategy(desk, strategy_id: str | None) -> dict | None:
    if strategy_id:
        return desk.state["strategies"][strategy_id]
    rows = tested(desk)
    return rows[0] if rows else None


def curves_wf(record: dict) -> tuple[dict, str]:
    from backend.app.wf.adapters.evaluators import WfEvaluator

    result = WfEvaluator(data_dir=None, normalize=False).evaluate(record["weights"], record["cutoff"], record["end"])
    note = "wf engine on data/wf: monthly rebalance to the frozen weights, next-open fills, slippage, price returns, cash earns the Fed funds rate."
    return result.equity, note


def curves_legacy(record: dict) -> tuple[dict, str]:
    window = data.prices_full(list(record["weights"]) + [data.REFERENCE])
    available_end = window.index.max().date().isoformat()
    if record["end"] > available_end:
        raise ValueError(f"snapshot ends {available_end}, before the strategy end {record['end']}")
    weights = [
        Weight(ticker=t, weight=w, rationale="", changes_my_mind="", analyst_influence={})
        for t, w in record["weights"].items()
    ]
    equity, _ = legacy_backtest.backtest(
        weights, record["cutoff"], record["end"], baseline="spy", universe=list(record["weights"]), closes=window
    )
    note = "legacy engine on data/prices: monthly rebalance, no costs, price returns, data ends 2025-06-30."
    return {"dates": equity.dates, "portfolio": equity.portfolio, "equal_weight": equity.equal_weight, "spy": equity.spy}, note


def drawdown(values: list[float]) -> list[float]:
    series = pd.Series(values, dtype=float)
    return r6((series / series.cummax() - 1).clip(upper=0))


def monthly(dates: list[str], portfolio: list[float], benchmark: list[float]) -> list[dict]:
    frame = pd.DataFrame({"p": portfolio, "b": benchmark}, index=pd.to_datetime(dates))
    last = frame.groupby(frame.index.to_period("M")).last()
    start = frame.iloc[[0]].set_axis([last.index[0] - 1])
    rets = pd.concat([start, last]).pct_change().dropna()
    return [
        {"month": str(period), "portfolio": round(float(row.p), 6), "benchmark": round(float(row.b), 6)}
        for period, row in rets.iterrows()
    ]


def thresholds(desk) -> dict:
    policy = desk.state.get("policy") or {}
    keys = ("max_drawdown", "min_sharpe", "min_excess_return", "max_position")
    return {k: policy.get(k) for k in keys}


def backtest_block(desk, record: dict, test: dict, capital: float, engine: str) -> Backtest:
    curves, note = (curves_wf if engine == "wf" else curves_legacy)(record)
    dates = list(curves["dates"])
    scale = capital
    portfolio = [v * scale for v in curves["portfolio"]]
    bench = [v * scale for v in curves["spy"]]
    equal = curves.get("equal_weight")
    recorded = test["metrics"]["portfolio"]["total_return"]
    recomputed = curves["portfolio"][-1] / curves["portfolio"][0] - 1
    consistent = math.isclose(recomputed, recorded, abs_tol=TOLERANCE)
    note += (
        f" Window {dates[0]} to {dates[-1]}. Recomputed total return {recomputed:.4%} "
        + ("matches" if consistent else f"DOES NOT match (mismatch {abs(recomputed - recorded):.4%} vs)")
        + f" the recorded {recorded:.4%}."
    )
    return Backtest(
        dates=dates,
        portfolio=r6(portfolio),
        benchmark=r6(bench),
        equal_weight=None if equal is None else r6([v * scale for v in equal]),
        drawdown=drawdown(portfolio),
        benchmark_drawdown=drawdown(bench),
        monthly=monthly(dates, portfolio, bench),
        metrics=test["metrics"],
        checks=test.get("checks"),
        thresholds=thresholds(desk),
        consistent=consistent,
        note=note,
    )


def team_block(capital: float, notes: list[str]) -> Team | None:
    run = src.walk_forward(src.WF_ROOT)
    path = run["dir"] / "results_all" / "equity.csv" if run else None
    if path is None or not path.is_file():
        notes.append("Team walk-forward run not present (reports/wf/final/results_all/equity.csv); no team series.")
        return None
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    first_col = next(iter(rows[0]))
    dates = [r[first_col] for r in rows]
    series = {c: r6(float(r[c]) / float(rows[0][c]) * capital for r in rows) for c in TEAM_COLUMNS}
    return Team(
        title="Team walk-forward pipeline (frozen run)",
        first=dates[0],
        last=dates[-1],
        dates=dates,
        series={"pipeline": series["pipeline"], "equal_weight_buy_hold": series["equal_weight_buy_hold"], "spy_buy_hold": series["spy_buy_hold"]},
        note=f"The team's walk-forward run ({run['dir'].name}), not this fund's strategy; scaled from its own start to this fund's capital.",
    )


def orders_block(desk) -> list[OrderRow]:
    rows = sorted(desk.state.get("orders", {}).values(), key=lambda o: o.get("time") or "")
    return [
        OrderRow(
            client_order_id=o["client_order_id"],
            symbol=o["symbol"],
            side=o["side"],
            notional=o["notional"],
            status=o.get("status"),
            time=o.get("time"),
        )
        for o in rows
    ]


def strategy_info(record: dict, test: dict | None) -> StrategyInfo:
    test = test or {}
    return StrategyInfo(
        id=record["id"],
        name=record["name"],
        author=record.get("author"),
        created_at=record.get("created_at"),
        cutoff=record["cutoff"],
        end=record["end"],
        verdict=test.get("verdict"),
        engine=test.get("engine", "legacy"),
        label=test.get("label"),
    )


def build_charts(fund_id: str, record: dict, manager, strategy_id: str | None = None) -> FundCharts:
    desk = desk_for(manager)
    capital = float(record.get("capital") or 0)
    notes: list[str] = []
    chosen = pick_strategy(desk, strategy_id)
    info = test = backtest = allocation = None
    if chosen is None:
        notes.append("No strategy with a recorded test yet; no backtest to draw.")
    else:
        test = desk.state["tests"].get(chosen["id"])
        info = strategy_info(chosen, test)
        allocation = Allocation(
            strategy_id=chosen["id"],
            weights=chosen["weights"],
            max_position=(desk.state.get("policy") or {}).get("max_position"),
        )
        if test is None:
            notes.append("This strategy has no recorded test; no backtest to draw.")
        else:
            try:
                backtest = backtest_block(desk, chosen, test, capital, info.engine)
            except (ValueError, KeyError, OSError) as exc:
                notes.append(f"Backtest could not be recomputed with the {info.engine} engine: {exc}")
    orders = orders_block(desk)
    if not orders:
        notes.append("No paper orders recorded for this fund.")
    if capital <= 0:
        notes.append("Fund capital is zero; dollar curves are zero.")
    return FundCharts(
        fund_id=fund_id,
        fund_name=record.get("name", fund_id),
        capital=capital,
        generated_at=datetime.now(UTC).isoformat(),
        strategy=info,
        strategies=[StrategyRow(id=s["id"], name=s["name"], created_at=s.get("created_at"), verdict=desk.state["tests"][s["id"]].get("verdict")) for s in tested(desk)],
        backtest=backtest,
        allocation=allocation,
        orders=orders,
        team=team_block(capital, notes),
        notes=notes,
    )
