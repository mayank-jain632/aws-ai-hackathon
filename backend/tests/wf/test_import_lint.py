"""Static scan: agent-side modules must not be able to reach future data."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
AGENT_SIDE = [*sorted((APP / "agents").rglob("*.py"))]
AGENT_SIDE += [APP / "wf" / f"{n}.py" for n in ("pit", "analysts", "stages", "pipeline", "llm", "orders")]
AGENT_SIDE = [p for p in AGENT_SIDE if p.exists()]
FORBIDDEN_MODULE_PARTS = ("wf.market", "prices_full")
FORBIDDEN_NAMES = {"last_close", "prices_full"}


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if any(part in a.name for part in FORBIDDEN_MODULE_PARTS):
                    bad.append(f"import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(part in mod for part in FORBIDDEN_MODULE_PARTS):
                bad.append(f"from {mod} import ...")
            if mod.endswith("wf") and any(a.name == "market" for a in node.names):
                bad.append(f"from {mod} import market")
            if mod.endswith("market") and node.level:
                bad.append(f"from {'.' * node.level}{mod} import ...")
            if node.level and any(a.name == "market" for a in node.names):
                bad.append("from . import market")
            bad += [f"from {mod} import {a.name}" for a in node.names if a.name in FORBIDDEN_NAMES]
    return bad


def test_scan_covers_pit() -> None:
    assert APP / "wf" / "pit.py" in AGENT_SIDE


@pytest.mark.parametrize("path", AGENT_SIDE, ids=lambda p: str(p.relative_to(APP)))
def test_agent_side_module_does_not_import_future_data(path: Path) -> None:
    assert _violations(path) == []


def test_pit_does_not_use_legacy_data_access() -> None:
    src = (APP / "wf" / "pit.py").read_text(encoding="utf-8")
    assert "data_access" not in src.replace("legacy loaders", "")
    assert "agents" not in {n.module.split(".")[2] for n in ast.walk(ast.parse(src))
                            if isinstance(n, ast.ImportFrom) and n.module and n.module.count(".") >= 2}


def test_lint_detects_violation(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("from backend.app.wf.market import load_bars\nfrom backend.app.wf import market\n")
    assert len(_violations(f)) == 2
