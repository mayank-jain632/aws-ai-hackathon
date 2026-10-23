"""Synthetic bar helpers shared by the engine tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.app.wf.config import WfConfig
from backend.app.wf.schemas import DecisionOrders, OrderIntent

D0, D1, D2, D3 = (
    pd.Timestamp(x) for x in ("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05")
)
BIG = 1e9


def cfg(**kw) -> WfConfig:
    base = {
        "start_cash": 100_000.0,
        "slippage_bps": 5.0,
        "volume_participation_cap": 0.05,
        "rebalance_band": 0.01,
    }
    return WfConfig(**{**base, **kw})


def bars(rows: list[tuple]) -> pd.DataFrame:
    """rows of (date, open, high, low, close[, volume])."""
    recs = [
        {
            "date": r[0],
            "open": r[1],
            "high": r[2],
            "low": r[3],
            "close": r[4],
            "volume": r[5] if len(r) > 5 else BIG,
        }
        for r in rows
    ]
    return pd.DataFrame(recs).set_index("date")


def flat(date, px: float) -> tuple:
    return (date, px, px, px, px)


def rf(value: float = 0.0, start="2023-12-01", end="2024-12-31") -> pd.Series:
    return pd.Series(value, index=pd.date_range(start, end))


def dec(date, *intents: OrderIntent) -> DecisionOrders:
    return DecisionOrders(
        date=pd.Timestamp(date).strftime("%Y-%m-%d"), intents=list(intents)
    )


def buy(ticker: str, w: float, **kw) -> OrderIntent:
    return OrderIntent(ticker=ticker, target_weight=w, **kw)


def random_walk_bars(
    tickers: list[str], n: int, seed: int, vol: float = 0.02
) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=n)
    out = {}
    for t in tickers:
        close = 100 * np.cumprod(1 + rng.normal(0.0, vol, n))
        open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.003, n))
        high = np.maximum(open_, close) * 1.005
        low = np.minimum(open_, close) * 0.995
        out[t] = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": np.full(n, BIG),
            },
            index=idx,
        )
    return out
