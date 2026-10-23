"""Firm-level exposure across every fund.

Each existing check is scoped to one fund: the desk policy, the fund mandate and the
watchdog's order gate all reason about a single account. Two things are therefore
invisible to every one of them.

First, capacity. One shared Alpaca paper account backs every fund, and each fund's cash
check reads that same balance, so several funds can each claim $100,000 of capital, and
each approve a book sized to it, against one $100,000 account.

Second, correlated client positioning. A name can sit inside all six mandates' own
single-name limits while every client holds it, so one issuer's drawdown reaches the
whole book at once and no per-fund view shows that. Note what this is not: if each fund
holds a name at 8% of its own capital, the firm total is also 8% of combined capital, not
48%. The signal is how many clients share the position and how far the firm total sits
from the most cautious exposed mandate, not an amplified percentage.

Exposure here is derived only from orders a fund actually recorded and from strategies a
person approved after a backend PASS. Nothing is assumed, simulated or carried forward
from a proposal. Limits are never invented: a firm total is compared against the
strictest limit the exposed mandates themselves set.

Money is dollars. Fractions are 0..1, so a mandate's `max_position: 20` becomes 0.20.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.desk import digest
from backend.app.wf.masking import SECTORS

# `SECTORS` is the one classification in the repo, from `backend/app/wf/masking.py`, and is
# what `desk.check_allocation`, `paper.submit` and `synthesis/orders.py` enforce against.
# Reused rather than redefined so a firm total can never disagree with a per-fund limit.
#
# One deliberate difference: those call sites fail closed on an unknown symbol, which is
# right for a gate that is about to trade. This is a read-only report, so an unmapped
# symbol becomes UNCLASSIFIED, is excluded from sector totals and is named in a finding.
# A missing label must not make the whole firm view unavailable.
UNCLASSIFIED = "Unclassified"

# A fund keeps its capital at risk while paused; an archived fund does not.
COUNTED_STATUSES = frozenset({"active", "paused"})

# Alpaca states. A recorded order that never reached the broker, or whose outcome we do
# not know, must not be counted as exposure or silently dropped.
VOID_STATUSES = frozenset({"canceled", "expired", "rejected", "blocked"})
UNCERTAIN_STATUSES = frozenset({"submitting", "unknown"})


def sector_of(symbol: str) -> str:
    return SECTORS.get(symbol.upper(), UNCLASSIFIED)


class Finding(BaseModel):
    code: str
    severity: str = Field(description="info, warn or critical")
    subject: str
    message: str
    value: float | None = None
    limit: float | None = None


def _approved_book(state: dict) -> tuple[dict[str, float], str | None]:
    """Weights of the newest strategy that holds a current human approval and PASS."""
    stamp = digest(state.get("policy"))
    live = [
        record
        for strategy_id, record in state.get("strategies", {}).items()
        if state.get("approvals", {}).get(strategy_id) == stamp
        and state.get("tests", {}).get(strategy_id, {}).get("verdict") == "PASS"
        and state.get("tests", {}).get(strategy_id, {}).get("policy_hash") == stamp
    ]
    if not live:
        return {}, None
    newest = max(live, key=lambda record: record.get("created_at", ""))
    return dict(newest["weights"]), newest["id"]


def _recorded_orders(state: dict) -> tuple[dict[str, float], list[dict]]:
    """Net notional per symbol from this fund's own order log, plus unresolved orders."""
    net: dict[str, float] = {}
    uncertain = []
    for record in state.get("orders", {}).values():
        status = str(record.get("status", "")).lower()
        if status in VOID_STATUSES:
            continue
        if status in UNCERTAIN_STATUSES:
            uncertain.append(
                {
                    "symbol": record["symbol"],
                    "side": record["side"],
                    "notional": record["notional"],
                    "status": status,
                    "client_order_id": record.get("client_order_id", ""),
                }
            )
            continue
        signed = record["notional"] if record["side"] == "buy" else -record["notional"]
        net[record["symbol"]] = net.get(record["symbol"], 0.0) + signed
    return {k: v for k, v in net.items() if abs(v) > 0.005}, uncertain


def fund_exposure(fund_id: str, record: dict, state: dict) -> dict:
    """One fund's exposure, separating what it traded from what it is approved to hold."""
    capital = float(record.get("capital") or 0)
    weights, strategy_id = _approved_book(state)
    committed, uncertain = _recorded_orders(state)
    return {
        "fund": fund_id,
        "name": record.get("name", fund_id),
        "risk": record.get("risk", "balanced"),
        "status": record.get("status", "active"),
        "mode": record.get("mode", "historical"),
        "capital": capital,
        "counted": record.get("status", "active") in COUNTED_STATUSES,
        "trading_allowed": bool(record.get("trading_allowed")),
        "max_position": float(record.get("max_position", 100)) / 100,
        "max_sector": float(record.get("max_sector", 100)) / 100,
        "strategy_id": strategy_id,
        "approved": {symbol: weight * capital for symbol, weight in weights.items()},
        "committed": committed,
        "uncertain_orders": uncertain,
        "proposed_strategies": len(state.get("strategies", {})),
    }


