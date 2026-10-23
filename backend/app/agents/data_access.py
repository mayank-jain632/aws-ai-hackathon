"""What each analyst is allowed to see, filtered to <= cutoff.

Lane B owns `backend/app/data.py` (`prices`, `fundamentals`, `macro`, `events`, each
taking `cutoff`). Until it lands, or if a loader raises, we fall back to the fixture
`data/fixtures/run_2023-01-01.json`, sliced by source kind and date.

Each `slice_*` function returns `(digest: str, sources: list[Source])`:
- `digest` is the text the analyst reads (tables / bullet summaries),
- `sources` are the citable Source records, every one dated <= cutoff.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.schema import Source, SourceKind

log = logging.getLogger("desk.data")

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "data" / "fixtures" / "run_2023-01-01.json"

try:  # Lane B's module, may not exist yet
    from backend.app import data as real_data  # type: ignore
except Exception:  # noqa: BLE001 ImportError or half-written module
    real_data = None


@lru_cache(maxsize=1)
def fixture() -> dict[str, Any]:
    with FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)


def fixture_sources(kind: SourceKind, cutoff: str, universe: list[str]) -> list[Source]:
    out = []
    for raw in fixture()["sources"]:
        if raw["kind"] != kind or raw["date"] > cutoff:
            continue
        src = Source.model_validate(raw)
        if _ticker_specific(src) and not any(t.lower() in src.id.lower() for t in universe):
            continue
        out.append(src)
    return out


def _ticker_specific(src: Source) -> bool:
    return src.kind in ("sec", "price")


# ---------------------------------------------------------------- adapters


def _to_text(obj: Any, limit: int = 60) -> str:
    """Render whatever Lane B returns into something a model can read."""
    try:
        import pandas as pd

        if isinstance(obj, pd.DataFrame):
            return obj.tail(limit).to_string(max_cols=20)
        if isinstance(obj, pd.Series):
            return obj.tail(limit).to_string()
    except ImportError:
        pass
    if isinstance(obj, dict):
        return "\n".join(f"## {k}\n{_to_text(v, limit)}" for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return json.dumps(list(obj)[:limit], indent=1, default=str)
    return str(obj)


def _real_sources(obj: Any, kind: SourceKind, cutoff: str) -> list[Source]:
    """Lift Source-shaped records if Lane B attaches them (list[dict], a DataFrame with
    id/title/date/excerpt columns, or a dict with a `sources` list). Else []."""
    rows: list[dict] = []
    try:
        import pandas as pd

        if isinstance(obj, pd.DataFrame) and {"id", "title", "date", "excerpt"} <= set(obj.columns):
            rows = obj.to_dict("records")
    except ImportError:
        pass
    if isinstance(obj, dict) and isinstance(obj.get("sources"), list):
        rows = obj["sources"]
    elif isinstance(obj, list) and obj and isinstance(obj[0], dict) and "excerpt" in obj[0]:
        rows = obj
    out = []
    for r in rows:
        r = dict(r)
        r.setdefault("kind", kind)
        r["date"] = str(r["date"])[:10]
        if r["date"] <= cutoff:
            out.append(Source.model_validate(r))
    return out


def _load(kind: SourceKind, loader_name: str, cutoff: str, universe: list[str]) -> tuple[str, list[Source]]:
    if real_data is not None and hasattr(real_data, loader_name):
        try:
            loader = getattr(real_data, loader_name)
            try:
                obj = loader(cutoff, universe)  # preferred signature if Lane B supports it
            except TypeError:
                obj = loader(cutoff)
            digest = _to_text(obj)
            sources = _real_sources(obj, kind, cutoff) or fixture_sources(kind, cutoff, universe)
            return digest, sources
        except Exception as exc:  # noqa: BLE001 deliberate fallback to fixture/mock
            log.warning("backend.app.data.%s failed (%s); using fixture", loader_name, exc)
    sources = fixture_sources(kind, cutoff, universe)
    digest = "\n".join(f"[{s.id}] {s.date} {s.title}: {s.excerpt}" for s in sources)
    return digest, sources


def slice_prices(cutoff: str, universe: list[str]):
    return _load("price", "prices", cutoff, universe)


def slice_fundamentals(cutoff: str, universe: list[str]):
    return _load("sec", "fundamentals", cutoff, universe)


def slice_macro(cutoff: str, universe: list[str]):
    return _load("fred", "macro", cutoff, universe)


def slice_events(cutoff: str, universe: list[str]):
    return _load("gdelt", "events", cutoff, universe)
