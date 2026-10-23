"""Live market context for the pre-trade gate, from the same Alpaca paper credentials.

The venue's own data is the freshest answer to the questions the gate asks right before
an order: does Alpaca list this ticker as active and tradable, where did it last trade
against yesterday's close, is the market open, and what was the account's real equity
peak. Every call is read-only. When Alpaca is unreachable the gate falls back to the desk
snapshot and says so; the account snapshot in `paper.submit` already fails closed.
"""

from __future__ import annotations

import os
import threading
import time

import httpx
from dotenv import dotenv_values

from backend.app.watchdog.halt import REPO_ROOT
from backend.app.watchdog.models import LiveMarket

TRADING_URL = "https://paper-api.alpaca.markets"
DATA_URL = "https://data.alpaca.markets"
TTL_SECONDS = {"snapshots": 15, "asset": 600, "clock": 30, "history": 300}
CACHE: dict[tuple, tuple[float, object]] = {}
LOCK = threading.Lock()


def credentials() -> tuple[str, str] | None:
    settings = {
        **os.environ,
        **{k: v for k, v in dotenv_values(REPO_ROOT / ".env.local").items() if v is not None},
    }
    key = settings.get("ALPACA_API_KEY") or settings.get("APCA_API_KEY_ID")
    secret = settings.get("ALPACA_SECRET_KEY") or settings.get("APCA_API_SECRET_KEY")
    return (key, secret) if key and secret else None


def get(base: str, path: str, params: dict | None = None):
    keys = credentials()
    if not keys:
        raise ValueError("Alpaca paper credentials are not configured on the backend")
    with httpx.Client(base_url=base, timeout=8, follow_redirects=False) as client:
        response = client.get(
            path, params=params, headers={"APCA-API-KEY-ID": keys[0], "APCA-API-SECRET-KEY": keys[1]}
        )
    if response.status_code == 404:
        return None
    if response.is_error:
        raise ValueError(f"Alpaca returned HTTP {response.status_code} for {path}")
    return response.json()


def cached(kind: str, key: tuple, fetch):
    now = time.monotonic()
    with LOCK:
        hit = CACHE.get((kind, *key))
        if hit and now - hit[0] < TTL_SECONDS[kind]:
            return hit[1]
    value = fetch()
    with LOCK:
        CACHE[(kind, *key)] = (now, value)
    return value


def asset(symbol: str) -> dict | None:
    return cached("asset", (symbol,), lambda: get(TRADING_URL, f"/v2/assets/{symbol}"))


def snapshots(symbols: list[str]) -> dict:
    joined = ",".join(sorted(set(symbols)))
    return cached(
        "snapshots", (joined,), lambda: get(DATA_URL, "/v2/stocks/snapshots", {"symbols": joined, "feed": "iex"}) or {}
    )


def clock() -> dict:
    return cached("clock", (), lambda: get(TRADING_URL, "/v2/clock"))


def equity_peak() -> float | None:
    history = cached(
        "history", (), lambda: get(TRADING_URL, "/v2/account/portfolio/history", {"period": "1M", "timeframe": "1D"})
    )
    values = [float(v) for v in (history or {}).get("equity") or [] if v is not None]
    return max(values) if values else None


def live_market(symbols: list[str]) -> LiveMarket:
    """Live context for the gate. Never raises; failures come back as `error`."""
    try:
        listed = {s: asset(s) for s in symbols}
        snaps = snapshots(symbols)
        last_trade, prev_close = {}, {}
        for s, snap in snaps.items():
            trade = (snap or {}).get("latestTrade") or {}
            prev = (snap or {}).get("prevDailyBar") or {}
            if trade.get("p"):
                last_trade[s] = float(trade["p"])
            if prev.get("c"):
                prev_close[s] = float(prev["c"])
        return LiveMarket(
            source="Alpaca paper trading API and IEX market data",
            tradable={s: bool(a and a.get("tradable") and a.get("status") == "active") for s, a in listed.items()},
            last_trade=last_trade,
            prev_close=prev_close,
            market_open=bool(clock().get("is_open")),
            equity_peak=equity_peak(),
        )
    except (ValueError, httpx.HTTPError) as error:
        return LiveMarket(source="unavailable", error=str(error))