def _by_symbol(funds: list[dict], firm_capital: float) -> list[dict]:
    symbols = sorted({s for fund in funds for s in (*fund["approved"], *fund["committed"])})
    rows = []
    for symbol in symbols:
        holders = [
            fund for fund in funds if symbol in fund["approved"] or symbol in fund["committed"]
        ]
        approved = sum(fund["approved"].get(symbol, 0.0) for fund in holders)
        committed = sum(fund["committed"].get(symbol, 0.0) for fund in holders)
        rows.append(
            {
                "symbol": symbol,
                "sector": sector_of(symbol),
                "approved": approved,
                "committed": committed,
                "exposure": max(approved, committed),
                "funds": [
                    {
                        "fund": fund["fund"],
                        "name": fund["name"],
                        "risk": fund["risk"],
                        "approved": fund["approved"].get(symbol, 0.0),
                        "committed": fund["committed"].get(symbol, 0.0),
                        "own_weight": (
                            max(
                                fund["approved"].get(symbol, 0.0),
                                fund["committed"].get(symbol, 0.0),
                            )
                            / fund["capital"]
                            if fund["capital"]
                            else None
                        ),
                    }
                    for fund in holders
                ],
                "fund_count": len(holders),
                # The tightest single-name limit any exposed mandate set for itself.
                "strictest_mandate_limit": min(fund["max_position"] for fund in holders),
                "firm_fraction": (
                    max(approved, committed) / firm_capital if firm_capital else None
                ),
                **_against_mandates(
                    max(approved, committed), holders, lambda fund: fund["max_position"]
                ),
            }
        )
    return sorted(rows, key=lambda row: row["exposure"], reverse=True)


def _against_mandates(exposure: float, holders: list[dict], limit_of) -> dict:
    """Exposure over the exposed funds' own capital, and the ceiling those mandates imply.

    `permitted_fraction` is the capital-weighted average of the holders' own limits, which
    is the only like-for-like comparison for a capital-weighted exposure share. It is a
    reconciliation figure, not a threshold: if every fund sits exactly at its own limit the
    two are equal by construction, so the aggregate can exceed it only when some individual
    fund is already over its own mandate. That case is reported per fund as drift, and the
    aggregate numbers are reported without inventing a firm-level limit on top of them.
    """
    capital = sum(fund["capital"] for fund in holders)
    if not capital:
        return {"holder_capital": 0.0, "holder_fraction": None, "permitted_fraction": None}
    return {
        "holder_capital": capital,
        "holder_fraction": exposure / capital,
        "permitted_fraction": sum(
            fund["capital"] * limit_of(fund) for fund in holders
        )
        / capital,
    }


def _by_sector(symbol_rows: list[dict], funds: list[dict], firm_capital: float) -> list[dict]:
    sectors: dict[str, dict] = {}
    for row in symbol_rows:
        bucket = sectors.setdefault(
            row["sector"],
            {"sector": row["sector"], "exposure": 0.0, "symbols": [], "holders": {}},
        )
        bucket["exposure"] += row["exposure"]
        bucket["symbols"].append(row["symbol"])
        for holder in row["funds"]:
            bucket["holders"][holder["fund"]] = holder["fund"]
    exposed = {fund["fund"]: fund for fund in funds}
    for bucket in sectors.values():
        holders = [exposed[key] for key in bucket.pop("holders") if key in exposed]
        bucket["firm_fraction"] = bucket["exposure"] / firm_capital if firm_capital else None
        bucket["strictest_mandate_limit"] = min(
            (fund["max_sector"] for fund in holders), default=1.0
        )
        bucket.update(
            _against_mandates(bucket["exposure"], holders, lambda fund: fund["max_sector"])
        )
    return sorted(sectors.values(), key=lambda bucket: bucket["exposure"], reverse=True)


def _by_risk_band(funds: list[dict]) -> list[dict]:
    bands: dict[str, dict] = {}
    for fund in funds:
        bucket = bands.setdefault(
            fund["risk"],
            {"risk": fund["risk"], "funds": 0, "capital": 0.0, "approved": 0.0, "committed": 0.0},
        )
        bucket["funds"] += 1
        bucket["capital"] += fund["capital"]
        bucket["approved"] += sum(fund["approved"].values())
        bucket["committed"] += sum(fund["committed"].values())
    return sorted(bands.values(), key=lambda bucket: bucket["capital"], reverse=True)


