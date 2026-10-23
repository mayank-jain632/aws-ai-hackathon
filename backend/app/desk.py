"""Server-owned strategy artifacts and gates. Kept outside the agents' shared files."""

import hashlib
import json
import math
import os
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
    trading_allowed: bool = True
    approval_required: bool = False

    @model_validator(mode="after")
    def valid_universe(self):
        if set(self.universe) - set(data.UNIVERSE) or len(set(self.universe)) != len(
            self.universe
        ):
            raise ValueError("Use unique tickers from the existing historical universe")
        return self


class PaperCriteria(StrictModel):
    min_sharpe: float
    min_excess_return: float
    max_order_notional: float = Field(gt=0, le=10000000)
    max_daily_orders: int = Field(ge=1, le=100)
    rationale: str = Field(min_length=20, max_length=2000)


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
        ) or sum(self.weights.values()) > 1 + 1e-9:
            raise ValueError("Long-only weights must be positive and sum to at most one; the remainder is cash")
        return self


def check_allocation(weights, mandate):
    """Validate target or projected holdings as fractions of the fund capital.

    Sector labels are the existing static ten-name classification, not live data.
    Unknown holdings fail closed when a sector cap applies.
    """
    if not mandate:
        return
    reserve = float(mandate.get("min_cash", 0)) / 100
    if sum(weights.values()) > 1 - reserve + 1e-9:
        raise ValueError("Allocation would breach the fund cash reserve")
    sector_limit = float(mandate.get("max_sector", 100)) / 100
    if sector_limit < 1:
        from backend.app.wf.masking import SECTORS

        totals = {}
        for symbol, weight in weights.items():
            if weight <= 0:
                continue
            if symbol not in SECTORS:
                raise ValueError(f"Unknown sector for {symbol}; cannot enforce sector limit")
            sector = SECTORS[symbol]
            totals[sector] = totals.get(sector, 0) + weight
        if any(weight > sector_limit + 1e-9 for weight in totals.values()):
            raise ValueError("Allocation would breach the fund sector limit")


class ReviewInput(StrictModel):
    strategy_id: str
    verdict: Literal["APPROVE", "CHANGES_REQUESTED"]
    critique: str = Field(min_length=20, max_length=6000)
    evaluation_id: str | None = Field(default=None, min_length=64, max_length=64)


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


ENGINE_VERSIONS = {"wf": "wf-frozen-v1", "legacy": "legacy-monthly-v2"}


def selected_engine():
    engine = os.environ.get("BACKTEST_ENGINE", "wf")
    if engine not in ENGINE_VERSIONS:
        raise ValueError("BACKTEST_ENGINE must be wf or legacy; no fallback is available")
    return engine


