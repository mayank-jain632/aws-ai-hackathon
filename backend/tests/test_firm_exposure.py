"""Firm-wide exposure roll-up: what counts as exposure, and the cross-fund findings."""

import pytest
from fastapi.testclient import TestClient

from backend.app import firm
from backend.app.agent import AgentManager
from backend.app.desk import Policy, StrategyInput, desk_for
from backend.app.firm import fund_exposure, roll_up, sector_of
from backend.app.routes.firm import collect


def mandate_record(**overrides):
    return {
        "name": "Client fund",
        "risk": "balanced",
        "status": "active",
        "mode": "paper",
        "capital": 100000.0,
        "max_position": 20.0,
        "max_sector": 40.0,
        "trading_allowed": True,
        **overrides,
    }


def desk_state(policy=None, strategies=(), orders=()):
    """A desk.json-shaped dict. `strategies` entries are (id, weights, approved, verdict).

    These exercise the aggregation directly. `StrategyInput` and `Desk.register` own the
    real weight-sum and mandate-limit validation, which the route test goes through.
    """
    state = {
        "policy": policy,
        "stop": True,
        "strategies": {},
        "reviews": {},
        "tests": {},
        "approvals": {},
        "orders": {},
        "events": [],
    }
    from backend.app.desk import digest

    stamp = digest(policy)
    for index, (sid, weights, approved, verdict) in enumerate(strategies):
        state["strategies"][sid] = {
            "id": sid,
            "weights": weights,
            "created_at": f"2026-10-23T1{index}:00:00+00:00",
        }
        state["tests"][sid] = {"verdict": verdict, "policy_hash": stamp}
        if approved:
            state["approvals"][sid] = stamp
    for record in orders:
        state["orders"][record["client_order_id"]] = record
    return state


def order(symbol, side, notional, status="filled", key=None):
    return {
        "symbol": symbol,
        "side": side,
        "notional": notional,
        "status": status,
        "client_order_id": key or f"{symbol}-{side}-{notional}-{status}",
    }


POLICY = {"universe": ["NVDA", "JPM"], "max_position": 0.2}


def test_only_approved_and_passing_strategies_count_as_intent():
    state = desk_state(
        POLICY,
        strategies=[
            ("old", {"NVDA": 0.10}, True, "PASS"),
            ("newer", {"NVDA": 0.15, "JPM": 0.05}, True, "PASS"),
            ("unapproved", {"XOM": 0.9}, False, "PASS"),
            ("failed", {"PG": 0.9}, True, "FAIL"),
        ],
    )
    exposure = fund_exposure("f1", mandate_record(), state)
    assert exposure["strategy_id"] == "newer"
    assert exposure["approved"] == {"NVDA": 15000.0, "JPM": 5000.0}
    assert exposure["proposed_strategies"] == 4


def test_unapproved_proposal_is_never_exposure():
    state = desk_state(POLICY, strategies=[("only", {"NVDA": 0.9}, False, "PASS")])
    exposure = fund_exposure("f1", mandate_record(), state)
    assert exposure["approved"] == {}
    assert exposure["strategy_id"] is None


def test_orders_net_sells_and_exclude_void_and_unresolved():
    state = desk_state(
        POLICY,
        orders=[
            order("NVDA", "buy", 9000),
            order("NVDA", "sell", 4000),
            order("JPM", "buy", 7000, status="rejected"),
            order("PG", "buy", 2500, status="unknown"),
            order("CAT", "buy", 1500, status="submitting"),
        ],
    )
    exposure = fund_exposure("f1", mandate_record(), state)
    assert exposure["committed"] == {"NVDA": 5000.0}
    assert {o["symbol"] for o in exposure["uncertain_orders"]} == {"PG", "CAT"}


def test_archived_fund_is_excluded_but_paused_capital_still_counts():
    funds = [
        fund_exposure("a", mandate_record(status="active"), desk_state(POLICY)),
        fund_exposure("p", mandate_record(status="paused"), desk_state(POLICY)),
        fund_exposure("z", mandate_record(status="archived"), desk_state(POLICY)),
    ]
    result = roll_up(funds)
    assert result["funds"] == 2
    assert result["archived_excluded"] == 1
    assert result["capital"] == 200000.0


def test_shared_account_cannot_cover_every_mandate():
    funds = [
        fund_exposure(f"f{i}", mandate_record(name=f"Client {i}"), desk_state(POLICY))
        for i in range(6)
    ]
    result = roll_up(funds, broker_equity=100000.0)
    capacity = next(f for f in result["findings"] if f["code"] == "capacity_oversubscribed")
    assert result["capital"] == 600000.0
    assert capacity["value"] == pytest.approx(6.0)
    assert "$600,000" in capacity["message"]


