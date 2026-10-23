"""Lazy imports of teammates' modules that may not be on this branch yet."""

from __future__ import annotations

import importlib
from typing import Any


class ComponentUnavailable(RuntimeError):
    """A module a component wraps is not importable (not merged yet, or broken)."""


def load_attr(module: str, attr: str) -> Any:
    """Import ``module`` at call time and return ``attr``; a clear error names what is missing."""
    try:
        mod = importlib.import_module(module)
    except ImportError as exc:
        raise ComponentUnavailable(
            f"{module} is not importable ({exc}); it lives on another branch, "
            f"merge it or inject a replacement through the constructor"
        ) from exc
    try:
        return getattr(mod, attr)
    except AttributeError as exc:
        raise ComponentUnavailable(f"{module} has no attribute {attr!r}") from exc