class WorkflowPending(ValueError):
    """An agent can complete a missing workflow stage; this is not an order-risk breach."""


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
                "stop_source": "initial",
                "strategies": {},
                "reviews": {},
                "tests": {},
                "approvals": {},
                "orders": {},
                "events": [],
            }
        )
        # Old approvals remain visible for audit, but have no evaluation binding.
        self.state.setdefault("approved_evaluations", {})
        if "stop_source" not in self.state:
            self.state["stop_source"] = "legacy"
            for event in reversed(self.state["events"]):
                source = {"human_stop": "human", "moderator_stop": "moderator", "human_policy": "human_policy", "agent_paper_policy": "policy_configuration"}.get(event["check"])
                if source:
                    self.state["stop_source"] = source
                    break
            else:
                if not self.state["events"] and not self.state["policy"] and not any(self.state[k] for k in ("strategies", "tests", "orders")):
                    self.state["stop_source"] = "initial"

        if self.state["stop"] and self.state["stop_source"] not in {"human", "moderator"}:
            for event in reversed(self.state["events"]):
                if event["check"] == "human_stop":
                    if not isinstance(event.get("result"), dict) or event["result"].get("stopped"):
                        self.state["stop_source"] = "human"
                    break
                if event["check"] == "moderator_stop":
                    self.state["stop_source"] = "moderator"
                    break

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
                "Please configure the paper policy and freeze criteria before testing"
            )
        return Policy.model_validate(self.state["policy"])

    def autonomous_paper(self):
        mandate = json.loads(getattr(self.manager, "context", "") or "{}").get("mandate", {})
        policy = self.state.get("policy") or {}
        return (
            mandate.get("mode") == "paper" and mandate.get("trading_allowed") is True
            and mandate.get("approval_required", True) is False
            and policy.get("approval_required", False) is False
        )

    def authorize_initial_paper(self):
        with self.lock:
            if self.autonomous_paper() and self.state["stop_source"] in {"initial", "policy_configuration", "human_policy"}:
                self.state["stop"] = False
                self.state["stop_source"] = "standing_paper_authorization"
                self.event("standing_paper_authorization", "Bootstrap stop removed under the saved autonomous paper mandate; explicit user/moderator stops are preserved")

    def set_policy(self, policy, *, origin=None):
        with self.lock:
            self.state["policy"] = policy.model_dump()
            self.state["policy_version"] = uuid4().hex
            self.state["policy_origin"] = origin or {"type": "human", "time": stamp()}
            self.state["approvals"] = {}
            self.state["approved_evaluations"] = {}
            self.authorize_initial_paper()
            self.event(
                "human_policy" if self.state["policy_origin"]["type"] == "human" else "agent_paper_policy", {"message": "Policy updated; approvals invalidated", "stop": self.state["stop"], "stop_source": self.state["stop_source"]}
            )

    def configure_paper_policy(self, criteria, author):
        with self.lock:
            mandate = json.loads(getattr(self.manager, "context", "") or "{}").get("mandate", {})
            if mandate.get("mode") != "paper":
                raise ValueError("Agent policy selection is limited to an explicit paper fund")
            policy = Policy(
                universe=mandate["universe"], max_position=mandate["max_position"] / 100,
                max_drawdown=mandate["max_drawdown"] / 100,
                min_sharpe=criteria.min_sharpe, min_excess_return=criteria.min_excess_return,
                max_order_notional=criteria.max_order_notional, max_daily_orders=criteria.max_daily_orders,
                trading_allowed=bool(mandate.get("trading_allowed")), approval_required=bool(mandate.get("approval_required", True)),
            )
            if policy.max_order_notional > mandate["capital"]:
                raise ValueError("Paper order limit cannot exceed saved fund capital")
            if self.state["tests"]:
                if self.state["policy"] == policy.model_dump() and self.state.get("policy_origin", {}).get("type") == "agent":
                    return {"policy": self.state["policy"], "policy_version": self.state["policy_version"], "origin": self.state["policy_origin"]}
                raise ValueError("Paper criteria are frozen after the first observed evaluation; agents cannot tune thresholds to results")
            origin = {"type": "agent", "author": author, "rationale": criteria.rationale, "time": stamp(), "authorization": "Human delegated paper policy selection before testing"}
            self.set_policy(policy, origin=origin)
            self.event("paper_policy_selected", {"policy_version": self.state["policy_version"], "policy": self.state["policy"], "origin": self.state["policy_origin"]})
            return {"policy": self.state["policy"], "policy_version": self.state["policy_version"], "origin": self.state["policy_origin"]}

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
            context = json.loads(getattr(self.manager, "context", "") or "{}")
            check_allocation(body.weights, context.get("mandate"))
            record = {
                **body.model_dump(mode="json"),
                "id": uuid4().hex,
                "author": author,
                "author_model": getattr(
                    getattr(self.manager, "agents", {}).get(author), "model", None
                ),
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
            if body.evaluation_id is not None:
                test = self.state["tests"].get(body.strategy_id, {})
                if not self.test_is_current(body.strategy_id) or body.evaluation_id != test.get("evaluation_id"):
                    raise ValueError("Final review must reference the exact current evaluation_id")
                if body.verdict == "APPROVE" and test.get("verdict") != "PASS":
                    raise ValueError("A failed backtest cannot receive execution APPROVE")
            record = {**body.model_dump(), "phase": "final" if body.evaluation_id else "strategy", "author": author, "time": stamp()}
            self.state["reviews"][body.strategy_id] = record
            self.state["approvals"].pop(body.strategy_id, None)
            self.state["approved_evaluations"].pop(body.strategy_id, None)
            self.event("adversarial_review", record)
            return record

    def test_is_current(self, strategy_id):
        test = self.state["tests"].get(strategy_id, {})
        engine = selected_engine()
        unsigned = {k: v for k, v in test.items() if k != "evaluation_id"}
        return bool(
            test
            and test.get("engine") == engine
            and test.get("engine_version") == ENGINE_VERSIONS[engine]
            and test.get("policy_hash") == digest(self.state["policy"])
            and test.get("policy_version") == self.state.get("policy_version")
            and test.get("strategy_hash") == digest(self.strategy(strategy_id))
            and test.get("evaluation_id") == digest(unsigned)
        )

    def human_approved(self, strategy_id):
        return (
            self.test_is_current(strategy_id)
            and self.state["approvals"].get(strategy_id) == digest(self.state["policy"])
            and self.state["approved_evaluations"].get(strategy_id)
            == self.state["tests"][strategy_id]["evaluation_id"]
        )

    def require_final_review(self, strategy_id):
        review = self.state["reviews"].get(strategy_id, {})
        if review.get("verdict") != "APPROVE" and not self.autonomous_paper():
            raise WorkflowPending("An approving adversarial review is required; obtain or revise the strategy for review")
        test = self.state["tests"].get(strategy_id, {})
        if not test.get("evaluation_id") or review.get("evaluation_id") != test["evaluation_id"] or review.get("phase") != "final":
            raise WorkflowPending("An independent final review of this exact backtest evaluation is required; create a reviewer, record the result and continue")
        if review.get("author") == self.strategy(strategy_id)["author"]:
            raise WorkflowPending("The final review must be performed by an independent agent")
        return review

    def approve(self, strategy_id):
        with self.lock:
            self.strategy(strategy_id)
            if not self.test_is_current(strategy_id) or self.state["tests"][strategy_id]["verdict"] != "PASS":
                raise ValueError("A current backend PASS is required before human approval")
            self.require_final_review(strategy_id)
            evaluation_id = self.state["tests"][strategy_id]["evaluation_id"]
            self.state["approvals"][strategy_id] = digest(self.state["policy"])
            self.state["approved_evaluations"][strategy_id] = evaluation_id
            self.event("human_approval", {"strategy_id": strategy_id, "evaluation_id": evaluation_id})

    def _record_test(self, strategy_id, record, result, engine):
        result.update(
            engine=engine,
            engine_version=ENGINE_VERSIONS[engine],
            strategy_hash=digest(record),
            policy_version=self.state.get("policy_version"),
            author_model=record.get("author_model"),
        )
        result["evaluation_id"] = digest(result)
        self.state["tests"][strategy_id] = result
        self.state["approvals"].pop(strategy_id, None)
        self.state["approved_evaluations"].pop(strategy_id, None)
        self.event("backtest", result)
        return result

    def _evaluate_wf(self, strategy_id, record, policy):
        """Evaluate frozen weights with the default walk-forward engine, without fallback."""
        from backend.app.wf.gate import evaluate_with_wf

        result = evaluate_with_wf(
            strategy_id,
            record,
            policy,
            now=stamp(),
            policy_hash=digest(self.state["policy"]),
            author_model=record.get("author_model"),
        )
        return self._record_test(strategy_id, record, result, "wf")

    def evaluate(self, strategy_id):
        with self.lock:
            record = self.strategy(strategy_id)
            policy = self.policy()
            if selected_engine() == "wf":
                return self._evaluate_wf(strategy_id, record, policy)
            if not math.isclose(sum(record["weights"].values()), 1, abs_tol=1e-9):
                raise ValueError("Cash allocations require the WF engine; legacy normalizes weights")
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
            return self._record_test(strategy_id, record, result, "legacy")

    def execution_checks(self, strategy_id):
        policy = self.policy()
        strategy = self.strategy(strategy_id)
        if self.state["stop"] or getattr(self.manager, "paused", False):
            raise ValueError("Emergency stop or fund pause is active")
        if not policy.trading_allowed:
            raise ValueError("Human mandate does not allow paper trading")
        test = self.state["tests"].get(strategy_id, {})
        if not self.test_is_current(strategy_id):
            raise WorkflowPending("A current backend PASS is required; run the bound evaluator and continue from its actual result")
        if test.get("verdict") != "PASS":
            raise ValueError("A current backend PASS is required; revise the strategy rather than inventing a pass")
        self.require_final_review(strategy_id)
        if policy.approval_required and not self.human_approved(strategy_id):
            raise ValueError("Human strategy approval is required by this mandate")
        # Also honor the fund dashboard mandate when that integration is installed.
        context = json.loads(getattr(self.manager, "context", "") or "{}")
        mandate = context.get("mandate")
        if mandate:
            if not mandate.get("trading_allowed") or mandate.get("mode") != "paper":
                raise ValueError("Fund mandate must allow trading in paper mode")
            if mandate.get("approval_required", True) and not self.human_approved(strategy_id):
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
                mandate.get("exclusions")
                or mandate.get("rebalance", "monthly") != "monthly"
            ):
                raise ValueError(
                    "Exclusions or rebalance mandate needs a matching evaluation engine before execution"
                )
            check_allocation(strategy["weights"], mandate)
        return policy, strategy


def desk_for(manager):
    if not hasattr(manager, "desk"):
        manager.desk = Desk(manager)
    return manager.desk