def test_approved_books_exceeding_the_one_account_are_critical():
    funds = [
        fund_exposure(
            f"f{i}",
            mandate_record(),
            desk_state(POLICY, strategies=[("s", {"NVDA": 0.2}, True, "PASS")]),
        )
        for i in range(4)
    ]
    result = roll_up(funds, broker_equity=50000.0)
    finding = next(f for f in result["findings"] if f["code"] == "approved_exceeds_account")
    assert finding["severity"] == "critical"
    assert finding["value"] == pytest.approx(80000.0)
    assert finding["limit"] == 50000.0
    # Critical findings sort ahead of warnings and notes.
    assert result["findings"][0]["severity"] == "critical"


def test_capacity_is_omitted_not_passed_when_the_account_is_unreadable():
    funds = [fund_exposure("f1", mandate_record(), desk_state(POLICY))]
    result = roll_up(funds, broker_equity=None)
    assert result["capacity_checked"] is False
    assert result["capacity_ratio"] is None
    assert not [f for f in result["findings"] if "capacity" in f["code"]]


def test_a_name_every_client_holds_is_flagged_without_inflating_the_fraction():
    funds = [
        fund_exposure(
            f"f{i}",
            mandate_record(),
            desk_state(POLICY, strategies=[("s", {"NVDA": 0.08}, True, "PASS")]),
        )
        for i in range(6)
    ]
    result = roll_up(funds)
    row = next(r for r in result["by_symbol"] if r["symbol"] == "NVDA")
    assert row["fund_count"] == 6
    # Six funds each at 8% of their own capital is 8% of combined capital, not 48%.
    assert row["firm_fraction"] == pytest.approx(0.08)
    shared = next(f for f in result["findings"] if f["code"] == "every_client_exposed")
    assert "All 6 funds" in shared["message"]
    # Inside every mandate's own 20% limit, so nothing is reported as a breach.
    assert not [f for f in result["findings"] if f["code"].startswith("mandate_drift")]
    top = next(f for f in result["findings"] if f["code"] == "top_firm_position")
    assert top["value"] == pytest.approx(0.08)


def test_compliant_funds_never_produce_an_aggregate_breach():
    """Each fund exactly at its own limit must not read as a firm-level breach.

    The capital-weighted ceiling equals the aggregate by construction here, so a rule
    comparing the two would fire on fully compliant books.
    """
    funds = [
        fund_exposure(
            "cautious",
            mandate_record(
                risk="conservative", capital=900000, max_position=10.0, max_sector=10.0
            ),
            desk_state(POLICY, strategies=[("s", {"NVDA": 0.10}, True, "PASS")]),
        ),
        fund_exposure(
            "bold",
            mandate_record(
                risk="aggressive", capital=100000, max_position=60.0, max_sector=60.0
            ),
            desk_state(POLICY, strategies=[("s", {"NVDA": 0.60}, True, "PASS")]),
        ),
    ]
    result = roll_up(funds)
    row = next(r for r in result["by_symbol"] if r["symbol"] == "NVDA")
    assert row["strictest_mandate_limit"] == pytest.approx(0.10)
    assert row["holder_fraction"] == pytest.approx(0.15)
    assert row["permitted_fraction"] == pytest.approx(0.15)
    assert not [f for f in result["findings"] if f["code"].startswith("mandate_drift")]


def test_orders_pushing_a_fund_past_its_own_mandate_are_reported_as_drift():
    funds = [
        fund_exposure(
            "f1",
            mandate_record(name="Hartley Trust", max_position=20.0),
            desk_state(POLICY, orders=[order("NVDA", "buy", 26000)]),
        )
    ]
    result = roll_up(funds)
    drift = next(f for f in result["findings"] if f["code"] == "mandate_drift_position")
    assert drift["value"] == pytest.approx(0.26)
    assert drift["limit"] == pytest.approx(0.20)
    assert "Hartley Trust holds 26.0% in NVDA" in drift["message"]


def test_sector_limit_is_checked_here_because_nothing_else_checks_it():
    funds = [
        fund_exposure(
            "f1",
            mandate_record(name="Reyes Endowment", max_position=20.0, max_sector=40.0),
            desk_state(
                POLICY,
                strategies=[
                    ("s", {"NVDA": 0.2, "MSFT": 0.2, "AAPL": 0.2, "JPM": 0.2, "PG": 0.2}, True, "PASS")
                ],
            ),
        )
    ]
    result = roll_up(funds)
    drift = next(f for f in result["findings"] if f["code"] == "mandate_drift_sector")
    assert "Information technology" in drift["subject"]
    assert drift["value"] == pytest.approx(0.60)
    assert drift["limit"] == pytest.approx(0.40)
    assert not [f for f in result["findings"] if f["code"] == "mandate_drift_position"]


