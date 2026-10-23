"""Fund-scoped historical orders using the existing WF fill/accounting engine.

This module has no broker client. Server callers supply an authenticated fund Desk.
Each mutation advances exactly one session; quotes never go beyond the saved clock.
The replay is a separate simulation, never a replacement backend evaluation/PASS.
"""
from __future__ import annotations

import json
import math
import re
from uuid import uuid4

import pandas as pd

from backend.app.desk import check_allocation, digest
from backend.app.wf import market
from backend.app.wf.config import WfConfig
from backend.app.wf.engine import run_engine
from backend.app.wf.schemas import DecisionOrders, OrderIntent


class HistoricalReplay:
    def __init__(self, desk, *, data_dir=None):
        self.desk = desk
        self.path = desk.path.parent / "historical-replay.json"
        self.data_dir = data_dir

    def _load(self):
        if not self.path.exists():
            raise ValueError("No historical replay has been started in this fund")
        return json.loads(self.path.read_text())

    def _save(self, state):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, allow_nan=False, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def _binding(self, state):
        sid = state["strategy_id"]
        strategy = self.desk.strategy(sid)
        evaluation = self.desk.state["tests"].get(sid, {})
        if (evaluation.get("evaluation_id") != state["evaluation_id"]
                or evaluation.get("engine") != "wf"
                or not self.desk.test_is_current(sid)
                or digest(strategy) != state["strategy_hash"]):
            raise ValueError("Historical replay requires its exact current frozen WF evaluation")
        if getattr(self.desk.manager, "paused", False):
            raise ValueError("Fund is paused")
        return strategy, evaluation

    def _bars(self, strategy):
        bars = market.load_bars(self.data_dir, list(strategy["weights"]))
        sessions = None
        for frame in bars.values():
            valid = frame.dropna().index
            sessions = valid if sessions is None else sessions.intersection(valid)
        sessions = sessions[(sessions >= pd.Timestamp(strategy["cutoff"])) & (sessions <= pd.Timestamp(strategy["end"]))].sort_values()
        if len(sessions) < 2:
            raise ValueError("Historical replay needs at least two complete common sessions")
        return bars, sessions

    def start(self, strategy_id: str, evaluation_id: str):
        with self.desk.lock:
            strategy = self.desk.strategy(strategy_id)
            state = {"replay_id": uuid4().hex, "strategy_id": strategy_id,
                     "evaluation_id": evaluation_id, "strategy_hash": digest(strategy)}
            self._binding(state)
            if self.path.exists():
                existing = self._load()
                if (existing["strategy_id"], existing["evaluation_id"]) != (strategy_id, evaluation_id):
                    raise ValueError("This fund already has a historical replay; inspect it instead of resetting history")
                return self.inspect(existing["replay_id"])
            _, sessions = self._bars(strategy)
            context = json.loads(getattr(self.desk.manager, "context", "") or "{}")
            capital = float(context.get("mandate", {}).get("capital", WfConfig().start_cash))
            if not math.isfinite(capital) or capital <= 0:
                raise ValueError("Historical virtual capital must be positive")
            state.update(clock=sessions[0].date().isoformat(), end=sessions[-1].date().isoformat(),
                         start=sessions[0].date().isoformat(), start_cash=capital,
                         orders=[], decisions=[],
                         cfg=WfConfig(start_cash=capital, rebalance_band=0).model_dump(mode="json"))
            state["ledger"] = self._view(state, strategy)
            self._save(state)
            return state["ledger"]

    def current(self):
        """Read-only UI view, including older ledgers after a new evaluation."""
        with self.desk.lock:
            if not self.path.exists():
                return None
            state = self._load()
            return self.inspect(state["replay_id"])

    def inspect(self, replay_id: str):
        with self.desk.lock:
            state = self._load()
            self._identity(state, replay_id)
            return state["ledger"]

    def _history_unchanged(self, state, strategy):
        if digest(self._view(state, strategy)) != digest(state["ledger"]):
            raise ValueError("Historical price/rate inputs changed; preserved ledger cannot be rewritten")

    @staticmethod
    def _identity(state, replay_id, clock=None):
        if state["replay_id"] != replay_id:
            raise ValueError("Unknown historical replay in this fund")
        if clock is not None and state["clock"] != clock:
            raise ValueError("Historical clock changed; inspect current state before ordering")

    def _view(self, state, strategy):
        bars, sessions = self._bars(strategy)
        clock = pd.Timestamp(state["clock"])
        quotes = {symbol: float(frame.loc[clock, "close"]) for symbol, frame in bars.items()}
        if state["clock"] == state["start"]:
            account = {"cash": state["start_cash"], "equity": state["start_cash"], "positions": {}, "shares": {}}
            fills, skips = [], []
            curve = [{"date": state["clock"], "equity": state["start_cash"]}]
        else:
            # Truncate every price input at the simulation clock, including engine-only data.
            limited = {symbol: frame.loc[:clock] for symbol, frame in bars.items()}
            index = sessions[sessions <= clock]
            rf = market.rf_annual_pct(index, self.data_dir)
            if rf.isna().any():
                raise ValueError("Historical rate unavailable at replay clock; refusing future backfill")
            result = run_engine(limited, [DecisionOrders.model_validate(x) for x in state["decisions"]],
                                WfConfig.model_validate(state["cfg"]), rf, state["start"], state["clock"])
            held = result.positions[result.positions["date"] == clock]
            shares = {row["ticker"]: float(row["shares"]) for row in held.to_dict("records")}
            positions = {symbol: quantity * quotes[symbol] for symbol, quantity in shares.items()}
            equity = float(result.equity.iloc[-1])
            account = {"cash": equity - sum(positions.values()), "equity": equity,
                       "positions": positions, "shares": shares}
            fills = [{**row, "date": pd.Timestamp(row["date"]).date().isoformat()} for row in result.fills.to_dict("records")]
            skips = [{**row, "date": pd.Timestamp(row["date"]).date().isoformat()} for row in result.skipped.to_dict("records")]
            curve = [{"date": d.date().isoformat(), "equity": float(value)} for d, value in result.equity.items()]
        orders = []
        for order in state["orders"]:
            matching = [fill for fill in fills if fill["date"] == order["fill_date"] and fill["ticker"] == order["symbol"]]
            skipped = [skip for skip in skips if skip["date"] == order["fill_date"] and skip["ticker"] in {order["symbol"], "*"}]
            filled_qty = sum(fill["shares"] for fill in matching)
            filled_notional = sum(fill["shares"] * fill["price"] for fill in matching)
            requested_qty = order["requested_notional"] / float(bars[order["symbol"]].loc[pd.Timestamp(order["decision_date"]), "close"])
            status = "unfilled" if not matching else ("simulated_partial_fill" if filled_qty < requested_qty - 1e-8 else "simulated_fill")
            orders.append({**order, "status": status, "filled_qty": filled_qty, "filled_notional": filled_notional, "fills": matching, "skipped": skipped})
        evaluation = self.desk.state["tests"][state["strategy_id"]]
        return {"mode": "historical_simulation", "source": "historical_simulation", "replay_id": state["replay_id"],
                "strategy_id": state["strategy_id"], "evaluation_id": state["evaluation_id"],
                "policy_hash": evaluation.get("policy_hash"), "policy_version": evaluation.get("policy_version"),
                "engine_version": evaluation.get("engine_version"), "label": evaluation.get("label"),
                "clock": state["clock"], "end": state["end"], "complete": state["clock"] == state["end"],
                "account": account, "quotes": quotes, "orders": orders, "fills": fills,
                "equity_curve": curve, "skipped": skips, "leakage": evaluation.get("leakage"),
                "assumptions": ["Historical simulation only; no Alpaca orders or broker fills.",
                                "Decision after close; fills at next session open with WF slippage and volume cap.",
                                "Notional sized at decision close; actual fill amount changes with gaps and slippage.",
                                "Cash earns the recorded as-of Fed funds rate; no dividends."]}

    def advance(self, replay_id: str, clock: str):
        with self.desk.lock:
            state = self._load()
            self._identity(state, replay_id, clock)
            strategy, _ = self._binding(state)
            self._history_unchanged(state, strategy)
            _, sessions = self._bars(strategy)
            future = sessions[sessions > pd.Timestamp(clock)]
            if not len(future):
                raise ValueError("Historical replay is complete")
            state["clock"] = future[0].date().isoformat()
            view = self._view(state, strategy)
            state["ledger"] = view
            self._save(state)
            return view

    def place_order(self, replay_id: str, clock: str, symbol: str, side: str,
                    notional: float, client_order_id: str):
        with self.desk.lock:
            state = self._load()
            self._identity(state, replay_id)
            strategy, _ = self._binding(state)
            request = {"clock": clock, "symbol": symbol, "side": side, "notional": notional}
            if not re.fullmatch(r"[a-zA-Z0-9_-]{8,48}", client_order_id):
                raise ValueError("Use a stable 8-48 character historical order ID")
            for old in state["orders"]:
                if old["id"] == client_order_id:
                    if old["request_hash"] != digest(request):
                        raise ValueError("Historical order ID already identifies a different request")
                    return state["ledger"]
            self._identity(state, replay_id, clock)
            if side not in {"buy", "sell"} or not math.isfinite(notional) or notional <= 0:
                raise ValueError("Historical order needs buy/sell and positive finite notional")
            if symbol not in strategy["weights"]:
                raise ValueError("Historical order is outside its frozen strategy")
            policy = self.desk.policy()
            if notional > policy.max_order_notional:
                raise ValueError("Historical order exceeds frozen policy notional limit")
            self._history_unchanged(state, strategy)
            view = state["ledger"]
            if view["complete"]:
                raise ValueError("Historical replay is complete")
            account = view["account"]
            current = account["positions"].get(symbol, 0)
            delta = notional if side == "buy" else -notional
            target = (current + delta) / account["equity"]
            if target < 0 or target > min(strategy["weights"][symbol], policy.max_position) + 1e-9:
                raise ValueError("Historical order violates frozen target or long-only holdings")
            if side == "buy" and notional > account["cash"]:
                raise ValueError("Historical virtual account has insufficient cash")
            projected = {s: value / account["equity"] for s, value in account["positions"].items()}
            projected[symbol] = target
            context = json.loads(getattr(self.desk.manager, "context", "") or "{}")
            check_allocation(projected, context.get("mandate"))
            _, sessions = self._bars(strategy)
            next_date = sessions[sessions > pd.Timestamp(clock)][0].date().isoformat()
            state["decisions"].append(DecisionOrders(date=clock, intents=[OrderIntent(ticker=symbol, target_weight=target, entry="market_open")]).model_dump(mode="json"))
            state["orders"].append({"id": client_order_id, "request_hash": digest(request), "decision_date": clock,
                                    "symbol": symbol, "side": side, "requested_notional": notional, "fill_date": next_date})
            state["clock"] = next_date
            result = self._view(state, strategy)
            state["ledger"] = result
            self._save(state)
            return result
