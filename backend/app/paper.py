"""Alpaca paper-only adapter. Brokerage credentials never enter model tool arguments."""

import json
import math
import os
import threading
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

import httpx
from dotenv import dotenv_values

from backend.app.agent import ROOT
from backend.app.desk import digest, stamp
from backend.app.watchdog import gate as watchdog_gate

PAPER_URL = "https://paper-api.alpaca.markets"
BROKER_LOCK = threading.RLock()


def broker(method, path, body=None):
    settings = {
        **os.environ,
        **{
            k: v for k, v in dotenv_values(ROOT / ".env.local").items() if v is not None
        },
    }
    key = settings.get("ALPACA_API_KEY") or settings.get("APCA_API_KEY_ID")
    secret = settings.get("ALPACA_SECRET_KEY") or settings.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise ValueError("Alpaca paper credentials are not configured on the backend")
    with httpx.Client(base_url=PAPER_URL, timeout=20, follow_redirects=False) as client:
        response = client.request(
            method,
            path,
            json=body,
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        )
    if response.is_error:
        raise ValueError(
            f"Alpaca paper API rejected the request with HTTP {response.status_code}"
        )
    return response.json()


def account_snapshot():
    account = broker("GET", "/v2/account")
    return {
        "paper": True,
        "account": {
            k: account.get(k)
            for k in [
                "status",
                "currency",
                "cash",
                "equity",
                "buying_power",
                "trading_blocked",
                "account_blocked",
            ]
        },
        "positions": broker("GET", "/v2/positions"),
        "open_orders": broker("GET", "/v2/orders?status=open&limit=500"),
    }


def market_snapshot(symbols):
    """Fresh read through the existing Alpaca adapter, with no snapshot fallback."""
    from backend.app.watchdog import market

    snapshots = market.get(market.DATA_URL, "/v2/stocks/snapshots", {"symbols": ",".join(sorted(set(symbols))), "feed": "iex"})
    clock = market.get(market.TRADING_URL, "/v2/clock")
    if not isinstance(snapshots, dict) or not isinstance(clock, dict):
        raise TypeError("Alpaca market snapshot or clock is unavailable")
    retrieved = datetime.now(UTC)
    def age(item):
        try:
            timestamp = datetime.fromisoformat(item["t"])
            if timestamp.tzinfo is None:
                return None
            return round((retrieved - timestamp).total_seconds(), 3)
        except (KeyError, TypeError, ValueError):
            return None
    quotes = {}
    for symbol in symbols:
        snapshot = snapshots.get(symbol) or {}
        trade, quote_data = snapshot.get("latestTrade") or {}, snapshot.get("latestQuote") or {}
        quotes[symbol] = {"latest_trade": trade, "latest_quote": quote_data, "trade_age_seconds": age(trade), "quote_age_seconds": age(quote_data), "missing": not trade and not quote_data}
    return {"paper": True, "source": "Alpaca market data API", "feed": "iex", "feed_scope": "IEX venue subset; not consolidated SIP quotes", "retrieved_at": retrieved.isoformat(), "cache_used": False, "market_clock": clock, "symbols": quotes, "limitations": "Use exchange timestamps and ages to assess freshness; market closure may leave old last trades. Quotes are not guaranteed fill prices. Missing, stale or future timestamps are not current evidence. Broker-reported fills remain definitive."}


