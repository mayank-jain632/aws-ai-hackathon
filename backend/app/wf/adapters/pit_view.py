"""Date-bound views over `PitData` (or `masking.MaskedPit`).

`BoundPit` fixes the decision date once, so a component holding it cannot ask for another
date through the public API (`PitView` protocol). `DatedPit` is the reverse shim: it exposes
the legacy date-taking signature that `analysts.run_research` expects while refusing any
date but the bound one.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from backend.app.schema import Source


class BoundPit:
    """`PitData` bound to one decision date; implements `interfaces.PitView`."""

    def __init__(self, pit: Any, as_of: str) -> None:
        self.pit = pit
        self.as_of = as_of

    def evidence(self, analyst: str, universe: Sequence[str]) -> tuple[str, list[Source]]:
        return self.pit.evidence(analyst, self.as_of, list(universe))

    def execution_context(self, tickers: Sequence[str]) -> dict[str, dict]:
        return self.pit.execution_context(self.as_of, list(tickers))

    def last_close(self, ticker: str) -> float:
        return self.pit.last_close(self.as_of, ticker)


class DatedPit:
    """Date-taking facade over a `PitView`; any date other than the bound one is an error."""

    def __init__(self, view: Any) -> None:
        self.view = view

    def _check(self, as_of: str) -> None:
        if as_of != self.view.as_of:
            raise ValueError(f"view is bound to {self.view.as_of}, refusing date {as_of}")

    def evidence(self, analyst: str, as_of: str, universe: Sequence[str]):
        self._check(as_of)
        return self.view.evidence(analyst, universe)

    def execution_context(self, as_of: str, tickers: Sequence[str]) -> dict[str, dict]:
        self._check(as_of)
        return self.view.execution_context(tickers)

    def last_close(self, as_of: str, ticker: str) -> float:
        self._check(as_of)
        return self.view.last_close(ticker)
