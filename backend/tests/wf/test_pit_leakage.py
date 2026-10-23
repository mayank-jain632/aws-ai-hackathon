from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from backend.app.wf.pit import PitData
from backend.tests.wf.synth import TICKERS, make_data_dir

ANALYSTS = ["technical", "fundamentals", "macro", "sentiment", "geopolitics"]
AS_OFS = ["2024-02-02", "2024-06-14", "2024-10-16", "2024-11-12", "2024-12-06"]
SENTINEL = 9.99e12


def _poison(src: Path, dst: Path, as_of: str) -> None:
    shutil.copytree(src, dst)
    for p in (dst / "prices").glob("*.csv"):
        df = pd.read_csv(p)
        fut = df["date"] > as_of
        for c in ("open", "high", "low", "close", "volume"):
            df.loc[fut, c] = SENTINEL
        df.to_csv(p, index=False)
    m = pd.read_csv(dst / "fred" / "macro.csv")
    m.loc[m["available"] > as_of, "value"] = SENTINEL
    m.to_csv(dst / "fred" / "macro.csv", index=False)
    f = pd.read_csv(dst / "sec" / "fundamentals.csv")
    f.loc[f["filed"] >= as_of, ["revenue", "net_income", "total_debt"]] = SENTINEL
    f.to_csv(dst / "sec" / "fundamentals.csv", index=False)
    k = pd.read_csv(dst / "sec" / "filings_8k.csv")
    k.loc[k["filed"] >= as_of, ["items", "item_titles", "description"]] = "SENTINEL 8.01 7.01 5.02"
    k.to_csv(dst / "sec" / "filings_8k.csv", index=False)


def _truncate(src: Path, dst: Path, as_of: str) -> None:
    shutil.copytree(src, dst)
    for p in (dst / "prices").glob("*.csv"):
        df = pd.read_csv(p)
        df[df["date"] <= as_of].to_csv(p, index=False)
    m = pd.read_csv(dst / "fred" / "macro.csv")
    m[m["available"] <= as_of].to_csv(dst / "fred" / "macro.csv", index=False)
    f = pd.read_csv(dst / "sec" / "fundamentals.csv")
    f[f["filed"] < as_of].to_csv(dst / "sec" / "fundamentals.csv", index=False)
    k = pd.read_csv(dst / "sec" / "filings_8k.csv")
    k[k["filed"] < as_of].to_csv(dst / "sec" / "filings_8k.csv", index=False)


def _snapshot(pit: PitData, as_of: str) -> dict:
    return {
        "evidence": {a: pit.evidence(a, as_of, TICKERS) for a in ANALYSTS},
        "ctx": pit.execution_context(as_of, TICKERS),
        "last_close": pit.last_close(as_of, "AAA"),
    }


@pytest.fixture()
def base(tmp_path: Path) -> Path:
    return make_data_dir(tmp_path / "base")


@pytest.mark.parametrize("as_of", AS_OFS)
def test_future_poison_leaves_evidence_byte_identical(base: Path, tmp_path: Path, as_of: str) -> None:
    clean = _snapshot(PitData(base), as_of)
    _poison(base, tmp_path / "poison", as_of)
    poisoned = _snapshot(PitData(tmp_path / "poison"), as_of)
    assert poisoned == clean
    for a in ANALYSTS:
        digest, sources = poisoned["evidence"][a]
        assert "SENTINEL" not in digest and "9990000000000" not in digest
        assert all("SENTINEL" not in s.excerpt for s in sources)


@pytest.mark.parametrize("as_of", AS_OFS)
def test_truncation_invariance(base: Path, tmp_path: Path, as_of: str) -> None:
    full = _snapshot(PitData(base), as_of)
    _truncate(base, tmp_path / "cut", as_of)
    cut = _snapshot(PitData(tmp_path / "cut"), as_of)
    assert cut == full


def test_poison_is_detectable_when_visible(base: Path, tmp_path: Path) -> None:
    """Sanity: the poison would show up if the PIT cut were wrong (guards the test itself)."""
    _poison(base, tmp_path / "poison", "2024-12-06")
    leaky = PitData(tmp_path / "poison")
    digest, _ = leaky.evidence("technical", "2024-12-30", TICKERS)  # after the poisoned region starts
    assert "9990000000000" in digest or "+" in digest and "nan" not in digest
    assert digest != PitData(base).evidence("technical", "2024-12-30", TICKERS)[0]


def test_real_data_truncation_invariance(tmp_path: Path) -> None:
    real = Path(__file__).resolve().parents[3] / "data" / "wf"
    if not (real / "prices" / "SPY.csv").exists():
        pytest.skip("data/wf not built")
    as_of = "2026-03-13"
    universe = ["AAPL", "NVDA", "JPM", "XOM"]
    full = PitData(real)
    _truncate(real, tmp_path / "cut", as_of)
    shutil.rmtree(tmp_path / "cut" / "sec" / "raw", ignore_errors=True)
    cut = PitData(tmp_path / "cut")
    for a in ANALYSTS:
        assert full.evidence(a, as_of, universe) == cut.evidence(a, as_of, universe)
    assert full.execution_context(as_of, universe) == cut.execution_context(as_of, universe)
