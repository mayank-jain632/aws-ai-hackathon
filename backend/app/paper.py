"""Alpaca paper-only adapter. Brokerage credentials never enter model tool arguments."""

import json
import os
import threading

import httpx

from backend.app.desk import digest, stamp

PAPER_URL = "https://paper-api.alpaca.markets"
BROKER_LOCK = threading.RLock()


def broker(method, path, body=None):
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
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
