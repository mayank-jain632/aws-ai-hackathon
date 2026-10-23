"""Verified Bedrock profiles shared by the API, worker and deployment policy."""

import json
from pathlib import Path

CATALOG = json.loads(
    (Path(__file__).resolve().parents[1] / "model-catalog.json").read_text()
)
DEFAULT_MODEL = CATALOG["default"]
BACKTEST_MODEL = CATALOG["backtester"]
MAIN_MODELS = {item["id"] for item in CATALOG["main"]}


def choices(role):
    return [CATALOG["evaluation"]] if role == "backtester" else CATALOG["main"]


def select_model(role, requested=None, inherited=None):
    if role == "backtester":
        if requested not in (None, BACKTEST_MODEL):
            raise ValueError("Backtesters are pinned to Claude Opus 4.6")
        return BACKTEST_MODEL
    model = requested if requested is not None else inherited or DEFAULT_MODEL
    if model not in MAIN_MODELS:
        raise ValueError("Choose Claude Opus 5.5 or GPT-6.1 Sol")
    return model
