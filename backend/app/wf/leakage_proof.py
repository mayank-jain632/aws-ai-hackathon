"""Evidence that agents cannot see past the decision date, on the REAL data and prompts.

For every decision date the exact inputs the agents are fed (the five analyst prompts, the
execution context and the last close) are rebuilt from three copies of the data:

    real       data/wf as is
    truncated  every row not public at the date removed
    poisoned   every row not public at the date overwritten with absurd sentinels

If the model's inputs are byte-identical across all three, nothing dated after the decision
can reach it through the data channel. Two more checks keep the proof honest: every ISO date
printed in any prompt must be <= the decision date, and the poison must be present in the
poisoned files (otherwise "identical" would prove nothing). No model is called.

    uv run python -m backend.app.wf.leakage_proof --out reports/wf/leakage_proof
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from backend.app.wf import market
from backend.app.wf.analysts import build_prompt
from backend.app.wf.calendar import decision_dates
from backend.app.wf.config import WfConfig
from backend.app.wf.pit import PitData

ANALYSTS = ("technical", "fundamentals", "macro", "sentiment", "geopolitics")
SENTINEL = 9.99e12
ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
SUBDIRS = ("prices", "fred", "sec")


def _copy_small(src: Path, dst: Path) -> None:
    """Copy the CSVs the PIT layer reads; skip the large raw SEC cache."""
    for sub in SUBDIRS:
        (dst / sub).mkdir(parents=True, exist_ok=True)
        for p in (src / sub).glob("*.csv"):
            shutil.copy(p, dst / sub / p.name)


def make_variant(src: Path, dst: Path, as_of: str, mode: str) -> None:
    """mode is 'truncate' or 'poison'; rows public at ``as_of`` are never touched."""
    _copy_small(src, dst)
    for p in (dst / "prices").glob("*.csv"):
        df = pd.read_csv(p)
        if mode == "truncate":
            df = df[df["date"] <= as_of]
        else:
            df.loc[df["date"] > as_of, ["open", "high", "low", "close", "volume"]] = SENTINEL
        df.to_csv(p, index=False)
    macro = pd.read_csv(dst / "fred" / "macro.csv")
    if mode == "truncate":
        macro = macro[macro["available"] <= as_of]
    else:
        macro.loc[macro["available"] > as_of, "value"] = SENTINEL
    macro.to_csv(dst / "fred" / "macro.csv", index=False)
    fund = pd.read_csv(dst / "sec" / "fundamentals.csv")
    if mode == "truncate":
        fund = fund[fund["filed"] < as_of]
    else:
        fund.loc[fund["filed"] >= as_of, ["revenue", "net_income", "total_debt"]] = SENTINEL
    fund.to_csv(dst / "sec" / "fundamentals.csv", index=False)
    k8 = pd.read_csv(dst / "sec" / "filings_8k.csv")
    if mode == "truncate":
        k8 = k8[k8["filed"] < as_of]
    else:
        k8.loc[k8["filed"] >= as_of, ["items", "item_titles", "description"]] = "SENTINEL 8.01 7.01"
    k8.to_csv(dst / "sec" / "filings_8k.csv", index=False)


def model_inputs(pit: PitData, as_of: str, universe: list[str]) -> dict:
    """Everything the stages read, as strings: the analyst user prompts and execution context."""
    prompts = {}
    for analyst in ANALYSTS:
        digest, sources = pit.evidence(analyst, as_of, universe)
        prompts[analyst] = build_prompt(analyst, as_of, universe, digest, sources, lambda x: x)
    ctx = pit.execution_context(as_of, universe)
    return {"prompts": prompts, "context": ctx, "last_close": {t: pit.last_close(as_of, t) for t in universe}}


def _digest(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def latest_prompt_date(inputs: dict) -> str | None:
    found = [d for text in inputs["prompts"].values() for d in ISO.findall(text)]
    return max(found) if found else None


def poison_present(variant_dir: Path, as_of: str) -> bool:
    """True if the poisoned price files really hold sentinels after ``as_of``."""
    for p in (variant_dir / "prices").glob("*.csv"):
        df = pd.read_csv(p)
        later = df[df["date"] > as_of]
        if len(later) and (later["close"] == SENTINEL).all():
            return True
    return False


def prove_date(src: Path, as_of: str, universe: list[str], tmp: Path) -> dict:
    real = model_inputs(PitData(src), as_of, universe)
    out = {"as_of": as_of, "real_hash": _digest(real), "latest_date_in_prompts": latest_prompt_date(real)}
    for mode in ("truncate", "poison"):
        variant = tmp / mode
        if variant.exists():
            shutil.rmtree(variant)
        make_variant(src, variant, as_of, mode)
        out[f"{mode}_identical"] = _digest(model_inputs(PitData(variant), as_of, universe)) == out["real_hash"]
        if mode == "poison":
            out["poison_was_present"] = poison_present(variant, as_of)
    out["no_future_dates"] = out["latest_date_in_prompts"] is None or out["latest_date_in_prompts"] <= as_of
    out["ok"] = all(out[k] for k in ("truncate_identical", "poison_identical", "poison_was_present", "no_future_dates"))
    return out


def prove(dates: list[str], universe: list[str], data_dir: Path | None = None) -> dict:
    src = Path(data_dir) if data_dir else market.DEFAULT_DATA_DIR
    with tempfile.TemporaryDirectory() as t:
        rows = [prove_date(src, d, universe, Path(t)) for d in dates]
    return {
        "dates": len(rows),
        "all_ok": all(r["ok"] for r in rows),
        "failures": [r["as_of"] for r in rows if not r["ok"]],
        "rows": rows,
    }


def _markdown(result: dict) -> str:
    verdict = "PASS" if result["all_ok"] else "FAIL"
    lines = [
        "# Leakage proof on real data",
        "",
        f"{verdict}: {result['dates']} decision dates; failures: {result['failures'] or 'none'}.",
        "",
        "For each date the exact analyst prompts, execution context and last closes were rebuilt from the real",
        "data, from data truncated at the date, and from data whose future rows were overwritten with 9.99e12.",
        "",
        "| date | truncated identical | poisoned identical | poison present | latest date in prompts |",
        "|---|---|---|---|---|",
    ]
    for r in result["rows"]:
        lines.append(
            f"| {r['as_of']} | {r['truncate_identical']} | {r['poison_identical']} "
            f"| {r['poison_was_present']} | {r['latest_date_in_prompts']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    cfg = WfConfig()
    bars = market.load_bars(tickers=[cfg.reference])
    dates = decision_dates(bars[cfg.reference].index, cfg.first_decision, cfg.last_decision)
    result = prove(dates, list(cfg.universe))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "leakage_proof.json").write_text(json.dumps(result, indent=1))
    (out / "leakage_proof.md").write_text(_markdown(result))
    print(f"{'PASS' if result['all_ok'] else 'FAIL'}: {result['dates']} dates, failures {result['failures']}")


if __name__ == "__main__":
    main()
