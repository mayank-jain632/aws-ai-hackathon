"""Exercise real snapshots and the private worker boundary without model calls."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.research import (
    ResearchContext,
    ResearchQuery,
    claim_context,
    query_snapshot,
)


@pytest.mark.parametrize("source", ["prices", "ohlcv", "fundamentals", "macro", "events", "tone"])
def test_snapshots_respect_availability(source):
    result = query_snapshot(ResearchQuery(source=source, mode="historical", cutoff="2023-01-01", tickers=["AAPL"] if source == "ohlcv" else [], limit=7))
    assert result["returned_rows"] <= 7
    assert all(row[result["availability"]][:10] <= "2023-01-01" for row in result["rows"])
    if source != "tone":
        assert result["returned_rows"] > 0
    if source == "events":
        assert "UNVERIFIED" in result["warning"]
    if source == "macro":
        # Observation date alone is insufficient for monthly releases.
        assert all(row["available"][:10] <= "2023-01-01" for row in result["rows"])


def test_invalid_context_and_ticker():
    with pytest.raises(ValueError):
        ResearchContext(mode="historical")
    with pytest.raises(ValueError):
        ResearchContext(mode="live", cutoff="2023-01-01")
    with pytest.raises(ValueError, match="Unsupported ticker"):
        query_snapshot(ResearchQuery(source="ohlcv", mode="historical", cutoff="2023-01-01", tickers=["../../secret"]))


def test_modes_and_cutoffs_cannot_mix_through_descendants():
    root = SimpleNamespace(id="root", state={}, publish=lambda: None)
    child = SimpleNamespace(id="child", state={}, publish=lambda: None)
    manager = SimpleNamespace(agents={"root": root, "child": child}, ancestors=lambda _: {"root", "child"})
    historical = ResearchContext(mode="historical", cutoff="2023-01-01")
    claim_context(child, manager, historical)
    assert root.state["research_context"] == historical.model_dump(mode="json")
    claim_context(child, manager, historical)
    for context in [ResearchContext(mode="live"), ResearchContext(mode="historical", cutoff="2024-01-01")]:
        with pytest.raises(ValueError, match="conflicts"):
            claim_context(child, manager, context)


def test_worker_auth_and_query(monkeypatch):
    agent = SimpleNamespace(id="dexter", state={}, publish=lambda: None)
    manager = SimpleNamespace(token="test-token", agents={"dexter": agent}, ancestors=lambda _: {"dexter"})
    agent.manager = manager
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    client = TestClient(app, base_url="http://localhost")
    try:
        assert client.get("/api/internal/research/sources").status_code == 403
        headers = {"X-Agent-Token": "test-token", "X-Agent-ID": "dexter"}
        response = client.post("/api/internal/research/query", headers=headers, json={"mode": "historical", "cutoff": "2023-01-01", "source": "prices", "tickers": ["AAPL"], "limit": 3})
        assert response.status_code == 200
        assert response.json()["returned_rows"] == 3
        assert client.post("/api/internal/research/context", headers=headers, json={"mode": "live"}).status_code == 409
    finally:
        client.close()
