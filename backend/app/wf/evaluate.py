"""Evaluation statistics for the walk-forward backtest (pandas/numpy only)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from backend.app.backtest import metrics
from backend.app.schema import Metrics

if TYPE_CHECKING:  # engine imports this module; avoid a runtime cycle
    from backend.app.wf.engine import EngineResult

WEEKS_PER_YEAR = 52


@dataclass(frozen=True)
class BootCI:
    mean: float
    lo: float
    hi: float
    n: int
    p_le_zero: float  # share of bootstrap means <= 0 (one-sided p for "no edge")


@dataclass(frozen=True)
class RankIC:
    ic: pd.Series
    mean: float
    t_stat: float
    hit_rate: float
    n: int


def summarize(equity: pd.Series, rf_annual_pct: float | pd.Series = 0.0) -> Metrics:
    """backtest.metrics on the equity curve; a rf Series is averaged over the curve's dates."""
    if isinstance(rf_annual_pct, pd.Series):
        aligned = (
            rf_annual_pct.sort_index()
            .reindex(rf_annual_pct.index.union(equity.index))
            .ffill()
            .bfill()
        )
        rf = float(aligned.reindex(equity.index).mean())
    else:
        rf = float(rf_annual_pct)
    return metrics(equity, rf)


def weekly_returns(equity: pd.Series) -> pd.Series:
    """Return per ISO week (last mark of the week over the previous week's last mark), indexed
    by the week's last session. The first week is measured from the first equity point; if that
    week holds only the base point it is dropped."""
    if len(equity) < 2:
        return pd.Series(dtype=float)
    key = equity.index.to_period("W-SUN")
    last = equity.groupby(key).last()
    last_date = equity.index.to_series().groupby(key).last()
    prev = last.shift(1)
    prev.iloc[0] = float(equity.iloc[0])
    out = pd.Series(
        (last / prev - 1).to_numpy(), index=pd.DatetimeIndex(last_date.to_numpy())
    )
    if (key == key[0]).sum() == 1:
        out = out.iloc[1:]
    return out


def _block_indices(
    n: int, block: int, n_boot: int, rng: np.random.Generator
) -> np.ndarray:
    block = max(1, min(block, n))
    n_blocks = math.ceil(n / block)
    starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
    return (starts[:, :, None] + np.arange(block)).reshape(n_boot, -1)[:, :n]


def _align(a: pd.Series, b: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    both = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(both) < 2:
        raise ValueError("need at least two aligned weekly returns")
    return both.iloc[:, 0].to_numpy(), both.iloc[:, 1].to_numpy()


def paired_excess_ci(
    strategy_weekly: pd.Series,
    baseline_weekly: pd.Series,
    block: int = 4,
    n_boot: int = 2000,
    seed: int = 0,
) -> BootCI:
    """Moving-block bootstrap of the mean weekly excess return (strategy - baseline)."""
    s, b = _align(strategy_weekly, baseline_weekly)
    d = s - b
    idx = _block_indices(len(d), block, n_boot, np.random.default_rng(seed))
    means = d[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return BootCI(
        float(d.mean()), float(lo), float(hi), len(d), float((means <= 0).mean())
    )


def _sharpe(x: np.ndarray, rf_weekly: float) -> np.ndarray:
    sd = x.std(axis=-1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (x.mean(axis=-1) - rf_weekly) / sd * math.sqrt(WEEKS_PER_YEAR)
    return np.where(sd > 0, out, 0.0)


def sharpe_diff_ci(
    strategy_weekly: pd.Series,
    baseline_weekly: pd.Series,
    rf_weekly: float = 0.0,
    block: int = 4,
    n_boot: int = 2000,
    seed: int = 0,
) -> BootCI:
    """Paired block bootstrap of annualised (sqrt(52)) Sharpe(strategy) - Sharpe(baseline)."""
    s, b = _align(strategy_weekly, baseline_weekly)
    idx = _block_indices(len(s), block, n_boot, np.random.default_rng(seed))
    diffs = _sharpe(s[idx], rf_weekly) - _sharpe(b[idx], rf_weekly)
    point = float(_sharpe(s, rf_weekly) - _sharpe(b, rf_weekly))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return BootCI(point, float(lo), float(hi), len(s), float((diffs <= 0).mean()))


def random_policy_percentile(strategy_total_return: float, random_totals) -> float:
    """Percentile rank (0-100) of the strategy among random-policy totals; ties count half."""
    r = np.asarray(list(random_totals), dtype=float)
    if r.size == 0:
        raise ValueError("random_totals is empty")
    return float(
        100.0
        * ((r < strategy_total_return).sum() + 0.5 * (r == strategy_total_return).sum())
        / r.size
    )


def rank_ic(
    scores: pd.DataFrame, forward_returns: pd.DataFrame, min_names: int = 3
) -> RankIC:
    """Per-date Spearman correlation of scores (date x ticker) with forward returns."""
    rows = {}
    for d in scores.index.intersection(forward_returns.index):
        pair = pd.concat(
            [scores.loc[d], forward_returns.loc[d]], axis=1, join="inner"
        ).dropna()
        if len(pair) >= min_names:
            rho = pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank())
            if not np.isnan(rho):
                rows[d] = float(rho)
    ic = pd.Series(rows, dtype=float)
    n = len(ic)
    sd = float(ic.std(ddof=1)) if n > 1 else 0.0
    t = float(ic.mean() / (sd / math.sqrt(n))) if sd > 0 else 0.0
    return RankIC(
        ic, float(ic.mean()) if n else 0.0, t, float((ic > 0).mean()) if n else 0.0, n
    )


def forward_returns(
    closes: pd.DataFrame, dates: list[str], horizon_sessions: int
) -> pd.DataFrame:
    """Forward return per decision date and ticker, using ONLY closes strictly after the date.

    Entry is the close of the next session (t+1), exit the close ``horizon_sessions`` later
    (t+1+h): a conservative close-to-close proxy for filling at the next open. The decision
    date's own close is never used. Rows without a full horizon are NaN."""
    closes = closes.sort_index()
    out = {}
    for d in dates:
        pos = closes.index.searchsorted(
            pd.Timestamp(d), side="right"
        )  # first session > d
        if pos + horizon_sessions < len(closes):
            out[d] = closes.iloc[pos + horizon_sessions] / closes.iloc[pos] - 1
        else:
            out[d] = pd.Series(np.nan, index=closes.columns)
    return pd.DataFrame(out).T


def attribution_table(
    results: dict[str, EngineResult], rf_annual_pct: float = 0.0
) -> pd.DataFrame:
    """One row per named run: return, risk, costs, turnover and activity."""
    rows = {}
    for name, r in results.items():
        m = summarize(r.equity, rf_annual_pct)
        rows[name] = {
            "total_return": m.total_return,
            "cagr": m.cagr,
            "max_drawdown": m.max_drawdown,
            "sharpe": m.sharpe,
            "final_equity": float(r.equity.iloc[-1]),
            "costs": r.costs,
            "mean_weekly_turnover": float(r.turnover.mean())
            if len(r.turnover)
            else 0.0,
            "n_fills": len(r.fills),
            "n_skipped": len(r.skipped),
        }
    return pd.DataFrame(rows).T
