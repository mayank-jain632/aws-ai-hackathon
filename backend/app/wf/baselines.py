"""Baseline policies as DecisionOrders, fed through the same engine with the same costs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.app.wf.schemas import DecisionOrders, OrderIntent


def _decision(
    date: str, weights: dict[str, float], entry: str = "market_open"
) -> DecisionOrders:
    if sum(weights.values()) > 1 + 1e-9:
        raise ValueError(f"weights on {date} sum to {sum(weights.values()):.6f} > 1")
    intents = [
        OrderIntent(ticker=t, target_weight=float(w), entry=entry)
        for t, w in sorted(weights.items())
    ]
    return DecisionOrders(date=date, intents=intents)


def from_target_weights(
    dates_to_weights: dict[str, dict[str, float]], entry: str = "market_open"
) -> list[DecisionOrders]:
    """Mechanical baseline (e.g. pm.seed_weights): one decision per date, no stops."""
    return [_decision(d, dates_to_weights[d], entry) for d in sorted(dates_to_weights)]


def equal_weight_buy_hold(dates: list[str], tickers: list[str]) -> list[DecisionOrders]:
    """Primary baseline: equal weights at the first date only, never rebalanced."""
    return from_target_weights({min(dates): {t: 1 / len(tickers) for t in tickers}})


def equal_weight_weekly(dates: list[str], tickers: list[str]) -> list[DecisionOrders]:
    """Equal weights re-set on every decision date (the band suppresses tiny trades)."""
    return from_target_weights(
        {d: {t: 1 / len(tickers) for t in tickers} for d in dates}
    )


def spy_buy_hold(dates: list[str], ref: str = "SPY") -> list[DecisionOrders]:
    return from_target_weights({min(dates): {ref: 1.0}})


def _momentum(closes: pd.DataFrame, lookback: int, skip: int) -> pd.Series:
    """Price at t-skip over price at t-lookback, minus one; NaN when history is too short."""
    if len(closes) <= lookback:
        return pd.Series(np.nan, index=closes.columns)
    return closes.iloc[-1 - skip] / closes.iloc[-1 - lookback] - 1


def momentum_rule(
    closes: pd.DataFrame,
    dates: list[str],
    tickers: list[str],
    lookback: int = 252,
    skip: int = 21,
    top_n: int = 5,
) -> list[DecisionOrders]:
    """Top ``top_n`` by 12-1 month momentum, equal weight, rebalanced on each date.

    Only closes with index <= the decision date are read. A date with fewer than
    ``lookback``+1 sessions of history emits no decision (the book stays as is)."""
    out = []
    for d in sorted(dates):
        mom = _momentum(closes.loc[: pd.Timestamp(d), tickers], lookback, skip).dropna()
        if mom.empty:
            continue
        # stable tie-break by ticker so output is deterministic
        top = sorted(mom.sort_values(ascending=False, kind="stable").index[:top_n])
        weights = {t: (1 / len(top) if t in top else 0.0) for t in tickers}
        out.append(_decision(d, weights))
    return out


def random_policy(
    dates: list[str], tickers: list[str], seed: int, n_names: int
) -> list[DecisionOrders]:
    """Per date: draw ``n_names`` tickers uniformly, weights ~ Dirichlet(1); fully invested."""
    rng = np.random.default_rng(seed)
    weights = {}
    for d in sorted(dates):
        names = sorted(rng.choice(tickers, size=n_names, replace=False))
        drawn = dict(zip(names, rng.dirichlet(np.ones(n_names)).tolist(), strict=True))
        weights[d] = {
            t: drawn.get(t, 0.0) for t in tickers
        }  # zeros close names dropped this week
    return from_target_weights(weights)
