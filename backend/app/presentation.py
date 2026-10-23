"""Optional display-only balances, isolated from mandates and trading records."""

import json
import math
from pathlib import Path


def fund_presentation(root: Path, fund_id: str, capital: float) -> dict:
    try:
        snapshot = json.loads(
            (root / "presentation" / "illustrative-fund-metrics.json").read_text()
        )
        if snapshot.get("enabled") is not True:
            return {}
        row = next(item for item in snapshot["funds"] if item.get("fund_id") == fund_id)
        values = {
            key: float(row[key])
            for key in ("nav", "cash", "invested", "pnl", "return_pct")
        }
        if not all(math.isfinite(value) for value in values.values()):
            return {}
        if min(values["nav"], values["cash"], values["invested"]) < 0:
            return {}
        if not math.isclose(
            values["nav"], values["cash"] + values["invested"], abs_tol=0.01
        ):
            return {}
        if not math.isclose(float(row["starting_capital"]), capital, abs_tol=0.01):
            return {}
        if not math.isclose(values["pnl"], values["nav"] - capital, abs_tol=0.01):
            return {}
        expected_return = 100 * values["pnl"] / capital if capital else 0
        if not math.isclose(values["return_pct"], expected_return, abs_tol=0.01):
            return {}
        positions = row["position_count"]
        if (
            not isinstance(positions, int)
            or isinstance(positions, bool)
            or positions < 0
        ):
            return {}
        return {
            "metrics": {**values, "positions": positions},
            "source": "presentation_snapshot",
        }
    except (OSError, ValueError, TypeError, KeyError, StopIteration):
        return {}
