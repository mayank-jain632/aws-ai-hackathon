"""Tape sidecar: live prices for the universe, broadcast over a local WebSocket.

Wraps the GPL-3 Tradingview-ticker library in tape/vendor (see tape/NOTICE.md) and
re-publishes every quote update as one JSON message per symbol:

    {"symbol": "AAPL", "price": 231.4, "change_pct": 0.81, "ts": 1761235200}

Listen on ws://localhost:8765/tape. New clients get the latest known quote for every
symbol immediately on connect, then updates as they arrive. Outside market hours
TradingView still sends a snapshot per symbol, so the tape is never empty.

Run:  python tape/server.py            (prints each tick to stdout)
      python tape/server.py --quiet    (prints only connection events)

The UI falls back to GET /api/last-close from the backend when this socket is down.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from ticker import ticker  # noqa: E402  (GPL-3 vendored library)

SYMBOLS = [
    "NASDAQ:AAPL", "NASDAQ:MSFT", "NASDAQ:NVDA", "NASDAQ:AMZN", "NASDAQ:GOOGL",
    "NYSE:JPM", "NYSE:XOM", "NYSE:UNH", "NYSE:PG", "NYSE:CAT",
]
HOST, PORT, PATH = "localhost", 8765, "/tape"

QUIET = "--quiet" in sys.argv
latest: dict[str, dict] = {}
clients: set = set()
loop: asyncio.AbstractEventLoop | None = None


def on_tick(symbol: str, state: dict) -> None:
    """Called by the ticker library on its own thread for every quote update."""
    if not state.get("price"):
        return
    msg = {
        "symbol": symbol.split(":", 1)[-1],
        "price": float(state["price"]),
        "change_pct": float(state.get("changePercentage") or 0.0),
        "ts": int(state.get("time") or time.time()),
    }
    latest[msg["symbol"]] = msg
    if not QUIET:
        print(f"{msg['symbol']:5s} {msg['price']:>10.2f} {msg['change_pct']:+6.2f}%  ts={msg['ts']}", flush=True)
    if loop is not None:
        loop.call_soon_threadsafe(asyncio.ensure_future, broadcast(msg))


async def broadcast(msg: dict) -> None:
    if not clients:
        return
    data = json.dumps(msg)
    dead = []
    for ws in list(clients):
        try:
            await ws.send(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


async def handler(ws) -> None:
    path = getattr(getattr(ws, "request", None), "path", None) or getattr(ws, "path", PATH)
    if not str(path).startswith(PATH):
        await ws.close(code=1008, reason=f"use {PATH}")
        return
    clients.add(ws)
    print(f"client connected ({len(clients)} total)", flush=True)
    try:
        for msg in list(latest.values()):  # snapshot first
            await ws.send(json.dumps(msg))
        async for _ in ws:  # ignore anything the client sends; keep the socket open
            pass
    except Exception:
        pass
    finally:
        clients.discard(ws)
        print(f"client disconnected ({len(clients)} total)", flush=True)


async def main() -> None:
    global loop
    loop = asyncio.get_running_loop()
    async with websockets.serve(handler, HOST, PORT):
        print(f"tape: ws://{HOST}:{PORT}{PATH}  symbols={len(SYMBOLS)}", flush=True)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    tick = ticker(SYMBOLS)
    tick.cb = on_tick
    tick.start()  # background thread; registers SIGINT/SIGTERM handlers (main thread)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        tick.stop()
