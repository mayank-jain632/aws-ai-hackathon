"""Persistent fund mandates and per-fund canvas runtimes. No simulated returns."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from backend.app.agent import ROOT, AgentManager


class Mandate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    objective: Literal[
        "capital_preservation", "balanced_growth", "long_term_growth", "income"
    ] = "balanced_growth"
    description: str = Field(default="", max_length=2000)
    capital: float = Field(default=100000, ge=0, le=10000000000, allow_inf_nan=False)
    risk: Literal["conservative", "balanced", "aggressive"] = "balanced"
    horizon_months: int = Field(default=36, ge=1, le=600)
    target_return: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    max_position: float = Field(default=20, ge=1, le=100, allow_inf_nan=False)
    max_drawdown: float = Field(default=15, ge=1, le=100, allow_inf_nan=False)
    min_cash: float = Field(default=5, ge=0, le=100, allow_inf_nan=False)
    max_sector: float = Field(default=40, ge=1, le=100, allow_inf_nan=False)
    universe: list[str] = Field(
        default_factory=lambda: [
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "GOOGL",
            "JPM",
            "XOM",
            "UNH",
            "PG",
            "CAT",
        ],
        min_length=1,
        max_length=50,
    )
    exclusions: str = Field(default="", max_length=500)
    benchmark: Literal["SPY"] = "SPY"
    rebalance: Literal["weekly", "monthly", "quarterly"] = "monthly"
    liquidity: Literal["daily", "monthly", "quarterly"] = "monthly"
    mode: Literal["historical", "paper"] = "historical"
    cutoff: str = Field(default="2024-06-01", pattern=r"^\d{4}-\d{2}-\d{2}$")
    trading_allowed: bool = False
    approval_required: bool = True
    allow_short: bool = False
    max_leverage: float = Field(default=1, ge=1, le=2, allow_inf_nan=False)
    notes: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Enter a fund name of at least two characters")
        return value.strip()

    @field_validator("universe")
    @classmethod
    def clean_universe(cls, values):
        import re

        symbols = list(dict.fromkeys(v.strip().upper() for v in values if v.strip()))
        if not symbols or any(
            not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", v) for v in symbols
        ):
            raise ValueError("Use valid ticker symbols, separated by commas")
        return symbols

    @field_validator("cutoff")
    @classmethod
    def valid_date(cls, value):
        from datetime import date

        date.fromisoformat(value)
        return value


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


class FundStore:
    def __init__(self, legacy: AgentManager, root: Path | None = None):
        self.root = root or ROOT / ".local"
        self.path = self.root / "funds.json"
        self.legacy = legacy
        self.managers = {"general": legacy}
        if self.path.exists():
            self.records = json.loads(self.path.read_text())
        else:
            self.records = {
                "general": self.record(
                    Mandate(
                        name="Team 4 fund",
                        description="Your original shared agent board, preserved as a fund.",
                    ),
                    "Team 4",
                )
            }
            self.save()
        for fund_id in self.records:
            self.runtime(fund_id)

    @staticmethod
    def record(mandate, owner):
        stamp = datetime.now(UTC).isoformat()
        return {
            **mandate.model_dump(),
            "owner": owner,
            "status": "active",
            "created_at": stamp,
            "updated_at": stamp,
        }

    def save(self):
        write_json(self.path, self.records)

    def runtime(self, fund_id):
        if fund_id not in self.records:
            raise KeyError(fund_id)
        if fund_id not in self.managers:
            self.managers[fund_id] = AgentManager(root=self.root / "funds" / fund_id)
        runtime = self.managers[fund_id]
        runtime.context = json.dumps(
            {"fund_id": fund_id, "mandate": self.records[fund_id]}, indent=2
        )
        runtime.paused = self.records[fund_id]["status"] != "active"
        return runtime

    def create(self, mandate, owner):
        if len(self.records) >= 30:
            raise ValueError("This demo supports up to 30 funds.")
        fund_id = uuid4().hex[:16]
        self.records[fund_id] = self.record(mandate, owner)
        self.save()
        runtime = self.runtime(fund_id)
        (runtime.root / "workspace" / "mandate.md").write_text(
            "# Fund mandate\n\n" + runtime.context + "\n"
        )
        return self.detail(fund_id)

    def detail(self, fund_id):
        runtime = self.runtime(fund_id)
        agents = [a.snapshot() for a in runtime.agents.values()]
        activity = sorted(
            [
                {**event, "agent": agent["name"]}
                for agent in agents
                for event in agent["activity"]
            ],
            key=lambda e: e["time"],
            reverse=True,
        )
        capital = self.records[fund_id]["capital"]
        return {
            **self.records[fund_id],
            "id": fund_id,
            "metrics": {
                "nav": capital,
                "cash": capital,
                "invested": 0,
                "pnl": 0,
                "return_pct": 0,
                "positions": 0,
                "agents": len(agents),
                "working": sum(a["status"] == "running" for a in agents),
                "files": len(runtime.agents["dexter"].files()),
                "runs": sum(e["label"] == "Run started" for e in activity),
            },
            "portfolio_status": "unfunded" if not capital else "cash_only",
            "holdings": [],
            "history": [],
            "activity": activity[:30],
            "agents": [
                {
                    "id": a["id"],
                    "name": a["name"],
                    "status": a["status"],
                    "parentId": a["parentId"],
                }
                for a in agents
            ],
        }

    def list(self):
        return [self.detail(key) for key in list(self.records)]

    def by_token(self, token):
        import secrets

        return next(
            (
                m
                for m in self.managers.values()
                if secrets.compare_digest(m.token, token)
            ),
            self.legacy,
        )

    async def close(self):
        await asyncio.gather(
            *(m.close() for m in self.managers.values() if m is not self.legacy)
        )
