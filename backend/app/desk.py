"""Server-owned strategy artifacts and gates. Kept outside the agents' shared files."""

import hashlib
import json
import math
import threading
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app import backtest, data
from backend.app.schema import Weight


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Policy(StrictModel):
    universe: list[str] = Field(min_length=1, max_length=15)
    max_position: float = Field(gt=0, le=1)
    max_drawdown: float = Field(gt=0, le=1)
    min_sharpe: float
    min_excess_return: float
    max_order_notional: float = Field(gt=0)
    max_daily_orders: int = Field(ge=1, le=100)
    trading_allowed: bool = False
    approval_required: bool = True

    @model_validator(mode="after")
    def valid_universe(self):
        if set(self.universe) - set(data.UNIVERSE) or len(set(self.universe)) != len(
            self.universe
        ):
            raise ValueError("Use unique tickers from the existing historical universe")
        return self


class StrategyInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    weights: dict[str, float] = Field(min_length=1, max_length=15)
    cutoff: date
    end: date
    rationale: str = Field(min_length=1, max_length=6000)
    memo_paths: list[str] = Field(min_length=1, max_length=30)
    changes_my_mind: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_strategy(self):
        if self.end <= self.cutoff or self.end > date.today():
            raise ValueError("Test end must be after cutoff and no later than today")
        if set(self.weights) - set(data.UNIVERSE):
            raise ValueError("Strategy contains unsupported historical tickers")
        if any(
            not math.isfinite(w) or w <= 0 or w > 1 for w in self.weights.values()
        ) or not math.isclose(sum(self.weights.values()), 1, abs_tol=1e-6):
            raise ValueError("Long-only weights must be positive and sum to one")
        return self


class ReviewInput(StrictModel):
    strategy_id: str
    verdict: Literal["APPROVE", "CHANGES_REQUESTED"]
    critique: str = Field(min_length=20, max_length=6000)


class OrderInput(StrictModel):
    strategy_id: str
    symbol: str
    side: Literal["buy", "sell"]
    notional: float = Field(ge=0.01, le=10000000)
    client_order_id: str = Field(
        min_length=8, max_length=48, pattern=r"^[a-zA-Z0-9_-]+$"
    )


