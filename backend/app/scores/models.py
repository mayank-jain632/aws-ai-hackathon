"""Scorecard shapes. One fund, one card, a 0..100 ring per score with its factors.

Every scored ring carries the raw metric, the formula that maps it to 0..100 and the
record it came from. A ring with no data is `not_produced` and names the lane that owns
its source; it never carries a placeholder number.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Scope = Literal["fund", "firm"]
FactorStatus = Literal["pass", "fail", "pending", "info"]
Attribution = Literal["recorded", "role holder", "system"]


class Citation(BaseModel):
    id: str = ""
    kind: str
    title: str
    date: str | None = None
    url: str | None = None
    excerpt: str = ""


class AgentRef(BaseModel):
    id: str | None = None
    name: str
    role: str
    specialty: str = ""
    attribution: Attribution = Field(
        default="recorded",
        description="recorded: the record names this agent. role holder: an agent with the role in this fund, not named per record. system: deterministic code or an offline run",
    )


class Provenance(BaseModel):
    record: str = Field(description="The record the value was read from")
    file: str | None = None
    time: str | None = None
    citations: list[Citation] = Field(default_factory=list)


class Factor(BaseModel):
    key: str
    label: str
    value: str
    number: float | None = None
    weight: float | None = Field(
        default=None, description="Share of the ring's formula, 0..1. None means context only"
    )
    status: FactorStatus = "info"
    detail: str = Field(default="", description="What was looked at")
    agents: list[AgentRef] = Field(default_factory=list)
    reasoning: str | None = None
    reasoning_label: str = "Recorded reasoning"
    provenance: Provenance


class SourceRef(BaseModel):
    id: str
    label: str
    scope: Scope
    location: str


class Score(BaseModel):
    key: str
    label: str
    question: str
    status: Literal["scored", "not_produced"]
    value: float | None = None
    raw: str = ""
    formula: str = ""
    source: SourceRef | None = None
    owner: str
    missing: str = ""
    scope: Scope = "fund"
    contributors: list[AgentRef] = Field(default_factory=list)
    factors: list[Factor] = Field(default_factory=list)


class SourceStatus(BaseModel):
    id: str
    label: str
    owner: str
    location: str
    status: Literal["present", "empty", "not_on_main"]
    detail: str = ""


class ToolCall(BaseModel):
    agent: AgentRef
    tool: str
    summary: str
    time: str


class Scorecard(BaseModel):
    fund_id: str
    fund_name: str
    generated_at: str
    strategy: dict | None = None
    strategies: list[dict] = Field(default_factory=list)
    scores: list[Score]
    team_title: str = ""
    team_note: str = ""
    team: list[Score] = Field(
        default_factory=list, description="Frozen team walk-forward run; never this fund's own results"
    )
    sources: list[SourceStatus]
    agents: list[AgentRef]
    inputs: list[ToolCall] = Field(
        default_factory=list, description="Tool calls recorded in each agent's activity log"
    )
    notes: list[str] = Field(default_factory=list)
