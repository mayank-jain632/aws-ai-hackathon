"""Fund isolation, migration, persistence, and mandate validation."""

import asyncio

import pytest
from pydantic import ValidationError

from backend.app.agent import AgentManager
from backend.app.funds import FundStore, Mandate


def test_legacy_board_survives_and_fund_files_do_not_cross(tmp_path):
    legacy = AgentManager(root=tmp_path)
    (legacy.root / "workspace" / "original.txt").write_text("existing team work")
    store = FundStore(legacy, root=tmp_path)
    assert store.runtime("general") is legacy
    one = store.create(
        Mandate(name="Income fund", risk="conservative"), "kush@example.com"
    )
    two = store.create(
        Mandate(name="Growth fund", capital=250000), "mayank@example.com"
    )
    first, second = store.runtime(one["id"]), store.runtime(two["id"])
    (first.root / "workspace" / "private.txt").write_text("first fund research")
    assert not (second.root / "workspace" / "private.txt").exists()
    assert not (first.root / "workspace" / "original.txt").exists()
    assert (
        legacy.root / "workspace" / "original.txt"
    ).read_text() == "existing team work"
    assert store.by_token(first.token) is first
    assert store.by_token(second.token) is second
    assert first.token != second.token
    restored = FundStore(legacy, root=tmp_path)
    assert restored.detail(two["id"])["metrics"]["cash"] == 250000
    assert (
        restored.runtime(one["id"]).root / "workspace" / "private.txt"
    ).read_text() == "first fund research"
    assert restored.detail(one["id"])["metrics"]["pnl"] == 0


def test_paused_fund_cannot_start_an_agent(tmp_path):
    manager = AgentManager(root=tmp_path)
    manager.paused = True
    with pytest.raises(ValueError, match="paused"):
        asyncio.run(manager.agents["dexter"].start("Place a trade"))
    assert manager.agents["dexter"].state["messages"] == []


@pytest.mark.parametrize(
    "values",
    [
        dict(name="  "),
        dict(name="Invalid", capital=-1),
        dict(name="Invalid", universe=["../other"]),
        dict(name="Invalid", max_drawdown=float("inf")),
        dict(name="Invalid", cutoff="2024-02-31"),
    ],
)
def test_invalid_mandates_rejected(values):
    with pytest.raises(ValidationError):
        Mandate(**values)
