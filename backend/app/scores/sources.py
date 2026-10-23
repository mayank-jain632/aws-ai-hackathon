"""Read-only loaders for every record the scorecard draws on. Each tolerates absence.

Nothing here writes: no desk save, no lessons refresh, no significance recompute.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from backend.app.agent import ROOT
from backend.app.scores.models import AgentRef, Citation

# The container image does not copy reports/ today; SCORES_WF_DIR points at a mounted copy.
WF_ROOT = Path(os.getenv("SCORES_WF_DIR") or ROOT / "reports" / "wf")
SYNTHESIS_CODE = ROOT / "backend" / "app" / "synthesis"
FILE_TOOLS = {"write_file", "edit_file"}
URL = re.compile(r"https?://[^\s)\]>\"'|]+")
ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
ARG = re.compile(r'"(path|query|ticker|symbol|series_id|url|name|strategy_id)"\s*:\s*"([^"]{1,300})"')
URL_KINDS = {
    "sec.gov": "sec",
    "stlouisfed.org": "fred",
    "x.com": "x",
    "twitter.com": "x",
    "gdeltproject.org": "gdelt",
    "financialdatasets.ai": "financial datasets",
    "alpaca.markets": "broker",
}


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def read_jsonl(path: Path) -> list[dict]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def rel(path: Path) -> str:
    path = Path(path)
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def fund_dir(manager) -> Path:
    return Path(manager.registry).parent


def workspace(manager) -> Path:
    return fund_dir(manager) / "workspace"


def roster(manager) -> dict[str, dict]:
    agents = {}
    for agent in getattr(manager, "agents", {}).values():
        state = getattr(agent, "state", {}) or {}
        agents[agent.id] = {
            "id": agent.id,
            "name": getattr(agent, "name", agent.id),
            "role": getattr(agent, "role", "unknown"),
            "model": getattr(agent, "model", None),
            "strategy_id": state.get("strategy_id"),
            "activity": state.get("activity", []),
        }
    return agents


def agent_ref(agents: dict, agent_id: str | None, attribution="recorded") -> AgentRef:
    found = agents.get(agent_id or "")
    if found:
        return AgentRef(
            id=found["id"],
            name=found["name"],
            role=found["role"],
            specialty=found["name"],
            attribution=attribution,
        )
    return AgentRef(
        id=agent_id,
        name=agent_id or "not recorded",
        role="not in this fund's roster",
        attribution=attribution,
    )


def tool_calls(agents: dict) -> list[dict]:
    calls = []
    for agent in agents.values():
        for event in agent["activity"]:
            if event.get("kind") != "tool":
                continue
            detail = event.get("detail") or "{}"
            try:
                args = json.loads(detail)
            except ValueError:
                # Activity details are cut at 12,000 characters, so long write_file calls arrive truncated.
                args = {k: v for k, v in ARG.findall(detail[:2000])} or {"raw": detail[:300]}
            calls.append(
                {"agent_id": agent["id"], "tool": event.get("label", ""), "args": args, "time": event.get("time", "")}
            )
    return sorted(calls, key=lambda c: c["time"])


def summarize_args(args: Any) -> str:
    if not isinstance(args, dict):
        return str(args)[:200]
    keys = ("query", "ticker", "tickers", "symbol", "series_id", "url", "path", "name", "strategy_id", "text")
    parts = [f"{k}={args[k]}" for k in keys if k in args]
    return ("; ".join(str(p) for p in parts) or json.dumps(args)[:200])[:240]


def file_authors(calls: list[dict]) -> dict[str, list[str]]:
    authors: dict[str, list[str]] = {}
    for call in calls:
        path = call["args"].get("path") if isinstance(call["args"], dict) else None
        if call["tool"] in FILE_TOOLS and path:
            path = str(path).lstrip("./")
            if call["agent_id"] not in authors.setdefault(path, []):
                authors[path].append(call["agent_id"])
    return authors


def url_kind(url: str) -> str:
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    return next((kind for domain, kind in URL_KINDS.items() if host.endswith(domain)), "web")


def memo_citations(path: str, text: str, limit: int = 25) -> list[Citation]:
    """URLs cited in a markdown memo. Kind is inferred from the URL host."""
    out = []
    for line in text.splitlines():
        for url in URL.findall(line):
            url = url.rstrip(".,;")
            date = ISO_DATE.search(line)
            title = URL.sub("", line).strip(" -*#>[]():|`") or url
            out.append(
                Citation(
                    id=f"{path}#{len(out) + 1}",
                    kind=url_kind(url),
                    title=title[:160],
                    date=date.group(1) if date else None,
                    url=url,
                    excerpt=line.strip()[:300],
                )
            )
            if len(out) >= limit:
                return out
    return out


def read_memo(root: Path, path: str) -> tuple[str | None, float | None]:
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        return None, None
    return target.read_text(errors="replace"), target.stat().st_mtime


def synthesis_runs(desk) -> list[dict]:
    runs = read_json(Path(desk.path).with_name("synthesis.json"))
    return runs if isinstance(runs, list) else []


def latest(runs: list[dict], kind: str, strategy_id: str | None) -> dict | None:
    matches = [r for r in runs if r.get("kind") == kind and r.get("strategy_id") == strategy_id]
    return matches[-1] if matches else None


def walk_forward(root: Path = WF_ROOT) -> dict | None:
    """The newest walk-forward run under reports/wf, preferring the frozen `final` run."""
    if not root.is_dir():
        return None
    runs = [d for d in root.iterdir() if (d / "manifest.json").is_file()]
    if not runs:
        return None
    run = next((d for d in runs if d.name == "final"), max(runs, key=lambda d: d.stat().st_mtime))
    stats, attribution = {}, {}
    for window in ("test", "all", "dev"):
        folder = run / f"results_{window}"
        if (data := read_json(folder / "stats.json")) is not None:
            stats[window] = data
        try:
            with (folder / "attribution.csv").open() as handle:
                attribution[window] = {row[""]: row for row in csv.DictReader(handle)}
        except (OSError, KeyError):
            pass
    decisions = sorted((run / "decisions").glob("*.json"))
    decision = read_json(decisions[-1]) if decisions else None
    audit_path = root / "audit_clean" / "audit.json"
    summary = folder_text(run / "results_test" / "summary.md") or folder_text(run / "results_all" / "summary.md")
    return {
        "dir": run,
        "manifest": read_json(run / "manifest.json") or {},
        "stats": stats,
        "attribution": attribution,
        "decision": decision,
        "decision_path": decisions[-1] if decisions else None,
        "n_decisions": len(decisions),
        "audit": read_json(audit_path),
        "audit_path": audit_path,
        "audit_note": folder_text(root / "audit_clean" / "audit.md"),
        "summary": summary,
    }


def folder_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except OSError:
        return None
