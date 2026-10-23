from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backend.app.wf.pit import PitData
from backend.tests.wf.synth import TICKERS, make_data_dir

ANALYSTS = ["technical", "fundamentals", "macro", "sentiment", "geopolitics"]


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return make_data_dir(tmp_path / "wf")


def test_fred_monthly_value_hidden_until_available(data_dir: Path) -> None:
    pit = PitData(data_dir)
    # FEDFUNDS for 2024-10-01 becomes available 2024-11-04 (date + 1 month + 3 days)
    before = pit.evidence("macro", "2024-11-03", TICKERS)[1]
    after = pit.evidence("macro", "2024-11-04", TICKERS)[1]
    ff = lambda srcs: [s.id for s in srcs if s.id.startswith("fred:FEDFUNDS")]
    assert ff(before) == ["fred:FEDFUNDS:2024-09-01"]
    assert ff(after) == ["fred:FEDFUNDS:2024-10-01"]


def test_8k_visible_only_strictly_before_as_of(data_dir: Path) -> None:
    pit = PitData(data_dir)
    same_day = pit.evidence("sentiment", "2024-11-12", TICKERS)[1]
    next_day = pit.evidence("sentiment", "2024-11-13", TICKERS)[1]
    assert not any("2024-11-12" in s.title for s in same_day)
    assert any("2024-11-12" in s.title for s in next_day)


def test_8k_older_than_eight_weeks_excluded(data_dir: Path) -> None:
    pit = PitData(data_dir)
    sources = pit.evidence("sentiment", "2024-12-31", TICKERS)[1]
    assert not any("2024-10-15" in s.title for s in sources)
    assert any("2024-11-12" in s.title for s in sources)


def test_fundamentals_visible_only_after_filing(data_dir: Path) -> None:
    pit = PitData(data_dir)
    # Q3 2024 (period end 2024-09-30) is filed 2024-10-30
    on_filing = pit.evidence("fundamentals", "2024-10-30", ["AAA"])[1]
    day_after = pit.evidence("fundamentals", "2024-10-31", ["AAA"])[1]
    assert on_filing[0].id == "sec:AAA:2024Q2"
    assert day_after[0].id == "sec:AAA:2024Q3"
    assert day_after[0].date == "2024-10-30"


def test_fundamentals_yoy_growth_uses_year_ago_quarter(data_dir: Path) -> None:
    pit = PitData(data_dir)
    digest, _ = pit.evidence("fundamentals", "2024-12-01", ["AAA"])
    assert "YoY revenue +" in digest


@pytest.mark.parametrize("analyst", ANALYSTS)
def test_no_source_dated_after_as_of(data_dir: Path, analyst: str) -> None:
    pit = PitData(data_dir)
    as_of = "2024-11-20"
    digest, sources = pit.evidence(analyst, as_of, TICKERS)
    assert sources
    assert all(s.date <= as_of for s in sources)
    assert pit.audit[-1][2] <= as_of
    assert len(digest) <= 6000


def test_prices_after_as_of_never_used(data_dir: Path) -> None:
    pit = PitData(data_dir)
    ctx = pit.execution_context("2024-06-14", ["AAA"])
    assert ctx["AAA"]["last_date"] == "2024-06-14"
    assert pit.last_close("2024-06-15", "AAA") == ctx["AAA"]["last_close"]  # Saturday -> Friday


def test_execution_context_keys(data_dir: Path) -> None:
    ctx = PitData(data_dir).execution_context("2024-06-14", ["AAA", "NOPE"])
    assert set(ctx) == {"AAA"}
    assert set(ctx["AAA"]) == {"last_close", "atr14", "avg_volume20", "avg_gap_pct", "ret_1w", "last_date"}


def test_graceful_empty_evidence_before_any_data(data_dir: Path) -> None:
    pit = PitData(data_dir)
    for analyst in ANALYSTS:
        digest, sources = pit.evidence(analyst, "2019-01-01", TICKERS)
        assert sources == []
        assert "No evidence available" in digest


def test_missing_dirs_give_empty_evidence_not_fixtures(tmp_path: Path) -> None:
    pit = PitData(tmp_path / "does-not-exist")
    assert pit.evidence("macro", "2024-01-05", TICKERS)[1] == []
    with pytest.raises(KeyError):
        pit.last_close("2024-01-05", "AAA")


def test_post_close_earnings_reaction_requires_both_days(data_dir: Path) -> None:
    pit = PitData(data_dir)
    # 2.02 filed 2024-10-15 at 21:30Z = 17:30 ET (after the close): reaction is 10-15 -> 10-16
    digest, _ = pit.evidence("sentiment", "2024-10-16", ["AAA"])
    assert "price reaction 2024-10-15 to 2024-10-16" in digest
    digest_early, _ = pit.evidence("sentiment", "2024-10-15", ["AAA"])
    assert "2.02" not in digest_early and "price reaction" not in digest_early


def test_real_data_dir_respects_as_of() -> None:
    real = Path(__file__).resolve().parents[3] / "data" / "wf"
    if not (real / "prices" / "SPY.csv").exists():
        pytest.skip("data/wf not built")
    pit = PitData(real)
    as_of = "2026-01-16"
    for analyst in ANALYSTS:
        _, sources = pit.evidence(analyst, as_of, ["AAPL", "MSFT", "NVDA"])
        assert sources
        assert all(s.date <= as_of for s in sources)
    assert pd.Timestamp(pit.max_evidence_date) <= pd.Timestamp(as_of)
