"""Scripted watchdog demo: an oversized order is blocked, then the firm-wide stop halts everything.

Runs the real backend routes the canvas tools call (strategy registration, adversarial
review, blind backtest on the real price snapshot, human approval, executor order) in a
throwaway directory. Only the Alpaca broker is stubbed, so no order leaves this machine;
the stub account mirrors the connected paper account's $100,000 starting state. With AWS
credentials and no MOCK_AGENTS, the second opinion calls Bedrock and the watchdog sends its
verdicts to CloudWatch, EventBridge and AgentCore Memory; otherwise it says it ran in mock mode.

    MOCK_AGENTS=1 uv run python scripts/watchdog_demo.py --fast    # local, no AWS
    AWS_PROFILE=team4-toolkit WATCHDOG_AWS=1 uv run python scripts/watchdog_demo.py
                                                                  # Aaron's account, AWS on
Without --fast it pauses between steps.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRATCH = Path(tempfile.mkdtemp(prefix="watchdog-demo-"))
os.environ["WATCHDOG_DIR"] = str(SCRATCH / "firm")
os.environ["WATCHDOG_INTERVAL_SECONDS"] = "0"
os.environ.pop("APP_ACCESS_PASSWORD", None)

from fastapi.testclient import TestClient

from backend.app import agent as runtime
from backend.app import paper
from backend.app.main import app
from backend.app.watchdog import aws, feedback, monitor, opinion

UNIVERSE = ["AAPL", "MSFT", "JPM", "PG", "UNH", "XOM"]
STRATEGY = {
    "name": "Quality tilt",
    "weights": {"AAPL": 0.25, "MSFT": 0.25, "JPM": 0.25, "PG": 0.25},
    "cutoff": "2023-01-01",
    "end": "2024-12-31",
    "rationale": "Equal weight across four profitable large caps with strong balance sheets, from memos dated before the cutoff.",
    "memo_paths": ["memos/quality.md"],
    "changes_my_mind": "Margins compress for two straight quarters or leverage rises.",
}
CLIENTS = {
    "calder": {
        "name": "Calder Family Trust",
        "risk": "conservative",
        "capital": 100_000,
        "max_position": 25,
        "max_drawdown": 12,
    },
    "ridge": {
        "name": "Ridge Growth Partners",
        "risk": "aggressive",
        "capital": 100_000,
        "max_position": 30,
        "max_drawdown": 25,
    },
}
POLICY = {
    "universe": UNIVERSE,
    "max_position": 0.30,
    "max_drawdown": 0.25,
    "min_sharpe": 0.5,
    "min_excess_return": 0.0,
    "max_order_notional": 50_000,
    "max_daily_orders": 10,
    "trading_allowed": True,
    "approval_required": True,
}


def stub_account():
    cash = 100_000 - sum(o["notional"] for o in SUBMITTED)
    positions = {}
    for o in SUBMITTED:
        positions[o["symbol"]] = positions.get(o["symbol"], 0) + o["notional"]
    return {
        "paper": True,
        "account": {
            "status": "ACTIVE",
            "currency": "USD",
            "cash": str(cash),
            "equity": "100000",
            "buying_power": str(cash),
            "trading_blocked": False,
            "account_blocked": False,
        },
        "positions": [{"symbol": s, "qty": "1", "market_value": str(v)} for s, v in positions.items()],
        "open_orders": [],
    }


SUBMITTED: list[dict] = []


def stub_broker(method, path, body=None):
    SUBMITTED.append({"symbol": body["symbol"], "notional": float(body["notional"])})
    return {"id": f"stub-{len(SUBMITTED)}", "status": "accepted", "filled_qty": "0"}


paper.account_snapshot = stub_account
paper.broker = stub_broker


def say(text="", indent=0):
    for line in textwrap.wrap(text, 96) or [""]:
        print(" " * indent + line)


def step(title, fast):
    if not fast:
        input("\n[enter] ")
    print("\n" + "=" * 100)
    say(title)
    print("=" * 100)


FUND_IDS = {"calder": "ca1de4000000000a", "ridge": "41d9e0000000000b"}  # server-style IDs scope Memory per fund


def fund(key):
    root = SCRATCH / key
    manager = runtime.AgentManager(root=root)
    manager.fund_id = FUND_IDS[key]
    manager.token = f"token-{key}"
    for role in ["strategy", "adversarial", "backtester", "executor"]:
        manager.agents[role] = runtime.LocalAgent(manager, role, role.title(), "dexter", role)
    manager.context = json.dumps(
        {
            "fund_id": key,
            "mandate": {
                **CLIENTS[key],
                "universe": UNIVERSE,
                "min_cash": 0,
                "max_sector": 100,
                "exclusions": "",
                "rebalance": "monthly",
                "mode": "paper",
                "trading_allowed": True,
                "approval_required": True,
            },
        }
    )
    memo = root / "workspace" / "memos" / "quality.md"
    memo.parent.mkdir(parents=True, exist_ok=True)
    memo.write_text("Quality memo. Latest filings used: AAPL 10-K filed 2022-10-28, JPM 10-Q filed 2022-11-01.\n")
    return manager


def as_agent(manager, role):
    return {"X-Agent-Token": manager.token, "X-Agent-ID": role}


def use(manager):
    app.state.manager = manager
    if hasattr(app.state, "funds"):
        del app.state.funds


def prepare(http, manager):
    """The pipeline up to execution, through the same routes the canvas tools call."""
    use(manager)
    http.put("/api/desk/policy", json=POLICY).raise_for_status()
    sid = http.post("/api/internal/desk/strategy", json=STRATEGY, headers=as_agent(manager, "strategy")).json()["id"]
    http.post(
        "/api/internal/desk/review",
        json={"strategy_id": sid, "verdict": "APPROVE", "critique": "Checked dates, concentration and the cited memo; no hindsight found."},
        headers=as_agent(manager, "adversarial"),
    ).raise_for_status()
    manager.agents["backtester"].state["strategy_id"] = sid
    test = http.post("/api/internal/desk/backtest", json={"strategy_id": sid}, headers=as_agent(manager, "backtester")).json()
    http.post(f"/api/desk/strategies/{sid}/approve").raise_for_status()
    http.put("/api/desk/stop", json={"stopped": False, "reason": "Analyst cleared the desk for trading"}).raise_for_status()
    return sid, test


def order(http, manager, sid, symbol, notional, oid):
    use(manager)
    response = http.post(
        "/api/internal/desk/order",
        json={"strategy_id": sid, "symbol": symbol, "side": "buy", "notional": notional, "client_order_id": oid},
        headers=as_agent(manager, "executor"),
    )
    return response.status_code, response.json()


def show_order(label, status, body):
    say(f"Executor: {label}")
    if status == 200:
        say(f"-> SENT to the paper broker stub, status {body['status']} (stub id {body['broker_id']}).", 3)
    else:
        say("-> BLOCKED before the broker.", 3)
        say(body["detail"], 6)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true")
    fast = parser.parse_args().fast
    runtime.ROOT = SCRATCH
    calder, ridge = fund("calder"), fund("ridge")
    http = TestClient(app, base_url="http://localhost")

    step("1. Calder Family Trust: a conservative client. The pipeline produced an approved strategy.", fast)
    sid, test = prepare(http, calder)
    p, b = test["metrics"]["portfolio"], test["metrics"]["baseline"]
    say("Mandate: conservative risk band, $100,000 capital, 25% max per position, 12% max drawdown.")
    say(f"Strategy '{STRATEGY['name']}': {', '.join(f'{t} {w:.0%}' for t, w in STRATEGY['weights'].items())}.")
    say(
        f"Blind backtest on the real price snapshot, {STRATEGY['cutoff']} to {STRATEGY['end']}: "
        f"{p['total_return']:+.1%} vs SPY {b['total_return']:+.1%}, max drawdown {abs(p['max_drawdown']):.1%}, "
        f"Sharpe {p['sharpe']:.2f}. Backend verdict: {test['verdict']}. Adversarial review: APPROVE. Analyst approval: yes."
    )
    say("Everything upstream says go. The only thing left between the agent and the broker is the watchdog.")

    step("2. The executor agent tries to put $40,000 into MSFT for this conservative client.", fast)
    status, body = order(http, calder, sid, "MSFT", 40_000, "calder-msft-0001")
    show_order("buy $40,000 MSFT", status, body)
    flagged = [e for e in feedback.entries(calder.desk) if e["kind"] == "block"][-1]
    note = opinion.second_opinion(calder.desk, flagged)
    feedback.record_opinion(calder.desk, flagged["id"], note)
    say(f"Second opinion ({note['source']}): {note['explanation']}", 3)
    say(f"Suggested fix: {note['suggested_fix']}", 3)

    step("3. The executor adjusts and sends a right-sized order. The watchdog lets it through.", fast)
    status, body = order(http, calder, sid, "MSFT", 8_000, "calder-msft-0002")
    show_order("buy $8,000 MSFT", status, body)

    step("4. Something looks off. A person trips the firm-wide emergency stop.", fast)
    use(calder)
    http.put("/api/watchdog/halt", json={"halted": True, "reason": "Analyst halted all agent trading for review"}).raise_for_status()
    say("PUT /api/watchdog/halt -> halted. One flag, every fund. Agents cannot clear it.")
    ridge_sid, _ = prepare(http, ridge)
    status, body = order(http, calder, sid, "PG", 5_000, "calder-pg-0001")
    show_order("Calder Family Trust, buy $5,000 PG", status, body)
    status, body = order(http, ridge, ridge_sid, "AAPL", 5_000, "ridge-aapl-0001")
    show_order("Ridge Growth Partners (a different fund), buy $5,000 AAPL", status, body)

    step("5. What the other agents learn: watchdog/LESSONS.md in the fund's shared files.", fast)
    monitor.audit(calder.desk, opinions=False)
    print(feedback.lessons(calder.desk))
    http.put("/api/watchdog/halt", json={"halted": False, "reason": "Review finished"}).raise_for_status()
    say(f"Stop cleared by a person. Scratch files: {SCRATCH}")
    if aws.enabled():
        sent = aws.flush()
        say(f"AWS: verdicts, the stop and lessons {'were sent' if sent else 'are still sending'} to CloudWatch {aws.NAMESPACE}, EventBridge {aws.EVENT_SOURCE} and AgentCore Memory.")


if __name__ == "__main__":
    main()
