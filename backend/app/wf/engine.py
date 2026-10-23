"""Deterministic daily-bar market simulator for the walk-forward backtest (no LLM).

Timeline. A decision dated t is made after t's close (reference equity E_t marked at the
closes of t). Its orders go live at the open of the next session and stay live until the
next decision date. This module is the only place allowed to read future bars; an order
never looks at a bar dated on or before its decision date.

Conventions (pessimistic, documented where the contract is silent):
  * Equity series: the first point is the first decision date's close at exactly
    ``cfg.start_cash`` (base, nothing held); every later session is a mark-to-close.
  * Fractional shares. Price return only (dividends are not modelled).
  * Cash accrues ``rf/252`` per session (rf from ``rf_annual_pct`` as-of that date).
  * A decision replaces the protective orders of every ticker it names (None clears them)
    and expires all unfilled entry orders. Tickers it does not name keep position + stops.
  * Entry skip_if_gap_pct is checked only at the first live open. A limit entry stays live
    until the next decision; market_open entries only for the first session.
  * The volume cap applies to entries; the unfilled remainder lapses (logged). Protective
    exits are not volume-capped (assumed liquid; documented).
  * Same session, all entry fills happen at the open/limit before protective checks;
    stops are live in the entry bar (pessimistic). Sells fill first, buys are scaled down
    to the available cash. After a stop/target fill the position is flat and its protective
    orders and any pending entry for that ticker are cancelled until the next decision.
  * slippage_cost = shares * unslipped price * slippage_bps/1e4 (0 for limit fills).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.app.wf.config import WfConfig
from backend.app.wf.evaluate import weekly_returns
from backend.app.wf.interfaces import PortfolioSnapshot
from backend.app.wf.schemas import DecisionOrders, OrderIntent

FILL_COLS = ["date", "ticker", "side", "shares", "price", "kind", "slippage_cost"]
POS_COLS = ["date", "ticker", "shares", "weight"]
SKIP_COLS = ["date", "ticker", "reason", "detail"]
EPS = 1e-9


@dataclass(frozen=True)
class EngineResult:
    equity: pd.Series
    fills: pd.DataFrame
    positions: pd.DataFrame
    turnover: pd.Series
    costs: float
    weekly_returns: pd.Series
    skipped: pd.DataFrame


@dataclass
class _Order:
    ticker: str
    qty: float  # signed shares wanted
    kind: str  # market_open | limit
    limit: float | None
    ref_close: float
    gap: float | None
    first_date: pd.Timestamp | None


@dataclass
class _State:
    cash: float
    shares: dict[str, float]
    stop: dict[str, float | None] = field(default_factory=dict)
    target: dict[str, float | None] = field(default_factory=dict)
    pending: list[_Order] = field(default_factory=list)
    fills: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    def log(self, date, ticker, reason, detail="") -> None:
        self.skipped.append(
            {"date": date, "ticker": ticker, "reason": reason, "detail": detail}
        )


def _fill(state: _State, date, ticker, side, shares, price, kind, slip_cost) -> None:
    sign = 1.0 if side == "buy" else -1.0
    state.cash -= sign * shares * price
    state.shares[ticker] = state.shares.get(ticker, 0.0) + sign * shares
    state.fills.append(
        {
            "date": date,
            "ticker": ticker,
            "side": side,
            "shares": shares,
            "price": price,
            "kind": kind,
            "slippage_cost": slip_cost,
        }
    )


def _entry_price(
    order: _Order, bar: pd.Series, slip: float
) -> tuple[float, str, float] | None:
    """(price, kind, slippage_cost_per_share) if the order can trade in this bar, else None."""
    buy = order.qty > 0
    o = float(bar["open"])
    if order.kind == "market_open":
        px = o * (1 + slip) if buy else o * (1 - slip)
        return px, "market_open", o * slip
    lim = float(order.limit)  # type: ignore[arg-type]
    if buy and float(bar["low"]) <= lim:
        return min(o, lim), "limit", 0.0
    if not buy and float(bar["high"]) >= lim:
        return max(o, lim), "limit", 0.0
    return None


def _gap_cancelled(order: _Order, open_px: float) -> bool:
    if order.gap is None:
        return False
    if order.qty > 0:
        return open_px > order.ref_close * (1 + order.gap)
    return open_px < order.ref_close * (1 - order.gap)


def _plan_entries(state: _State, d, bars, slip: float, cap: float) -> list[tuple]:
    """Resolve which pending orders trade today -> list of (order, shares, price, kind, slipcost)."""
    plans, keep = [], []
    for o in state.pending:
        bar = bars[o.ticker].loc[d] if d in bars[o.ticker].index else None
        if bar is None or np.isnan(bar["open"]):
            keep.append(o)
            state.log(d, o.ticker, "no_bar", "ticker has no bar this session")
            continue
        first = o.first_date == d
        if first and _gap_cancelled(o, float(bar["open"])):
            state.log(
                d,
                o.ticker,
                "gap_cancel",
                f"open {bar['open']:.4f} vs ref {o.ref_close:.4f}",
            )
            continue
        quote = _entry_price(o, bar, slip)
        if quote is None:
            keep.append(o)  # limit not reached yet; stays live
            continue
        qty = abs(o.qty)
        if o.qty < 0:
            qty = min(qty, state.shares.get(o.ticker, 0.0))
        room = cap * float(bar["volume"])
        take = min(qty, room)
        if qty - take > EPS:
            state.log(
                d, o.ticker, "volume_cap", f"unfilled {qty - take:.4f} of {qty:.4f}"
            )
        if take > EPS:
            plans.append((o, take, *quote))
    state.pending = [
        o for o in keep if o.kind == "limit"
    ]  # only limits survive the first session
    return plans


def _execute_entries(state: _State, d, plans: list[tuple]) -> None:
    for o, qty, px, kind, sc in (p for p in plans if p[0].qty < 0):
        _fill(state, d, o.ticker, "sell", qty, px, kind, qty * sc)
    buys = [p for p in plans if p[0].qty > 0]
    cost = sum(qty * px for _, qty, px, _, _ in buys)
    scale = min(1.0, state.cash / cost) if cost > 0 else 1.0
    if scale < 1.0:
        state.log(d, "*", "cash_scaled", f"buys scaled by {scale:.6f}")
    for o, qty, px, kind, sc in buys:
        if qty * scale > EPS:
            _fill(state, d, o.ticker, "buy", qty * scale, px, kind, qty * scale * sc)
    if abs(state.cash) < 1e-6:
        state.cash = max(state.cash, 0.0)


def _protective(state: _State, d, bars, slip: float) -> None:
    for t in sorted(k for k, v in state.shares.items() if v > EPS):
        if d not in bars[t].index or np.isnan(bars[t].loc[d, "open"]):
            continue
        b = bars[t].loc[d]
        stop, tgt = state.stop.get(t), state.target.get(t)
        px = kind = None
        if stop is not None and b["low"] <= stop:
            px, kind = min(float(b["open"]), stop), "stop"
        elif tgt is not None and b["high"] >= tgt:
            px, kind = max(float(b["open"]), tgt), "target"
        if px is None:
            continue
        shares = state.shares[t]
        _fill(state, d, t, "sell", shares, px * (1 - slip), kind, shares * px * slip)
        state.stop[t] = state.target[t] = None
        state.pending = [o for o in state.pending if o.ticker != t]


def _equity(state: _State, closes: pd.Series) -> float:
    return state.cash + sum(
        s * float(closes[t]) for t, s in state.shares.items() if s > EPS
    )


def _make_order(
    state, d, nxt, intent: OrderIntent, e_t: float, close: float, cfg: WfConfig
) -> None:
    cur = state.shares.get(intent.ticker, 0.0)
    cur_w = cur * close / e_t
    if abs(intent.target_weight - cur_w) < cfg.rebalance_band:
        state.log(
            d,
            intent.ticker,
            "within_band",
            f"target {intent.target_weight:.4f} cur {cur_w:.4f}",
        )
        return
    if intent.entry == "limit" and intent.limit_price is None:
        state.log(d, intent.ticker, "missing_limit", "limit entry without limit_price")
        return
    qty = intent.target_weight * e_t / close - cur
    limit = intent.limit_price if intent.entry == "limit" else None
    state.pending.append(
        _Order(
            intent.ticker, qty, intent.entry, limit, close, intent.skip_if_gap_pct, nxt
        )
    )


def _apply_decision(
    state, d, nxt, dec: DecisionOrders, bars, closes: pd.Series, cfg: WfConfig
) -> None:
    for o in state.pending:
        state.log(d, o.ticker, "expired", "unfilled when next decision arrived")
    state.pending = []
    for reason in dec.blocked:
        state.log(d, "*", "blocked", reason)
    e_t = _equity(state, closes)
    for it in dec.intents:
        if it.ticker not in bars or np.isnan(closes.get(it.ticker, np.nan)):
            state.log(
                d,
                it.ticker,
                "no_price",
                "ticker has no bars/close at the decision date",
            )
            continue
        if it.entry == "skip":
            continue
        _make_order(state, d, nxt, it, e_t, float(closes[it.ticker]), cfg)
        zero = it.target_weight == 0.0
        state.stop[it.ticker] = None if zero else it.stop_price
        state.target[it.ticker] = None if zero else it.target_price


def _result(state, eq_rows, pos_rows, cfg) -> EngineResult:
    equity = pd.Series({d: v for d, v in eq_rows}, name="equity", dtype=float)
    fills = pd.DataFrame(state.fills, columns=FILL_COLS)
    positions = pd.DataFrame(pos_rows, columns=POS_COLS)
    skipped = pd.DataFrame(state.skipped, columns=SKIP_COLS)
    notional = (
        (fills["shares"] * fills["price"]).groupby(fills["date"]).sum()
        if len(fills)
        else pd.Series(dtype=float)
    )
    daily = notional.reindex(equity.index, fill_value=0.0) / equity.shift(1).fillna(
        cfg.start_cash
    )
    turnover = daily.groupby(equity.index.to_period("W-SUN")).sum()
    turnover.index = turnover.index.end_time.normalize()
    return EngineResult(
        equity=equity,
        fills=fills,
        positions=positions,
        turnover=turnover,
        costs=float(fills["slippage_cost"].sum()),
        weekly_returns=weekly_returns(equity),
        skipped=skipped,
    )


def _sessions(bars, start: str, end: str) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(sorted(set().union(*[set(b.index) for b in bars.values()])))
    return idx[(idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))]


def _snapshot(state: _State, d, eq: float, closes: pd.Series) -> PortfolioSnapshot:
    """Account state at the decision close, built only from the engine's own state."""
    held = {t: s for t, s in sorted(state.shares.items()) if s > EPS}
    return PortfolioSnapshot(
        as_of=pd.Timestamp(d).strftime("%Y-%m-%d"),
        equity=eq,
        cash=state.cash,
        positions={t: s * float(closes[t]) for t, s in held.items()},
        shares=dict(held),
        open_orders=(),
    )


