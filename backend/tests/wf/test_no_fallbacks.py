import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "app"
FILES = [
    ROOT / "wf" / n for n in ("llm.py", "analysts.py", "orders.py", "pipeline.py")
] + [
    ROOT / "agents" / "strategy.py",
    ROOT / "agents" / "execution.py",
]
BANNED_NAMES = {
    "mock_mode",
    "_mock_memo",
    "fixture",
    "converse",
    "run_analyst",
    "_load",
}


def test_no_fallback_paths():
    for f in FILES:
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = {a.name for a in node.names}
                assert not names & BANNED_NAMES, (f, names)
                assert "data_access" not in (node.module or ""), f
            elif isinstance(node, ast.Call):
                fn = node.func
                name = (
                    fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                )
                if f.name == "llm.py" and name == "converse":
                    continue  # the boto client's own converse, not base.converse
                assert name not in BANNED_NAMES, (f, name)
            elif isinstance(node, ast.Attribute) and node.attr in {
                "mock_mode",
                "_mock_memo",
                "fixture",
            }:
                raise AssertionError((f, node.attr))
