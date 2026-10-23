"""The leakage proof must pass on a sealed reader AND fail on deliberately leaky readers."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.wf import leakage_proof
from backend.app.wf.pit import PitData
from backend.tests.wf.synth import TICKERS, make_data_dir

AS_OF = "2024-06-14"
LATER = "2024-07-31"


@pytest.fixture()
def src(tmp_path: Path) -> Path:
    return make_data_dir(tmp_path / "data")


def _prove(src: Path, tmp_path: Path) -> dict:
    return leakage_proof.prove_date(src, AS_OF, TICKERS, tmp_path / "work")


def test_sealed_reader_passes_all_checks(src: Path, tmp_path: Path) -> None:
    row = _prove(src, tmp_path)

    assert row["ok"] is True
    assert row["truncate_identical"] and row["poison_identical"]
    assert row["poison_was_present"], "poison must exist in the variant or the proof is vacuous"
    assert row["latest_date_in_prompts"] <= AS_OF


def test_reader_that_peeks_at_later_context_is_caught(
    src: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Leaky(PitData):
        def execution_context(self, as_of, tickers):  # ignores the decision date on purpose
            return super().execution_context(LATER, tickers)

    monkeypatch.setattr(leakage_proof, "PitData", Leaky)

    row = _prove(src, tmp_path)

    assert row["ok"] is False
    assert not (row["truncate_identical"] and row["poison_identical"])


def test_prompt_that_prints_a_future_date_is_caught(
    src: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DatesTheFuture(PitData):
        def evidence(self, analyst, as_of, universe):
            digest, sources = super().evidence(analyst, as_of, universe)
            return digest + f"\nNote: results due {LATER}", sources

    monkeypatch.setattr(leakage_proof, "PitData", DatesTheFuture)

    row = _prove(src, tmp_path)

    assert row["no_future_dates"] is False
    assert row["ok"] is False


def test_prove_reports_failures_by_date(src: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Leaky(PitData):
        def execution_context(self, as_of, tickers):
            return super().execution_context(LATER, tickers)

    monkeypatch.setattr(leakage_proof, "PitData", Leaky)

    result = leakage_proof.prove([AS_OF, "2024-06-21"], TICKERS, data_dir=src)

    assert result["all_ok"] is False
    assert result["failures"] == [AS_OF, "2024-06-21"]