def run_engine(
    bars: dict[str, pd.DataFrame],
    decisions: list[DecisionOrders],
    cfg: WfConfig,
    rf_annual_pct: pd.Series,
    start: str,
    end: str,
    decision_fn: Callable[[str, PortfolioSnapshot], DecisionOrders | None] | None = None,
    decision_dates: Sequence[str] | None = None,
) -> EngineResult:
    """Simulate ``decisions`` over [start, end]. ``start`` is the first decision date (the
    base equity point); decisions dated before it are ignored.

    Closed loop (optional): at each date in ``decision_dates`` (every session when None) that has
    no precomputed decision, after that session is marked at the close, ``decision_fn(date,
    snapshot)`` is called with the engine's own account state and its DecisionOrders (or None for
    no change) is applied exactly like a precomputed one. A precomputed decision wins on the same
    date and then ``decision_fn`` is not called. ``blocked`` reasons are logged as skipped."""
    bars = {t: b.sort_index() for t, b in bars.items()}
    sessions = _sessions(bars, start, end)
    if len(sessions) < 2:
        raise ValueError("fewer than two sessions between start and end")
    closes = (
        pd.DataFrame({t: b["close"] for t, b in bars.items()}).reindex(sessions).ffill()
    )
    rf = (
        rf_annual_pct.sort_index()
        .reindex(sessions.union(rf_annual_pct.index))
        .ffill()
        .bfill()
        .reindex(sessions)
    )
    by_date = {pd.Timestamp(x.date): x for x in sorted(decisions, key=lambda x: x.date)}
    fn_dates = None if decision_dates is None else {pd.Timestamp(x) for x in decision_dates}
    slip = cfg.slippage_bps / 1e4
    state = _State(cash=cfg.start_cash, shares={})
    eq_rows, pos_rows = [], []
    for i, d in enumerate(sessions):
        if i > 0:
            state.cash *= 1 + float(rf.iloc[i]) / 100 / 252
            _execute_entries(
                state,
                d,
                _plan_entries(state, d, bars, slip, cfg.volume_participation_cap),
            )
            _protective(state, d, bars, slip)
        eq = _equity(state, closes.iloc[i])
        eq_rows.append((d, eq))
        pos_rows += [
            {
                "date": d,
                "ticker": t,
                "shares": s,
                "weight": s * float(closes.iloc[i][t]) / eq,
            }
            for t, s in sorted(state.shares.items())
            if s > EPS
        ]
        if i + 1 >= len(sessions):
            continue
        dec = by_date.get(d)
        if dec is None and decision_fn is not None and (fn_dates is None or d in fn_dates):
            dec = decision_fn(d.strftime("%Y-%m-%d"), _snapshot(state, d, eq, closes.iloc[i]))
        if dec is not None:
            _apply_decision(state, d, sessions[i + 1], dec, bars, closes.iloc[i], cfg)
    return _result(state, eq_rows, pos_rows, cfg)