def _capacity_findings(
    funds: list[dict], firm_capital: float, equity: float | None
) -> list[Finding]:
    """Compare what the funds collectively claim with what the one account actually holds.

    The limit is the account balance itself, so nothing here is an invented threshold.
    """
    if equity is None:
        return []
    out: list[Finding] = []
    approved = sum(sum(fund["approved"].values()) for fund in funds)
    committed = sum(sum(fund["committed"].values()) for fund in funds)
    if firm_capital > equity + 0.005:
        out.append(
            Finding(
                code="capacity_oversubscribed",
                severity="warn",
                subject="firm",
                message=(
                    f"{len(funds)} funds claim ${firm_capital:,.0f} of capital against one "
                    f"shared paper account holding ${equity:,.0f}. Each fund's own cash "
                    "check passes because they all read the same balance, so they cannot "
                    "all invest to their mandate."
                ),
                value=firm_capital / equity if equity else None,
                limit=1.0,
            )
        )
    if approved > equity + 0.005:
        out.append(
            Finding(
                code="approved_exceeds_account",
                severity="critical",
                subject="firm",
                message=(
                    f"Approved strategies across funds require ${approved:,.0f}, more than "
                    f"the ${equity:,.0f} in the shared account. Whichever fund executes "
                    "first consumes capital the others have already been approved to use."
                ),
                value=approved,
                limit=equity,
            )
        )
    if committed > equity + 0.005:
        out.append(
            Finding(
                code="committed_exceeds_account",
                severity="critical",
                subject="firm",
                message=(
                    f"Recorded orders across funds total ${committed:,.0f} against "
                    f"${equity:,.0f} of account equity, so the per-fund order logs no "
                    "longer reconcile with the one account they share."
                ),
                value=committed,
                limit=equity,
            )
        )
    return out


def _drift_findings(funds: list[dict]) -> list[Finding]:
    """A fund whose own exposure is past its own mandate limit.

    `desk.check_allocation` applies the cash reserve and sector cap at registration, and
    `paper.submit` and `synthesis/orders.py` apply them to projected holdings, so a compliant
    book produces nothing here. This is the backstop for the two cases those gates cannot
    see: recorded orders that moved a fund past a limit it satisfied at registration, and a
    mandate tightened after a book was approved.
    """
    out: list[Finding] = []
    for fund in funds:
        if not fund["capital"]:
            continue
        held = {
            symbol: max(fund["approved"].get(symbol, 0.0), fund["committed"].get(symbol, 0.0))
            for symbol in {*fund["approved"], *fund["committed"]}
        }
        for symbol, value in sorted(held.items()):
            weight = value / fund["capital"]
            if weight > fund["max_position"] + 1e-9:
                out.append(
                    Finding(
                        code="mandate_drift_position",
                        severity="warn",
                        subject=f"{fund['name']} / {symbol}",
                        message=(
                            f"{fund['name']} holds {weight:.1%} in {symbol}, past the "
                            f"{fund['max_position']:.0%} single-name limit in its own "
                            "mandate."
                        ),
                        value=weight,
                        limit=fund["max_position"],
                    )
                )
        sectors: dict[str, float] = {}
        for symbol, value in held.items():
            sectors[sector_of(symbol)] = sectors.get(sector_of(symbol), 0.0) + value
        for sector, value in sorted(sectors.items()):
            weight = value / fund["capital"]
            if sector != UNCLASSIFIED and weight > fund["max_sector"] + 1e-9:
                out.append(
                    Finding(
                        code="mandate_drift_sector",
                        severity="warn",
                        subject=f"{fund['name']} / {sector}",
                        message=(
                            f"{fund['name']} holds {weight:.1%} in {sector}, past the "
                            f"{fund['max_sector']:.0%} sector limit in its own mandate. "
                            "Registration and the order path enforce this, so recorded "
                            "orders drifted past it or the mandate was tightened after."
                        ),
                        value=weight,
                        limit=fund["max_sector"],
                    )
                )
    return out