def test_sectors_aggregate_and_unmapped_symbols_stay_visible():
    assert sector_of("nvda") == "Information technology"
    assert sector_of("TSLA") == firm.UNCLASSIFIED
    funds = [
        fund_exposure(
            "f1",
            mandate_record(),
            desk_state(
                POLICY,
                strategies=[
                    ("s", {"NVDA": 0.2, "MSFT": 0.2, "AAPL": 0.1, "TSLA": 0.1}, True, "PASS")
                ],
            ),
        )
    ]
    result = roll_up(funds)
    tech = next(b for b in result["by_sector"] if b["sector"] == "Information technology")
    assert tech["exposure"] == pytest.approx(50000.0)
    assert sorted(tech["symbols"]) == ["AAPL", "MSFT", "NVDA"]
    note = next(f for f in result["findings"] if f["code"] == "unclassified_symbols")
    assert "TSLA" in note["subject"]


def test_risk_bands_group_the_six_mandate_shape():
    bands = ["conservative", "conservative", "balanced", "balanced", "aggressive", "aggressive"]
    funds = [
        fund_exposure(f"f{i}", mandate_record(risk=band), desk_state(POLICY))
        for i, band in enumerate(bands)
    ]
    result = roll_up(funds)
    assert {b["risk"]: b["funds"] for b in result["by_risk_band"]} == {
        "conservative": 2,
        "balanced": 2,
        "aggressive": 2,
    }


def test_route_reads_every_real_fund_without_a_broker(tmp_path, monkeypatch):
    """End to end over the app's own fund store and real desks, broker unavailable."""
    import backend.app.funds as funds_module
    from backend.app import main

    monkeypatch.setattr(funds_module, "ROOT", tmp_path)
    monkeypatch.setattr(main, "AgentManager", lambda: AgentManager(root=tmp_path / ".local"))
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)

    def unavailable():
        raise ValueError("Alpaca paper credentials are not configured on the backend")

    monkeypatch.setattr("backend.app.routes.firm.account_snapshot", unavailable)
    with TestClient(main.app, base_url="http://localhost") as client:
        first = client.post(
            "/api/funds", json={"name": "Income fund", "risk": "conservative"}
        ).json()["id"]
        client.post(
            "/api/funds",
            json={"name": "Growth fund", "risk": "aggressive", "capital": 250000},
        )
        store = main.app.state.funds
        desk = desk_for(store.runtime(first))
        desk.set_policy(
            Policy(
                universe=["NVDA", "JPM"],
                max_position=0.5,
                max_drawdown=0.5,
                min_sharpe=-100,
                min_excess_return=-1,
                max_order_notional=5000,
                max_daily_orders=5,
            )
        )
        registered = desk.register(
            StrategyInput(
                name="Core",
                weights={"NVDA": 0.5, "JPM": 0.5},
                cutoff="2024-06-01",
                end="2025-06-30",
                rationale="Two-name placeholder book for the exposure roll-up test.",
                memo_paths=["workspace/memo.md"],
                changes_my_mind="A failing backtest or an adversarial rejection.",
            ),
            "strategist",
        )
        exposures = collect(store)
        assert {e["name"] for e in exposures} == {"Team 4 fund", "Income fund", "Growth fund"}
        # Registered but neither reviewed, tested nor approved, so it is not yet exposure.
        assert all(not e["approved"] for e in exposures)
        assert registered["id"] in desk.state["strategies"]
        body = client.get("/api/firm/exposure").json()
    assert body["capital"] == pytest.approx(450000.0)
    assert body["funds"] == 3
    assert body["capacity_checked"] is False
    assert "credentials are not configured" in body["broker_note"]


def test_route_refuses_worker_tokens(tmp_path, monkeypatch):
    import backend.app.funds as funds_module
    from backend.app import main

    monkeypatch.setattr(funds_module, "ROOT", tmp_path)
    monkeypatch.setattr(main, "AgentManager", lambda: AgentManager(root=tmp_path / ".local"))
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    with TestClient(main.app, base_url="http://localhost") as client:
        denied = client.get("/api/firm/exposure", headers={"x-agent-token": "anything"})
    assert denied.status_code == 403
    assert "Workers cannot" in denied.json()["detail"]