def submit(desk, body):
    with BROKER_LOCK, desk.lock:
        policy, strategy = desk.execution_checks(body.strategy_id)
        order_key = body.client_order_id
        request_hash = digest(body.model_dump())
        existing = desk.state["orders"].get(order_key)
        if existing:
            if existing["request_hash"] != request_hash:
                raise ValueError(
                    "client_order_id already identifies a different request"
                )
            return existing
        if body.symbol not in strategy["weights"]:
            raise ValueError("Order symbol is outside the passing strategy")
        if body.notional > policy.max_order_notional:
            raise ValueError("Order exceeds the human notional limit")
        today = stamp()[:10]
        if (
            sum(order["time"][:10] == today for order in desk.state["orders"].values())
            >= policy.max_daily_orders
        ):
            raise ValueError("Daily order limit reached")
        snapshot = account_snapshot()
        account = snapshot["account"]
        if (
            account["status"] != "ACTIVE"
            or account["trading_blocked"]
            or account["account_blocked"]
        ):
            raise ValueError("Alpaca paper account is not active for trading")
        if snapshot["open_orders"]:
            raise ValueError(
                "Wait for existing paper orders to resolve before submitting another"
            )
        watchdog_gate.enforce(desk, body, policy, snapshot)
        equity, cash = float(account["equity"]), float(account["cash"])
        context = json.loads(getattr(desk.manager, "context", "") or "{}")
        fund = context.get("mandate")
        capital = min(equity, fund["capital"]) if fund else equity
        positions = snapshot["positions"]
        if equity <= 0 or any(float(p["qty"]) < 0 for p in positions):
            raise ValueError(
                "Positive equity and long-only paper holdings are required"
            )
        market_value = sum(
            float(p["market_value"]) for p in positions if p["symbol"] == body.symbol
        )
        if body.side == "buy":
            cap = (
                min(
                    policy.max_position,
                    strategy["weights"][body.symbol],
                    fund["max_position"] / 100 if fund else 1,
                )
                * capital
            )
            if body.notional > cash or market_value + body.notional > cap + 0.01:
                raise ValueError(
                    "Buy would exceed cash, mandate position size, or frozen strategy target"
                )
        elif body.notional > market_value:
            raise ValueError("Sell would create a short position")
        if fund:
            if (
                sum(float(p["market_value"]) for p in positions)
                + (body.notional if body.side == "buy" else -body.notional)
                > fund["capital"]
            ):
                raise ValueError("Projected holdings exceed fund capital")
            if fund.get("max_sector", 100) < 100:
                raise ValueError(
                    "Sector-limit enforcement is not connected to the order adapter yet"
                )
        # Recheck immediately before the broker call, then persist intent before I/O.
        desk.execution_checks(body.strategy_id)
        record = {
            **body.model_dump(),
            "request_hash": request_hash,
            "time": stamp(),
            "status": "submitting",
            "paper": True,
        }
        desk.state["orders"][order_key] = record
        desk.event("paper_order_intent", record.copy())
        try:
            result = broker(
                "POST",
                "/v2/orders",
                {
                    "symbol": body.symbol,
                    "side": body.side,
                    "notional": f"{body.notional:.2f}",
                    "type": "market",
                    "time_in_force": "day",
                    "client_order_id": order_key,
                },
            )
        except (httpx.HTTPError, ValueError) as error:
            record.update(status="unknown", reason=str(error))
            desk.event("paper_order_uncertain", record.copy())
            return record
        record.update(
            status=result["status"],
            broker_id=result["id"],
            filled_qty=result.get("filled_qty"),
            filled_avg_price=result.get("filled_avg_price"),
        )
        desk.event("paper_order_response", record.copy())
        return record


def order_status(desk, client_order_id):
    """Reconcile a recorded fund order using GET only, even while stopped."""
    with BROKER_LOCK, desk.lock:
        record = desk.state["orders"].get(client_order_id)
        if record is None:
            raise ValueError("Unknown paper order in this fund")
        if record.get("broker_id"):
            path = "/v2/orders/" + quote(str(record["broker_id"]), safe="")
        else:
            # An uncertain POST may have succeeded. Look up the stable ID;
            # never submit again or generate another ID to resolve uncertainty.
            path = "/v2/orders:by_client_order_id?" + urlencode(
                {"client_order_id": client_order_id}
            )
        result = broker("GET", path)
        try:
            if not isinstance(result, dict):
                raise TypeError("Broker order response is not an order object")
            matches = (
                result.get("client_order_id") == client_order_id
                and result.get("symbol") == record["symbol"]
                and result.get("side") == record["side"]
                and bool(result.get("id"))
                and (not record.get("broker_id") or result["id"] == record["broker_id"])
                and math.isclose(
                    float(result["notional"]), record["notional"], abs_tol=0.005
                )
            )
            status = result.get("status")
            quantity = float(result.get("filled_qty") or 0)
            price = float(result.get("filled_avg_price") or 0)
            valid = (
                isinstance(status, str)
                and 0 < len(status) <= 64
                and status.isascii()
                and status.replace("_", "").isalnum()
                and math.isfinite(quantity)
                and quantity >= 0
                and math.isfinite(price)
                and price >= 0
                and (status != "filled" or (quantity > 0 and price > 0))
            )
        except (KeyError, TypeError, ValueError):
            matches, valid = False, False
        if not matches or not valid:
            raise ValueError(
                "Broker order response does not match the recorded order or fill"
            )
        previous_status = record["status"]
        record.update(
            status=status,
            broker_id=result["id"],
            filled_qty=result.get("filled_qty"),
            filled_avg_price=result.get("filled_avg_price"),
            filled_at=result.get("filled_at"),
            broker_updated_at=result.get("updated_at"),
            last_checked_at=stamp(),
        )
        if "reason" in record:
            record["previous_uncertainty"] = record.pop("reason")
        desk.event("paper_order_status", {"previous_status": previous_status, **record})
        return record.copy()