def _findings(
    funds: list[dict],
    symbol_rows: list[dict],
    sector_rows: list[dict],
    firm_capital: float,
    equity: float | None,
) -> list[dict]:
    out: list[Finding] = _capacity_findings(funds, firm_capital, equity)
    out += _drift_findings(funds)
    for row in symbol_rows:
        if row["fund_count"] and row["fund_count"] == len(funds) > 1:
            out.append(
                Finding(
                    code="every_client_exposed",
                    severity="warn",
                    subject=row["symbol"],
                    message=(
                        f"All {len(funds)} funds are exposed to {row['symbol']}, so a move "
                        "in one issuer reaches every client at once. The largest single "
                        f"mandate weight is "
                        f"{max(f['own_weight'] or 0 for f in row['funds']):.1%} of that "
                        "fund's own capital."
                    ),
                    value=float(row["fund_count"]),
                    limit=float(len(funds)),
                )
            )
        if row["firm_fraction"] is None:
            continue
        if row is symbol_rows[0] and row["fund_count"] > 1:
            out.append(
                Finding(
                    code="top_firm_position",
                    severity="info",
                    subject=row["symbol"],
                    message=(
                        f"{row['symbol']} is the firm's largest position at "
                        f"{row['firm_fraction']:.1%} of combined fund capital "
                        f"(${row['exposure']:,.0f}) across {row['fund_count']} client(s). "
                        "No per-fund view shows this total."
                    ),
                    value=row["firm_fraction"],
                )
            )
        elif row["fund_count"] > 1:
            out.append(
                Finding(
                    code="cross_fund_overlap",
                    severity="info",
                    subject=row["symbol"],
                    message=(
                        f"{row['fund_count']} funds are exposed to {row['symbol']}; "
                        f"{row['firm_fraction']:.1%} of combined capital."
                    ),
                    value=row["firm_fraction"],
                    limit=row["strictest_mandate_limit"],
                )
            )
    for bucket in sector_rows[:1]:
        if bucket["sector"] != UNCLASSIFIED and bucket["firm_fraction"]:
            out.append(
                Finding(
                    code="top_firm_sector",
                    severity="info",
                    subject=bucket["sector"],
                    message=(
                        f"{bucket['sector']} is the firm's largest sector at "
                        f"{bucket['firm_fraction']:.1%} of combined fund capital "
                        f"({', '.join(sorted(bucket['symbols']))}). The most cautious "
                        f"exposed mandate allows itself "
                        f"{bucket['strictest_mandate_limit']:.0%} in one sector."
                    ),
                    value=bucket["firm_fraction"],
                    limit=bucket["strictest_mandate_limit"],
                )
            )
    unclassified = [row["symbol"] for row in symbol_rows if row["sector"] == UNCLASSIFIED]
    if unclassified:
        out.append(
            Finding(
                code="unclassified_symbols",
                severity="info",
                subject=", ".join(unclassified),
                message=(
                    "These symbols are outside the shared sector map, so sector "
                    "totals exclude them. Classify them before relying on a sector limit."
                ),
                value=float(len(unclassified)),
            )
        )
    unresolved = sum(len(fund["uncertain_orders"]) for fund in funds)
    if unresolved:
        out.append(
            Finding(
                code="unresolved_orders",
                severity="warn",
                subject="firm",
                message=(
                    f"{unresolved} recorded order(s) have no confirmed broker outcome, so "
                    "they are excluded from exposure. Firm totals are a lower bound until "
                    "they resolve."
                ),
                value=float(unresolved),
            )
        )
    order = {"critical": 0, "warn": 1, "info": 2}
    return [
        finding.model_dump()
        for finding in sorted(out, key=lambda finding: order.get(finding.severity, 3))
    ]


def roll_up(exposures: list[dict], broker_equity: float | None = None) -> dict:
    """Aggregate per-fund exposures into one firm view. Pure; no I/O.

    `broker_equity` is the shared paper account's equity, or None when the account could
    not be read. None means the capacity checks are omitted, not that they passed.
    """
    counted = [fund for fund in exposures if fund["counted"]]
    firm_capital = sum(fund["capital"] for fund in counted)
    symbol_rows = _by_symbol(counted, firm_capital)
    sector_rows = _by_sector(symbol_rows, counted, firm_capital)
    return {
        "capital": firm_capital,
        "funds": len(counted),
        "archived_excluded": len(exposures) - len(counted),
        "broker_equity": broker_equity,
        "capacity_ratio": (
            firm_capital / broker_equity if broker_equity else None
        ),
        "capacity_checked": broker_equity is not None,
        "approved_total": sum(sum(fund["approved"].values()) for fund in counted),
        "committed_total": sum(sum(fund["committed"].values()) for fund in counted),
        "by_symbol": symbol_rows,
        "by_sector": sector_rows,
        "by_risk_band": _by_risk_band(counted),
        "by_fund": counted,
        "findings": _findings(counted, symbol_rows, sector_rows, firm_capital, broker_equity),
        "basis": (
            "Committed exposure is each fund's own recorded broker orders, net of sells. "
            "Approved exposure is the newest strategy holding a current human approval and "
            "backend PASS, priced at the mandate's capital. Proposals and unresolved orders "
            "are excluded. One shared paper account backs every fund, so committed totals "
            "are firm-level already and cannot be attributed per fund beyond these records."
        ),
    }