def stamp():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Desk:
    def __init__(self, manager):
        self.manager = manager
        self.path = Path(manager.registry).parent / "desk.json"
        self.lock = threading.RLock()
        self.state = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {
                "policy": None,
                "stop": True,
                "strategies": {},
                "reviews": {},
                "tests": {},
                "approvals": {},
                "orders": {},
                "events": [],
            }
        )

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, allow_nan=False))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def event(self, check, result):
        self.state["events"].append({"time": stamp(), "check": check, "result": result})
        self.state["events"] = self.state["events"][-500:]
        self.save()

    def policy(self):
        if not self.state["policy"]:
            raise ValueError(
                "A person must configure the desk policy and test thresholds first"
            )
        return Policy.model_validate(self.state["policy"])

    def set_policy(self, policy):
        with self.lock:
            self.state["policy"] = policy.model_dump()
            self.state["approvals"] = {}
            self.state["stop"] = True
            self.event(
                "human_policy", "Policy updated; stop engaged and approvals invalidated"
            )

    def strategy(self, strategy_id):
        if strategy_id not in self.state["strategies"]:
            raise ValueError("Unknown strategy_id in this fund")
        return self.state["strategies"][strategy_id]

    def register(self, body, author):
        with self.lock:
            policy = self.policy()
            if (
                set(body.weights) - set(policy.universe)
                or max(body.weights.values()) > policy.max_position
            ):
                raise ValueError(
                    "Strategy violates the mandate's universe or position limit"
                )
            record = {
                **body.model_dump(mode="json"),
                "id": uuid4().hex,
                "author": author,
                "created_at": stamp(),
            }
            self.state["strategies"][record["id"]] = record
            self.event("strategy_registered", record["id"])
            return record

    def review(self, body, author):
        with self.lock:
            strategy = self.strategy(body.strategy_id)
            if strategy["author"] == author:
                raise ValueError("A strategy author cannot review their own strategy")
            record = {**body.model_dump(), "author": author, "time": stamp()}
            self.state["reviews"][body.strategy_id] = record
            self.state["approvals"].pop(body.strategy_id, None)
            self.event("adversarial_review", record)
            return record

    def evaluate(self, strategy_id):
        with self.lock:
            record = self.strategy(strategy_id)
            policy = self.policy()
            # Both windows and weights are frozen before the evaluator is created.
            window = data.prices_full(list(record["weights"]) + [data.REFERENCE])
            available_end = window.index.max().date().isoformat()
            if record["end"] > available_end:
                raise ValueError(
                    f"Snapshot ends {available_end}; refusing to silently shorten the test"
                )
            weights = [
                Weight(
                    ticker=t,
                    weight=w,
                    rationale="",
                    changes_my_mind="",
                    analyst_influence={},
                )
                for t, w in record["weights"].items()
            ]
            _, result = backtest.backtest(
                weights,
                record["cutoff"],
                record["end"],
                baseline="spy",
                universe=list(record["weights"]),
                closes=window,
            )
            metrics = result.model_dump()
            portfolio, benchmark = metrics["portfolio"], metrics["baseline"]
            checks = {
                "drawdown": abs(portfolio["max_drawdown"]) <= policy.max_drawdown,
                "sharpe": portfolio["sharpe"] >= policy.min_sharpe,
                "excess_return": portfolio["total_return"] - benchmark["total_return"]
                >= policy.min_excess_return,
                "mandate": not (set(record["weights"]) - set(policy.universe))
                and max(record["weights"].values()) <= policy.max_position,
            }
            result = {
                "strategy_id": strategy_id,
                "verdict": "PASS" if all(checks.values()) else "FAIL",
                "checks": checks,
                "metrics": metrics,
                "cutoff": record["cutoff"],
                "end": record["end"],
                "policy_hash": digest(self.state["policy"]),
                "time": stamp(),
                "limitations": "Existing monthly-rebalanced snapshot engine; price returns without dividends or costs. Retro-scored and approximate. No statistical-significance claim. This tool exposes only forward-test metrics; research and web are unavailable to the evaluator.",
            }
            self.state["tests"][strategy_id] = result
            self.state["approvals"].pop(strategy_id, None)
            self.event("backtest", result)
            return result

    def execution_checks(self, strategy_id):
        policy = self.policy()
        strategy = self.strategy(strategy_id)
        if self.state["stop"] or getattr(self.manager, "paused", False):
            raise ValueError("Emergency stop or fund pause is active")
        if not policy.trading_allowed:
            raise ValueError("Human mandate does not allow paper trading")
        test = self.state["tests"].get(strategy_id, {})
        if test.get("verdict") != "PASS" or test.get("policy_hash") != digest(
            self.state["policy"]
        ):
            raise ValueError("A current backend PASS is required")
        if self.state["reviews"].get(strategy_id, {}).get("verdict") != "APPROVE":
            raise ValueError("An approving adversarial review is required")
        if policy.approval_required and self.state["approvals"].get(
            strategy_id
        ) != digest(self.state["policy"]):
            raise ValueError("Human strategy approval is required by this mandate")
        # Also honor the fund dashboard mandate when that integration is installed.
        context = json.loads(getattr(self.manager, "context", "") or "{}")
        mandate = context.get("mandate")
        if mandate:
            if not mandate.get("trading_allowed") or mandate.get("mode") != "paper":
                raise ValueError("Fund mandate must allow trading in paper mode")
            if mandate.get("approval_required", True) and self.state["approvals"].get(
                strategy_id
            ) != digest(self.state["policy"]):
                raise ValueError("Fund mandate requires human strategy approval")
            if (
                set(strategy["weights"]) - set(mandate["universe"])
                or max(strategy["weights"].values()) > mandate["max_position"] / 100
            ):
                raise ValueError("Strategy violates the fund mandate")
            if (
                abs(test["metrics"]["portfolio"]["max_drawdown"])
                > mandate["max_drawdown"] / 100
            ):
                raise ValueError("Test exceeds fund drawdown limit")
            # Do not imply support for constraints the existing backtest cannot model.
            if (
                mandate.get("min_cash", 0)
                or mandate.get("exclusions")
                or mandate.get("rebalance", "monthly") != "monthly"
            ):
                raise ValueError(
                    "Cash reserve, exclusions or rebalance mandate needs a matching evaluation engine before execution"
                )
        return policy, strategy


def desk_for(manager):
    if not hasattr(manager, "desk"):
        manager.desk = Desk(manager)
    return manager.desk
