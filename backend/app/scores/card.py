"""Build one fund's scorecard from records other lanes already wrote. Read-only.

Fund rings read the fund's desk, mandate, watchdog logs and shared files, plus Chaithu's
walk_forward over the fund's frozen weights. The frozen team walk-forward run (reports/wf)
gets its own panel and never stands in for a fund's own results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from backend.app.desk import desk_for
from backend.app.scores import sources as src
from backend.app.scores.models import (
    AgentRef,
    Citation,
    Factor,
    Provenance,
    Score,
    Scorecard,
    SourceRef,
    SourceStatus,
    ToolCall,
)
from backend.app.watchdog import SWITCH, feedback, halt_reason, store
from backend.app.watchdog.claims import check_strategy_memos

OWNERS = {
    "desk": "Lane 1 roles and desk (Kushagra's 'different agents' chat): strategy, adversarial reviewer and backtester agents",
    "execution": "Lane 4 execution: paper executor agent and the Alpaca paper adapter",
    "watchdog": "Lane 4 moderator (Aaron): watchdog gate",
    "synthesis": "Lane 2, Chaithu's synthesis layer (backend/app/synthesis)",
    "wf": "Lane 2b, Mayank's walk-forward evaluation (backend/app/wf and reports/wf/)",
}
WATCHDOG = AgentRef(name="Watchdog gate (16 deterministic rules, no model)", role="moderator", attribution="system")
GATE = AgentRef(name="Backend gate (desk.evaluate)", role="backend", attribution="system")


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


@dataclass
class Context:
    fund_id: str
    fund: dict
    manager: object
    desk: object
    agents: dict
    calls: list
    authors: dict
    workspace: Path
    strategy: dict | None
    synthesis: list
    wf: dict | None
    notes: list = field(default_factory=list)

    @property
    def sid(self):
        return self.strategy["id"] if self.strategy else None

    @property
    def policy(self) -> dict | None:
        return self.desk.state.get("policy")

    def role_holders(self, role: str) -> list[AgentRef]:
        return [src.agent_ref(self.agents, a["id"], "role holder") for a in self.agents.values() if a["role"] == role]

    def desk_record(self, part: str) -> str:
        return f"{src.rel(self.desk.path)} → {part}"


def not_produced(key, label, question, owner, missing, factors=()) -> Score:
    return Score(
        key=key, label=label, question=question, status="not_produced", owner=owner, missing=missing, factors=list(factors)
    )


def scored(key, label, question, factors, raw, formula, source, owner, value, contributors, scope="fund") -> Score:
    return Score(
        key=key,
        label=label,
        question=question,
        status="scored",
        value=round(max(0.0, min(100.0, value)), 1),
        raw=raw,
        formula=formula,
        source=source,
        owner=owner,
        scope=scope,
        contributors=dedupe(contributors),
        factors=factors,
    )


def dedupe(refs: list[AgentRef]) -> list[AgentRef]:
    seen, out = set(), []
    for ref in refs:
        key = (ref.id, ref.name)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out


def checklist(factors: list[Factor]) -> tuple[float, int, int]:
    """Equal-weight pass share over factors that could be evaluated."""
    counted = [f for f in factors if f.status in ("pass", "fail")]
    for f in counted:
        f.weight = round(1 / len(counted), 4)
    passed = sum(f.status == "pass" for f in counted)
    return (100 * passed / len(counted) if counted else 0.0), passed, len(counted)


def desk_source(ctx: Context, label: str) -> SourceRef:
    return SourceRef(id="desk", label=label, scope="fund", location=src.rel(ctx.desk.path))


def wf_source(ctx: Context, label: str, path: Path) -> SourceRef:
    return SourceRef(id="walk_forward", label=label, scope="firm", location=src.rel(path))


def memo_files(ctx: Context) -> tuple[list[Citation], list[AgentRef], list[str]]:
    """Memo text, URL citations and the agents whose write_file calls produced each memo."""
    cites, writers, found = [], [], []
    for path in ctx.strategy["memo_paths"]:
        text, _ = src.read_memo(ctx.workspace, path)
        if text is None:
            continue
        found.append(path)
        cites += src.memo_citations(path, text)
        writers += [src.agent_ref(ctx.agents, a) for a in ctx.authors.get(path.lstrip("./"), [])]
    return cites, writers, found


def memo_excerpts(ctx: Context, paths: list[str], limit: int = 1500) -> str:
    parts = []
    for path in paths:
        text, _ = src.read_memo(ctx.workspace, path)
        if text:
            parts.append(f"{path}\n{text.strip()[:limit]}")
    return "\n\n".join(parts)


PLAN_FILES = (("fund-plan.md", "Fund plan"), ("research-checklist.md", "Research checklist"))


def plan_context(ctx: Context) -> list[Factor]:
    """The orchestrator's planning files, as context for the mandate ring."""
    factors = []
    for path, label in PLAN_FILES:
        text, mtime = src.read_memo(ctx.workspace, path)
        if text is None:
            continue
        writers = [src.agent_ref(ctx.agents, a) for a in ctx.authors.get(path, [])] or ctx.role_holders("orchestrator")
        factors.append(
            Factor(
                key=f"plan_{path}", label=f"{label} ({path})", value=f"{len(text.split())} words",
                detail="Context only: what the orchestrator planned from the mandate before any strategy",
                agents=writers, reasoning=text.strip()[:4000], reasoning_label=f"{label} as written in the fund's shared files",
                provenance=Provenance(record=f"workspace/{path}", file=src.rel(ctx.workspace / path), time=datetime.fromtimestamp(mtime, UTC).isoformat(), citations=src.memo_citations(path, text)),
            )
        )
    return factors


# ---------------------------------------------------------------- 1. risk / mandate fit


def mandate_fit(ctx: Context) -> Score:
    key, label = "mandate_fit", "Risk / mandate fit"
    question = "Does the current strategy stay inside the client's mandate?"
    if not ctx.strategy:
        return not_produced(key, label, question, OWNERS["desk"], "No strategy registered in this fund yet. A strategy agent registers one with register_strategy.", plan_context(ctx))
    m, s, sid = ctx.fund, ctx.strategy, ctx.sid
    weights = s["weights"]
    test = ctx.desk.state["tests"].get(sid)
    author = [src.agent_ref(ctx.agents, s["author"])]
    where = f"funds.json → {ctx.fund_id}; " + ctx.desk_record(f"strategies[{sid}]")
    outside = sorted(set(weights) - set(m["universe"]))
    top = max(weights, key=weights.get)
    factors = [
        Factor(
            key="universe",
            label="Tickers inside the client's universe",
            value=f"{len(weights) - len(outside)} of {len(weights)} inside" + (f"; outside: {', '.join(outside)}" if outside else ""),
            status="fail" if outside else "pass",
            detail=f"Strategy tickers vs the mandate universe of {len(m['universe'])}: {', '.join(m['universe'])}",
            agents=author,
            reasoning=s["rationale"],
            reasoning_label="Strategy rationale (register_strategy)",
            provenance=Provenance(record=where, time=s["created_at"]),
        ),
        Factor(
            key="position",
            label="Largest position vs mandate cap",
            value=f"{top} {pct(weights[top])} vs cap {m['max_position']:g}%",
            number=weights[top],
            status="pass" if weights[top] <= m["max_position"] / 100 + 1e-9 else "fail",
            detail="Largest target weight in the frozen strategy vs the mandate's max position",
            agents=author,
            reasoning=s["rationale"],
            reasoning_label="Strategy rationale (register_strategy)",
            provenance=Provenance(record=where, time=s["created_at"]),
        ),
    ]
    if test:
        dd = abs(test["metrics"]["portfolio"]["max_drawdown"])
        factors.append(
            Factor(
                key="drawdown",
                label="Tested drawdown vs mandate limit",
                value=f"{pct(dd)} vs limit {m['max_drawdown']:g}%",
                number=dd,
                status="pass" if dd <= m["max_drawdown"] / 100 else "fail",
                detail=f"Max drawdown from the backend backtest, {test['cutoff']} to {test['end']}",
                agents=[GATE],
                reasoning=test.get("limitations"),
                reasoning_label="Recorded limitations of the backend gate",
                provenance=Provenance(record=ctx.desk_record(f"tests[{sid}].metrics.portfolio.max_drawdown"), time=test["time"]),
            )
        )
    else:
        factors.append(
            Factor(
                key="drawdown",
                label="Tested drawdown vs mandate limit",
                value="No backtest yet",
                status="pending",
                detail="Needs a backend backtest of this strategy; left out of the score until then",
                provenance=Provenance(record=ctx.desk_record(f"tests[{sid}]")),
            )
        )
    unmodeled = [
        name
        for name, on in (
            (f"cash reserve {m.get('min_cash', 0):g}%", m.get("min_cash", 0)),
            (f"exclusions ({m.get('exclusions')})", m.get("exclusions")),
            (f"{m.get('rebalance')} rebalancing", m.get("rebalance", "monthly") != "monthly"),
        )
        if on
    ]
    factors.append(
        Factor(
            key="constraints",
            label="Mandate constraints the evaluation engine can model",
            value="All modeled" if not unmodeled else "Not modeled: " + "; ".join(unmodeled),
            status="fail" if unmodeled else "pass",
            detail="desk.execution_checks refuses execution while the mandate needs a constraint the monthly backtest cannot model",
            agents=[GATE],
            provenance=Provenance(record=f"funds.json → {ctx.fund_id}.min_cash / exclusions / rebalance"),
        )
    )
    factors.append(
        Factor(
            key="consent",
            label="Client trading consent",
            value=("Paper trading permitted" if m.get("trading_allowed") else "Research only") + f", {m.get('mode')} mode",
            detail="Context only; not part of the fit score",
            provenance=Provenance(record=f"funds.json → {ctx.fund_id}.trading_allowed / mode"),
        )
    )
    value, passed, total = checklist(factors)
    return scored(
        key, label, question, factors + plan_context(ctx),
        raw=f"{passed} of {total} mandate checks pass for {s['name']}",
        formula="100 × checks passed ÷ checks evaluated (pending checks are left out)",
        source=desk_source(ctx, "Fund mandate and the desk's frozen strategy"),
        owner=OWNERS["desk"], value=value, contributors=author + [GATE],
    )


# ---------------------------------------------------------------- 2. confidence in trades


def confidence(ctx: Context) -> Score:
    key, label = "confidence", "Confidence in trades"
    question = "How strongly do the analysts behind the book agree with each position?"
    run = src.latest(ctx.synthesis, "synthesis", ctx.sid) if ctx.strategy else None
    if run:
        conviction, weights = run["seed"]["conviction"], ctx.strategy["weights"]
        analysts = run.get("memos") or []
        n = max(len(analysts), 1)
        x = sum(w * conviction.get(t, 0.0) for t, w in weights.items()) / n
        author = src.agent_ref(ctx.agents, run.get("agent"))
        cites = memo_files(ctx)[0]
        factors = [
            Factor(
                key=f"conviction_{t}",
                label=t,
                value=f"net conviction {conviction.get(t, 0.0):+.2f}, weight {pct(w)}",
                number=conviction.get(t),
                weight=round(w, 4),
                status="pass" if conviction.get(t, 0.0) > 0 else "fail",
                detail=f"Sum of signed confidences from {', '.join(analysts) or 'the cited memos'} (long +, avoid -)",
                agents=[author] + [AgentRef(name=f"{a} analyst", role="research", specialty=a) for a in analysts],
                reasoning=ctx.strategy["rationale"] + "\n\nChanges my mind: " + ctx.strategy["changes_my_mind"],
                reasoning_label="Strategy rationale and change trigger",
                provenance=Provenance(record=f"synthesis.json → {run['id']}.seed.conviction.{t}", file=", ".join(run.get("memo_paths", [])), time=run["time"], citations=cites),
            )
            for t, w in weights.items()
        ] + [
            Factor(key=f"dropped_{t}", label=f"{t} (dropped)", value=why, detail="Left out of the book by the seed", provenance=Provenance(record=f"synthesis.json → {run['id']}.seed.dropped.{t}", time=run["time"]))
            for t, why in run["seed"].get("dropped", {}).items()
        ]
        return scored(
            key, label, question, factors,
            raw=f"weighted net conviction {x:+.2f} per analyst across {n} memos",
            formula="50 × (1 + Σ weight × net conviction ÷ number of analysts); net conviction is the signed sum of analyst confidences",
            source=SourceRef(id="synthesis", label="Synthesis seed (SeedDetail.conviction)", scope="fund", location=src.rel(Path(ctx.desk.path).with_name("synthesis.json"))),
            owner=OWNERS["synthesis"], value=50 * (1 + x), contributors=[author],
        )
    return not_produced(
        key, label, question, OWNERS["synthesis"],
        "Needs analyst conviction for this fund's strategy: a synthesis run records it in synthesis.json when the strategy agent uses the synthesize tool. The team walk-forward panel shows the frozen run's conviction separately.",
    )


def wf_sources_for(decision: dict, ids: list[str]) -> list[Citation]:
    index = {s["id"]: s for s in decision.get("sources", [])}
    return [
        Citation(id=i, kind=index[i]["kind"], title=index[i]["title"], date=index[i].get("date"), url=index[i].get("url"), excerpt=index[i].get("excerpt", "")[:400])
        for i in ids
        if i in index
    ]


def team_confidence(ctx: Context) -> Score:
    key, label, question = "team_confidence", "Strategist conviction", "How strongly did the frozen run's strategist back each position in its latest week?"
    decision = ctx.wf and ctx.wf["decision"]
    if not decision:
        return team_missing(key, label, question)
    plans = decision["plan"]["plans"]
    total = sum(p["target_weight"] for p in plans) or 1
    value = 100 * sum(p["target_weight"] * p["conviction"] for p in plans) / total
    path = src.rel(ctx.wf["decision_path"])
    strategist = AgentRef(name="Strategist (walk-forward run)", role="strategy", specialty="strategy", attribution="system")
    factors = []
    for i, p in enumerate(plans):
        views = [(m["analyst"], v) for m in decision["memos"] for v in m["views"] if v["ticker"] == p["ticker"]]
        notes = "\n".join(f"{a} analyst: {v['stance']} at {v['confidence']:.2f}. {v['note']}" for a, v in views)
        view_ids = [sid for _, v in views for sid in v["sources"]]
        factors.append(
            Factor(
                key=f"plan_{p['ticker']}",
                label=p["ticker"],
                value=f"conviction {p['conviction']:.2f}, target {pct(p['target_weight'])}",
                number=p["conviction"],
                weight=round(p["target_weight"] / total, 4),
                status="info",
                detail=f"Strategist conviction for {p['ticker']} on {decision['decision_date']}, with each analyst's view",
                agents=[strategist] + [AgentRef(name=f"{a} analyst (walk-forward run)", role="research", specialty=a, attribution="system") for a, _ in views],
                reasoning=f"{p['rationale']}\n\nChanges my mind: {p['changes_my_mind']}\n\nAnalyst views:\n{notes}",
                reasoning_label="Strategist rationale and analyst views, as recorded",
                provenance=Provenance(
                    record=f"{path} → plan.plans[{i}]",
                    file=path,
                    time=decision["decision_date"],
                    citations=wf_sources_for(decision, list(dict.fromkeys(p.get("memo_sources", []) + view_ids))),
                ),
            )
        )
    return scored(
        key, label, question, factors,
        raw=f"weighted conviction {value / 100:.2f} over {len(plans)} positions, decision {decision['decision_date']} ({decision['plan'].get('strategy_name', '')})",
        formula="100 × Σ(target weight × conviction) ÷ Σ target weight",
        source=wf_source(ctx, "Frozen walk-forward decision record (latest week)", ctx.wf["decision_path"]),
        owner=OWNERS["wf"], value=value, contributors=dedupe([a for f in factors for a in f.agents]), scope="firm",
    )


# ---------------------------------------------------------------- 3. strategy


def strategy_score(ctx: Context) -> Score:
    key, label = "strategy", "Strategy score"
    question = "Did the strategy clear adversarial review, cite real memos and get the approvals it needs?"
    if not ctx.strategy:
        return not_produced(key, label, question, OWNERS["desk"], "No strategy registered in this fund yet.")
    s, sid = ctx.strategy, ctx.sid
    review = ctx.desk.state["reviews"].get(sid)
    cites, writers, found = memo_files(ctx)
    claims = check_strategy_memos(ctx.workspace, s)
    integrity = [e for e in claims if e.details.get("problem") in ("lookahead", "edited_after_freeze")]
    factors = [
        Factor(
            key="review",
            label="Adversarial review",
            value=review["verdict"] if review else "No review recorded",
            status="info" if review and ctx.desk.autonomous_paper() and review["verdict"] != "APPROVE" else "pass" if review and review["verdict"] == "APPROVE" else "fail",
            detail="An independent final review is required; findings are advisory under the autonomous paper mandate" if ctx.desk.autonomous_paper() else "Execution requires an APPROVE from an agent other than the author",
            agents=[src.agent_ref(ctx.agents, review["author"])] if review else ctx.role_holders("adversarial"),
            reasoning=review["critique"] if review else None,
            reasoning_label="Adversarial critique (review_strategy)",
            provenance=Provenance(record=ctx.desk_record(f"reviews[{sid}]"), time=review["time"] if review else None),
        ),
        Factor(
            key="memos",
            label="Cited memos exist in the fund's shared files",
            value=f"{len(found)} of {len(s['memo_paths'])} found",
            status="pass" if len(found) == len(s["memo_paths"]) else "fail",
            detail="Each memo_path the strategy cites, looked up in the fund workspace",
            agents=dedupe(writers),
            reasoning=memo_excerpts(ctx, found) or None,
            reasoning_label="Memo text the strategy cites (first 1,500 characters each)",
            provenance=Provenance(record=ctx.desk_record(f"strategies[{sid}].memo_paths"), file=", ".join(s["memo_paths"]), time=s["created_at"], citations=cites),
        ),
        Factor(
            key="integrity",
            label="Memos dated before cutoff and unchanged since freeze",
            value="Clean" if not integrity else f"{len(integrity)} problem(s)",
            status="pass" if found and not integrity else ("fail" if integrity else "pending"),
            detail="Watchdog claim check: no cited date after the cutoff, no edit after the strategy was frozen",
            agents=[WATCHDOG],
            reasoning="\n".join(e.message for e in integrity) or None,
            reasoning_label="Watchdog claim findings",
            provenance=Provenance(record="watchdog.claims.check_strategy_memos over " + ", ".join(s["memo_paths"]), time=s["created_at"]),
        ),
    ]
    policy = ctx.policy
    if policy and policy.get("approval_required", True):
        approved = ctx.desk.human_approved(sid)
        factors.append(
            Factor(
                key="approval",
                label="Human approval under the current policy",
                value="Approved" if approved else "Not approved yet",
                status="pass" if approved else "fail",
                detail="The mandate requires a person to approve this strategy; approval is bound to the current policy and exact engine evaluation",
                agents=[AgentRef(name="Human analyst", role="human", attribution="system")],
                provenance=Provenance(record=ctx.desk_record(f"approvals[{sid}]")),
            )
        )
    factors.append(
        Factor(
            key="thesis",
            label="Thesis and change trigger",
            value=s["name"],
            detail="Context only: what the strategy agent recorded when it froze the book",
            agents=[src.agent_ref(ctx.agents, s["author"])],
            reasoning=f"{s['rationale']}\n\nChanges my mind: {s['changes_my_mind']}\n\nWeights: " + ", ".join(f"{t} {pct(w)}" for t, w in s["weights"].items()),
            reasoning_label="Strategy rationale (register_strategy)",
            provenance=Provenance(record=ctx.desk_record(f"strategies[{sid}]"), time=s["created_at"], citations=cites),
        )
    )
    value, passed, total = checklist(factors)
    return scored(
        key, label, question, factors,
        raw=f"{passed} of {total} strategy requirements met",
        formula="100 × requirements met ÷ requirements evaluated",
        source=desk_source(ctx, "Desk strategy, review and approval records"),
        owner=OWNERS["desk"], value=value,
        contributors=[src.agent_ref(ctx.agents, s["author"])] + (factors[0].agents if review else []) + dedupe(writers) + [WATCHDOG],
    )


# ---------------------------------------------------------------- 4. backtest


def backtest_score(ctx: Context) -> Score:
    key, label = "backtest", "Backtest score"
    question = "Did the frozen book pass the backend's historical gate under the human policy?"
    test = ctx.desk.state["tests"].get(ctx.sid) if ctx.strategy else None
    if not test:
        return not_produced(key, label, question, OWNERS["desk"], "No backend backtest for this fund's strategy. A backtester bound to the strategy calls run_backtest.")
    policy = ctx.policy or {}
    p, b = test["metrics"]["portfolio"], test["metrics"]["baseline"]
    excess = p["total_return"] - b["total_return"]
    bound = [src.agent_ref(ctx.agents, a["id"]) for a in ctx.agents.values() if a["strategy_id"] == ctx.sid and a["role"] == "backtester"]
    record = ctx.desk_record(f"tests[{ctx.sid}]")
    tickers = ", ".join(ctx.strategy["weights"])
    prices = Citation(
        id="data/wf" if test.get("engine") == "wf" else "data/prices", kind="price", title=f"Daily closes for {tickers} and SPY (repository price snapshots)",
        date=f"{test['cutoff']} to {test['end']}", excerpt="; ".join(test.get("assumptions", [])) or test.get("limitations", "Historical snapshot; engine not recorded"),
    )
    rows = [
        ("drawdown", "Max drawdown vs policy limit", f"{pct(abs(p['max_drawdown']))} vs limit {pct(policy.get('max_drawdown', 0), 0)}", abs(p["max_drawdown"])),
        ("sharpe", "Sharpe vs policy minimum", f"{p['sharpe']:.2f} vs minimum {policy.get('min_sharpe', 0):g}", p["sharpe"]),
        ("excess_return", "Return over SPY vs policy minimum", f"{excess:+.1%} ({pct(p['total_return'])} vs SPY {pct(b['total_return'])}) vs minimum {policy.get('min_excess_return', 0):+.1%}", excess),
        ("mandate", "Universe and position limit at test time", "Inside policy" if test["checks"]["mandate"] else "Outside policy", None),
    ]
    factors = [
        Factor(
            key=k, label=lbl, value=val, number=num,
            status="pass" if test["checks"][k] else "fail",
            detail=f"Backend metric from the test window {test['cutoff']} to {test['end']}; threshold from the human desk policy",
            agents=bound + [GATE],
            reasoning=test.get("limitations"),
            reasoning_label="Recorded limitations of the backend gate",
            provenance=Provenance(record=f"{record}.checks.{k}", time=test["time"], citations=[prices]),
        )
        for k, lbl, val, num in rows
    ]
    if not ctx.desk.test_is_current(ctx.sid):
        factors.append(Factor(key="stale", label="Evaluation is no longer current", value="Stale: execution needs a re-test", status="fail", detail="The test must match the current policy, frozen strategy and engine version", provenance=Provenance(record=record)))
    factors.append(
        Factor(
            key="metrics", label="Portfolio metrics", value=f"total {pct(p['total_return'])}, CAGR {pct(p['cagr'])}, Sharpe {p['sharpe']:.2f}",
            detail=f"Engine: {test.get('engine', 'not recorded')} / {test.get('engine_version', 'not recorded')}; label: {test.get('label', 'not recorded')}; author model: {test.get('author_model') or 'not recorded'}. {test.get('leakage', '')}", agents=[GATE], provenance=Provenance(record=f"{record}.metrics", time=test["time"], citations=[prices]),
        )
    )
    value, passed, total = checklist(factors)
    return scored(
        key, label, question, factors,
        raw=f"{test['verdict']}: {passed} of {total} checks" + (" (test is stale)" if total > 4 else ""),
        formula="100 × checks passed ÷ checks evaluated: the four gate checks (drawdown, Sharpe, excess return over SPY, mandate), plus a fifth that counts as failed when the test no longer matches the current policy, frozen strategy and engine version",
        source=desk_source(ctx, "Backend backtest record"),
        owner=OWNERS["desk"], value=value, contributors=bound + [GATE],
    )


# ---------------------------------------------------------------- 5. statistical significance


SIGNIFICANCE_CACHE: dict[tuple, dict] = {}
SIG_ENGINE = AgentRef(name="Chaithu's walk_forward (backend/app/synthesis/significance.py)", role="backend", attribution="system")


def strategy_significance(ctx: Context) -> tuple[dict | None, dict | None, str]:
    """Chaithu's walk_forward over the fund's frozen weights, read-only and cached.

    Runs for every registered strategy. A person's recorded run in synthesis.json is
    preferred and sets the horizon. Strategies are immutable and the price snapshot is
    fixed, so a cached result equals a fresh one. Any failure means no number at all.
    """
    if not ctx.strategy:
        return None, None, "No strategy registered in this fund yet."
    recorded = src.latest(ctx.synthesis, "significance", ctx.sid)
    try:
        from backend.app import data
        from backend.app.synthesis import significance as engine

        horizon = recorded["horizon_days"] if recorded else engine.DEFAULT_HORIZON_DAYS
        key = (ctx.sid, horizon)
        if key not in SIGNIFICANCE_CACHE:
            weights = ctx.strategy["weights"]
            closes = data.prices_full(list(weights) + [data.REFERENCE])
            result = engine.walk_forward(ctx.sid, weights, horizon_days=horizon, closes=closes).model_dump()
            result["snapshot"] = [closes.index.min().date().isoformat(), closes.index.max().date().isoformat()]
            SIGNIFICANCE_CACHE[key] = result
    except Exception as error:  # noqa: BLE001 any failure means no number, only the reason
        return None, recorded, f"Chaithu's walk_forward could not evaluate this strategy: {type(error).__name__}: {error}"
    return SIGNIFICANCE_CACHE[key], recorded, ""


def how_produced(ctx: Context, recorded: dict | None) -> str:
    if recorded:
        return f"Recorded: a person ran the significance route at {recorded['time']} (synthesis.json → {recorded['id']})"
    return f"Computed when this page loaded by Chaithu's walk_forward (the same function as GET /api/funds/{ctx.fund_id}/desk/strategies/{ctx.sid}/significance); not a recorded pipeline result"


def inputs_text(sig: dict, result: dict | None) -> str:
    text = f"{sig['horizon_days']}-day horizon, {sig['n_windows']} windows"
    if result and len(result.get("windows", [])) == sig["n_windows"]:
        w = result["windows"]
        text += f"; window starts {w[0]['cutoff']} to {w[-1]['cutoff']}, last window ends {w[-1]['end']}"
    if result and result.get("snapshot"):
        text += f"; price snapshot {result['snapshot'][0]} to {result['snapshot'][1]}"
    return text


def plain_reading(lo: float, hi: float) -> str:
    if lo > 0:
        return "Beat SPY: the 95% interval for mean excess return is above zero"
    if hi < 0:
        return "Trailed SPY: the 95% interval for mean excess return is below zero"
    return "No significant edge over SPY: the 95% interval for mean excess return includes zero"


def significance_provenance(ctx: Context, recorded: dict | None) -> Provenance:
    tickers = ", ".join(ctx.strategy["weights"])
    prices = Citation(id="data/prices", kind="price", title=f"Daily closes for {tickers}, SPY and equal weight (repository price snapshots)", excerpt="Existing Desk backtest engine run from every monthly cutoff for a fixed horizon.")
    return Provenance(record=how_produced(ctx, recorded), file="backend/app/synthesis/significance.py", time=recorded["time"] if recorded else None, citations=[prices])


def significance(ctx: Context) -> Score:
    key, label = "significance", "Statistical significance"
    question = "Is the edge over SPY distinguishable from noise?"
    result, recorded, missing = strategy_significance(ctx)
    sig = recorded or result
    if not sig:
        return not_produced(key, label, question, OWNERS["synthesis"], missing)
    t, p = sig["t_stat_vs_spy"], sig["p_value_vs_spy"]
    one_sided = p / 2 if t > 0 else 1 - p / 2
    lo, hi = sig["ci95_excess_vs_spy"]
    reading = plain_reading(lo, hi)
    prov = significance_provenance(ctx, recorded)
    rows = [
        ("reading", "Plain reading", reading, None, None),
        ("p", "One-sided p, mean excess over SPY > 0", f"{one_sided:.3f} (t = {t:.2f}, two-sided p = {p:.3f})", one_sided, 1.0),
        ("hit_spy", "Windows beating SPY (hit rate)", f"{pct(sig['hit_rate_vs_spy'], 0)} of {sig['n_windows']}", sig["hit_rate_vs_spy"], None),
        ("hit_equal", "Windows beating equal weight", pct(sig["hit_rate_vs_equal"], 0), sig["hit_rate_vs_equal"], None),
        ("mean", "Mean excess over SPY per window", f"{sig['mean_excess_vs_spy']:+.2%}", sig["mean_excess_vs_spy"], None),
        ("ci", "95% CI, mean excess over SPY (bootstrap)", f"[{lo:+.2%}, {hi:+.2%}]", None, None),
        ("drawdown", "Worst window drawdown", pct(abs(sig["worst_drawdown"])), sig["worst_drawdown"], None),
        ("inputs", "Inputs", inputs_text(sig, result), sig["n_windows"], None),
    ]
    factors = [
        Factor(
            key=k, label=lbl, value=val, number=num, weight=w, status="info", detail=prov.record, agents=[SIG_ENGINE],
            reasoning=sig["limitations"], reasoning_label="Limitations, verbatim from Significance", provenance=prov,
        )
        for k, lbl, val, num, w in rows
    ]
    return scored(
        key, label, question, factors,
        raw=f"{'Recorded' if recorded else 'Computed on page load'}: t = {t:.2f}, two-sided p = {p:.3f}, hit rate {pct(sig['hit_rate_vs_spy'], 0)}, 95% CI [{lo:+.2%}, {hi:+.2%}] over {sig['n_windows']} windows. {reading}",
        formula="100 × (1 − one-sided p) that mean excess return over SPY is above zero, from the walk_forward t-test",
        source=SourceRef(id="synthesis", label=prov.record, scope="fund", location="backend/app/synthesis/significance.py"),
        owner=OWNERS["synthesis"], value=100 * (1 - one_sided), contributors=[SIG_ENGINE],
    )


def team_stats(ctx: Context) -> dict | None:
    return ctx.wf and (ctx.wf["stats"].get("test") or ctx.wf["stats"].get("all"))


def team_significance(ctx: Context) -> Score:
    key, label, question = "team_significance", "Significance vs SPY", "Did the frozen pipeline beat SPY by more than noise?"
    stats = team_stats(ctx)
    if not stats:
        return team_missing(key, label, question)
    window = stats.get("window", "test")
    path = Path(ctx.wf["dir"]) / f"results_{window}" / "stats.json"
    record = src.rel(path)
    engine = AgentRef(name="Walk-forward evaluator (block bootstrap)", role="backend", attribution="system")
    sig = stats["significance"]
    factors = []
    for name, row in sig.items():
        if not isinstance(row, dict):
            continue
        factors.append(
            Factor(
                key=name, label=name.replace("_", " "),
                value=f"excess {row['excess_weekly_mean']:+.2%}/week [{row['excess_lo']:+.2%}, {row['excess_hi']:+.2%}], P(≤0) = {row['p_le_zero']:.3f}",
                number=row["p_le_zero"], weight=1.0 if name == "vs_spy_buy_hold" else None,
                detail=f"Sharpe difference {row['sharpe_diff']:+.2f} [{row['sharpe_diff_lo']:+.2f}, {row['sharpe_diff_hi']:+.2f}]",
                agents=[engine], reasoning=ctx.wf.get("summary"), reasoning_label="Walk-forward write-up (summary.md)",
                provenance=Provenance(record=f"{record} → significance.{name}", file=record, time=ctx.wf["manifest"].get("created")),
            )
        )
    if "random_policy_percentile" in sig:
        factors.append(Factor(key="random", label="Percentile among random policies", value=f"{sig['random_policy_percentile']:g} of 100 ({sig.get('random_policy_n')} random long-only policies)", number=sig["random_policy_percentile"], agents=[engine], provenance=Provenance(record=f"{record} → significance.random_policy_percentile", file=record)))
    for name, row in stats.get("research_ic", {}).items():
        series, horizon = name.split("@")
        factors.append(
            Factor(
                key=f"ic_{name}", label=f"{series} signal, {horizon} information coefficient",
                value=f"IC {row['mean_ic']:+.3f}, t = {row['t_stat']:.2f}, hit {pct(row['hit_rate'], 0)}, n = {row['n']}", number=row["mean_ic"],
                detail="Rank correlation of this agent's conviction with the forward return",
                agents=[AgentRef(name=f"{series} {'agent' if series == 'strategy_weight' else 'analyst'} (walk-forward run)", role="strategy" if series == "strategy_weight" else "research", specialty=series, attribution="system")],
                provenance=Provenance(record=f"{record} → research_ic.{name}", file=record),
            )
        )
    spy = sig["vs_spy_buy_hold"]
    p = spy["p_le_zero"]
    reading = plain_reading(spy["excess_lo"], spy["excess_hi"]).replace("mean excess return", "mean weekly excess return")
    if spy["excess_hi"] >= 0 >= spy["excess_lo"] and p > 0.5:
        reading = f"Did not beat SPY with any significance: P(excess ≤ 0) = {p:.3f} and the 95% interval for mean weekly excess, [{spy['excess_lo']:+.2%}, {spy['excess_hi']:+.2%}], includes zero"
    factors.insert(0, Factor(key="reading", label="Plain reading", value=reading, agents=[engine], reasoning=ctx.wf.get("summary"), reasoning_label="Walk-forward write-up (summary.md)", provenance=Provenance(record=f"{record} → significance.vs_spy_buy_hold", file=record, time=ctx.wf["manifest"].get("created"))))
    return scored(
        key, label, question, factors,
        raw=f"P(mean weekly excess vs SPY ≤ 0) = {p:.3f}, {stats.get('decisions')} weekly decisions ({window} window). {reading}",
        formula="100 × (1 − P(mean weekly excess ≤ 0)), block bootstrap, pipeline vs SPY buy-and-hold",
        source=wf_source(ctx, f"Frozen walk-forward stats.json ({window} window)", path),
        owner=OWNERS["wf"], value=100 * (1 - p), contributors=[engine] + [f.agents[0] for f in factors if f.key.startswith("ic_") and f.key.endswith("@1w")], scope="firm",
    )


# ---------------------------------------------------------------- 6. execution


def execution(ctx: Context) -> Score:
    key, label = "execution", "Execution score"
    question = "Did approved orders actually fill at the paper broker?"
    orders = list(ctx.desk.state["orders"].values())
    sent = [o for o in orders if o.get("status") != "submitting"]
    executors = ctx.role_holders("executor")
    blocked = [e for e in ctx.desk.state["events"] if e["check"] == "paper_order_blocked"]
    blocked_factors = [
        Factor(
            key=f"blocked_{i}", label=f"Blocked before the broker ({e['result'].get('strategy_id', '')[:8]})", value="Refused by a desk or watchdog check",
            detail="Context only: blocked attempts never reach the broker and are not counted",
            agents=[src.agent_ref(ctx.agents, e["result"].get("agent"))], reasoning=e["result"].get("reason"), reasoning_label="Recorded block reason",
            provenance=Provenance(record=ctx.desk_record("events[paper_order_blocked]"), time=e["time"]),
        )
        for i, e in enumerate(blocked[-10:])
    ]
    if sent:
        factors = []
        for o in sent:
            fill = f", {o.get('filled_qty')} @ {o.get('filled_avg_price')}" if o.get("filled_qty") else ""
            factors.append(
                Factor(
                    key=o["client_order_id"], label=f"{o['side']} ${o['notional']:,.0f} {o['symbol']}", value=f"{o['status']}{fill}",
                    status="pass" if o["status"] == "filled" else "fail",
                    detail=f"Alpaca paper order {o.get('broker_id', 'with no broker id')}; strategy {o['strategy_id'][:8]}",
                    agents=executors, reasoning=o.get("reason"), reasoning_label="Recorded broker error",
                    provenance=Provenance(record=ctx.desk_record(f"orders[{o['client_order_id']}]"), time=o["time"], citations=[Citation(id=o.get("broker_id", ""), kind="broker", title=f"Alpaca paper order {o.get('broker_id', 'unknown')}", excerpt=f"status {o['status']}")]),
                )
            )
        value, passed, total = checklist(factors)
        return scored(
            key, label, question, factors + blocked_factors,
            raw=f"{passed} of {total} paper orders filled at Alpaca",
            formula="100 × orders with status filled ÷ orders sent to the Alpaca paper broker",
            source=desk_source(ctx, "Desk order records (Alpaca paper responses)"),
            owner=OWNERS["execution"], value=value, contributors=executors,
        )
    return not_produced(
        key, label, question, OWNERS["execution"],
        f"No paper order has been sent from this fund yet ({len(blocked)} blocked before the broker).", blocked_factors,
    )


def team_rows(ctx: Context) -> tuple[dict | None, str]:
    for window in ("test", "all"):
        rows = ctx.wf and ctx.wf["attribution"].get(window)
        if rows and "pipeline" in rows:
            return rows, window
    return None, ""


def team_execution(ctx: Context) -> Score:
    key, label, question = "team_execution", "Execution fills", "How many of the frozen run's orders filled in the execution simulator?"
    rows, window = team_rows(ctx)
    if not rows:
        return team_missing(key, label, question)
    path = Path(ctx.wf["dir"]) / f"results_{window}" / "attribution.csv"
    record = src.rel(path)
    agent = AgentRef(name="Execution agent (walk-forward run)", role="executor", specialty="execution", attribution="system")
    fills, skipped = float(rows["pipeline"]["n_fills"]), float(rows["pipeline"]["n_skipped"])
    decision = ctx.wf.get("decision") or {}
    notes = (decision.get("execution") or {}).get("notes")
    factors = [
        Factor(
            key=name, label=name.replace("_", " "),
            value=f"{float(r['n_fills']):.0f} fills, {float(r['n_skipped']):.0f} skipped; total return {pct(float(r['total_return']))}, costs ${float(r['costs']):,.0f}",
            number=float(r["total_return"]), weight=1.0 if name == "pipeline" else None,
            detail=VARIANTS.get(name, ("", ""))[1],
            agents=[agent], reasoning=notes, reasoning_label=f"Execution agent notes, decision {decision.get('decision_date', '')}",
            provenance=Provenance(record=f"{record} → {name}", file=record, time=ctx.wf["manifest"].get("created")),
        )
        for name, r in rows.items()
        if name.startswith("pipeline")
    ]
    return scored(
        key, label, question, factors,
        raw=f"{fills:.0f} simulated fills, {skipped:.0f} skipped orders ({window} window)",
        formula="100 × fills ÷ (fills + skipped), walk-forward execution simulator",
        source=wf_source(ctx, f"Frozen walk-forward attribution.csv ({window} window)", path),
        owner=OWNERS["wf"], value=100 * fills / (fills + skipped) if fills + skipped else 0, contributors=[agent], scope="firm",
    )


# ---------------------------------------------------------------- 7. watchdog gate


def watchdog(ctx: Context) -> Score:
    key, label = "watchdog", "Watchdog gate"
    question = "How many of this fund's orders cleared the 16 pre-trade rules?"
    log = feedback.entries(ctx.desk)
    verdicts = [e for e in log if e.get("kind") in ("approve", "near_miss", "block")]
    opinions = {e["about"]: e for e in log if e.get("kind") == "opinion"}
    halt, reason = SWITCH.state(), halt_reason(ctx.desk)
    private = store.private_dir(ctx.desk)
    context = [
        Factor(
            key="halt", label="Emergency stop", value=f"ON: {reason}" if reason else "Off (firm-wide and fund desk)",
            status="info", detail="Firm-wide switch plus this fund's desk stop", agents=[WATCHDOG],
            provenance=Provenance(record="watchdog halt switch and desk.json → stop", time=halt.get("time")),
        )
    ] + [
        Factor(
            key=f"event_{i}", label=f"Moderator event: {e.get('kind')}", value=e.get("severity", ""), detail=e.get("subject", ""),
            agents=[WATCHDOG], reasoning=e.get("message"), reasoning_label="Watchdog monitor finding",
            provenance=Provenance(record=f"{src.rel(private / feedback.EVENTS)} line {i + 1}", time=e.get("time")),
        )
        for i, e in enumerate(store.read_jsonl(private / feedback.EVENTS))
    ][-10:]
    if not verdicts:
        return not_produced(key, label, question, OWNERS["watchdog"], "No order from this fund has reached the gate yet.", context)
    factors = []
    for e in verdicts[-25:]:
        opinion = opinions.get(e["id"])
        text = e.get("reason", "")
        if opinion:
            text += f"\n\nSecond opinion ({opinion.get('source', 'model')}): {opinion.get('verdict', '')}. {opinion.get('explanation', '')} {opinion.get('fix', '')}".rstrip()
        factors.append(
            Factor(
                key=e["id"], label=feedback.describe(e), value=e["kind"].replace("_", " ") + (f": {', '.join(e['rules'])}" if e.get("rules") else ""),
                status="fail" if e["kind"] == "block" else "pass",
                detail=f"{e.get('client', '')} ({e.get('risk', '')}), strategy {str(e.get('strategy_id') or '')[:8]}",
                agents=[WATCHDOG] + ([src.agent_ref(ctx.agents, e["agent_id"])] if e.get("agent_id") else []),
                reasoning=text, reasoning_label="Watchdog verdict" + (" and second opinion" if opinion else ""),
                provenance=Provenance(record=f"{src.rel(feedback.log_path(ctx.desk))} → {e['id']}", time=e.get("time")),
            )
        )
    value, passed, total = checklist(factors)
    near = sum(e["kind"] == "near_miss" for e in verdicts[-25:])
    return scored(
        key, label, question, factors + context,
        raw=f"{passed} of {total} reviewed orders cleared ({near} near misses)",
        formula="100 × orders the gate approved ÷ orders the gate reviewed (latest 25)",
        source=SourceRef(id="watchdog", label="Watchdog feedback log", scope="fund", location=src.rel(feedback.log_path(ctx.desk))),
        owner=OWNERS["watchdog"], value=value, contributors=[WATCHDOG],
    )


# ---------------------------------------------------------------- 8. sensitivity


def sensitivity(ctx: Context) -> Score:
    key, label = "sensitivity", "Sensitivity analysis"
    question = "Do results hold when the start date moves or the tickers are masked?"
    result, recorded, missing = strategy_significance(ctx)
    if not result:
        return not_produced(key, label, question, OWNERS["synthesis"], missing)
    prov = significance_provenance(ctx, None)
    inputs = inputs_text(result, result)
    factors = [
        Factor(
            key=f"window_{w['cutoff']}", label=f"Start {w['cutoff']}, end {w['end']}",
            value=f"book {w['portfolio']:+.1%} vs SPY {w['spy']:+.1%}, excess {w['excess_vs_spy']:+.1%}",
            number=w["excess_vs_spy"], status="pass" if w["excess_vs_spy"] > 0 else "fail",
            detail=f"Same frozen weights started on {w['cutoff']}; max drawdown {pct(abs(w['max_drawdown']))}. Inputs: {inputs}",
            agents=[SIG_ENGINE], reasoning=result["limitations"], reasoning_label="Limitations, verbatim from Significance", provenance=prov,
        )
        for w in result["windows"]
    ]
    value, passed, total = checklist(factors)
    note = f" A recorded run reported a {pct(recorded['hit_rate_vs_spy'], 0)} hit rate." if recorded else ""
    return scored(
        key, label, question, factors,
        raw=f"Computed on page load: beat SPY from {passed} of {total} monthly start dates ({result['horizon_days']}-day horizon).{note}",
        formula="100 × start dates where the frozen book beat SPY ÷ start dates tested",
        source=SourceRef(id="synthesis", label=prov.record, scope="fund", location="backend/app/synthesis/significance.py"),
        owner=OWNERS["synthesis"], value=value, contributors=[SIG_ENGINE],
    )


def team_sensitivity(ctx: Context) -> Score:
    key, label, question = "team_sensitivity", "Ticker-masking sensitivity", "Do the frozen run's signals hold when tickers are masked (a memorization check)?"
    audit = ctx.wf and ctx.wf.get("audit")
    if not (audit and audit.get("rows")):
        return team_missing(key, label, question)
    record = src.rel(ctx.wf["audit_path"])
    rule = next((line for line in (ctx.wf.get("audit_note") or "").splitlines() if line.startswith("Verdict rule")), "")
    factors = [
        Factor(
            key=f"{r['series']}@{r['horizon']}", label=f"{r['series']} signal, {r['horizon']}",
            value=f"named IC {r['named_ic']:+.3f}, masked {r['masked_ic']:+.3f}, difference {r['diff']:+.3f} [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}]",
            number=r["diff"], status="pass" if r["verdict"] == "no detectable memory effect" else "fail",
            detail=f"Verdict: {r['verdict']} ({r['n_dates']} dates)",
            agents=[AgentRef(name=f"{r['series']} {'agent' if r['series'] == 'strategy_weight' else 'analyst'} (walk-forward run)", role="strategy" if r["series"] == "strategy_weight" else "research", specialty=r["series"], attribution="system")],
            reasoning=f"{r['verdict']}. {rule}".strip(), reasoning_label="Audit verdict and rule",
            provenance=Provenance(record=f"{record} → rows[{i}]", file=record),
        )
        for i, r in enumerate(audit["rows"])
    ]
    value, passed, total = checklist(factors)
    return scored(
        key, label, question, factors,
        raw=f"{passed} of {total} signal series unchanged when tickers are masked ({audit.get('n_dates')} dates)",
        formula="100 × series with no detectable memory effect ÷ series audited (named vs masked tickers)",
        source=wf_source(ctx, "Frozen walk-forward memorization audit (named vs masked)", ctx.wf["audit_path"]),
        owner=OWNERS["wf"], value=value, contributors=[f.agents[0] for f in factors], scope="firm",
    )


# ---------------------------------------------------------------- team walk-forward panel


TEAM_TITLE = "Team walk-forward evaluation (frozen run)"
ANALYSTS = ("technical", "fundamentals", "macro", "sentiment", "geopolitics")
VARIANTS = {
    "pipeline": ("Full agent pipeline", "Analysts, strategist and execution agent, as run"),
    "pipeline_no_protective": ("Pipeline without stops and targets", "Same orders with the execution agent's stop and target prices removed"),
    "pipeline_naive_execution": ("Pipeline with naive execution", "Same strategist weights, all market-on-open orders: no execution agent"),
    "mechanical_seed": ("Mechanical seed from the same memos", "Weights from the analysts' signed conviction (pm.seed_weights): no strategist"),
    "equal_weight_buy_hold": ("Equal weight, buy and hold", "Baseline, no agents"),
    "equal_weight_weekly": ("Equal weight, weekly rebalance", "Baseline, no agents"),
    "spy_buy_hold": ("SPY, buy and hold", "Benchmark, no agents"),
    "momentum_12_1_top5": ("12-1 momentum, top five", "Rules baseline, no agents"),
}
CONTRIBUTIONS = (
    ("execution", "Execution agent (vs naive market orders)", "pipeline", "pipeline_naive_execution", "executor"),
    ("protective", "Stops and targets (vs none)", "pipeline", "pipeline_no_protective", "executor"),
    ("strategist", "Strategist (vs mechanical seed from the same memos)", "pipeline_naive_execution", "mechanical_seed", "strategy"),
)


def team_missing(key: str, label: str, question: str) -> Score:
    return not_produced(key, label, question, OWNERS["wf"], "reports/wf/final is not in this deployment (copy reports/wf into the image or set SCORES_WF_DIR).")


def team_backtest(ctx: Context) -> Score:
    key, label, question = "team_backtest", "Pipeline vs baselines", "How did the frozen agent pipeline do against baselines, and which agents added or cost return?"
    stats, (rows, window) = team_stats(ctx), team_rows(ctx)
    if not stats or not rows or "random_policy_percentile" not in stats.get("significance", {}):
        return team_missing(key, label, question)
    path = Path(ctx.wf["dir"]) / f"results_{window}" / "attribution.csv"
    record, created = src.rel(path), ctx.wf["manifest"].get("created")
    total = {name: float(r["total_return"]) for name, r in rows.items()}
    agents = {
        "research": [AgentRef(name=f"{a} analyst (walk-forward run)", role="research", specialty=a, attribution="system") for a in ANALYSTS],
        "strategy": [AgentRef(name="Strategist (walk-forward run)", role="strategy", specialty="strategy", attribution="system")],
        "executor": [AgentRef(name="Execution agent (walk-forward run)", role="executor", specialty="execution", attribution="system")],
    }
    factors = [
        Factor(
            key=f"contribution_{k}", label=lbl, value=f"{total[a] - total[b]:+.1%} total return ({pct(total[a])} vs {pct(total[b])})",
            number=total[a] - total[b], status="pass" if total[a] > total[b] else "fail",
            detail=f"{VARIANTS[a][0]} minus {VARIANTS[b][0].lower()}, same LLM decisions, {window} window",
            agents=agents[role], reasoning=ctx.wf.get("summary"), reasoning_label="Walk-forward write-up (summary.md)",
            provenance=Provenance(record=f"{record} → {a}.total_return − {b}.total_return", file=record, time=created),
        )
        for k, lbl, a, b, role in CONTRIBUTIONS
        if a in total and b in total
    ]
    for name, r in rows.items():
        title, what = VARIANTS.get(name, (name.replace("_", " "), ""))
        factors.append(
            Factor(
                key=name, label=title,
                value=f"total {pct(float(r['total_return']))}, CAGR {pct(float(r['cagr']))}, max drawdown {pct(abs(float(r['max_drawdown'])))}, Sharpe {float(r['sharpe']):.2f}",
                number=float(r["total_return"]), detail=f"{what}. Costs ${float(r['costs']):,.0f}, {float(r['n_fills']):.0f} fills",
                agents=agents["research"] + agents["strategy"] + agents["executor"] if name == "pipeline" else [],
                provenance=Provenance(record=f"{record} → {name}", file=record, time=created),
            )
        )
    sig = stats["significance"]
    return scored(
        key, label, question, factors,
        raw=f"pipeline {pct(total['pipeline'])} vs SPY {pct(total.get('spy_buy_hold', 0))} and equal weight {pct(total.get('equal_weight_buy_hold', 0))} ({window} window, {stats.get('decisions')} weekly decisions); {sig['random_policy_percentile']:g}th percentile of {sig.get('random_policy_n')} random long-only policies",
        formula="Percentile rank (0 to 100) of the pipeline's total return among random long-only policies (stats.json random_policy_percentile)",
        source=wf_source(ctx, f"Frozen walk-forward attribution.csv and stats.json ({window} window)", path),
        owner=OWNERS["wf"], value=float(sig["random_policy_percentile"]), contributors=agents["research"] + agents["strategy"] + agents["executor"], scope="firm",
    )


TEAM_RINGS = (team_backtest, team_significance, team_confidence, team_execution, team_sensitivity)


def team_note(wf: dict | None) -> str:
    if not wf:
        return "Not produced yet: reports/wf/final is not in this deployment."
    cfg = wf["manifest"].get("config", {})
    return (
        f"Frozen walk-forward run '{wf['manifest'].get('run_id', wf['dir'].name)}': {cfg.get('model_id', 'model not recorded')} weekly decisions "
        f"from {cfg.get('first_decision', '?')} to {cfg.get('last_decision', '?')}, marked to {cfg.get('mark_end', '?')}, on Mayank's experiment universe "
        f"({', '.join(cfg.get('universe', []))}). It evaluates the team's research pipeline, not this fund's strategy. Source: {src.rel(wf['dir'])}."
    )


# ---------------------------------------------------------------- the card


RINGS = (mandate_fit, confidence, strategy_score, backtest_score, significance, execution, watchdog, sensitivity)


def pick_strategy(desk, strategy_id: str | None) -> dict | None:
    strategies = desk.state["strategies"]
    if strategy_id:
        return strategies.get(strategy_id)
    return max(strategies.values(), key=lambda s: s["created_at"], default=None)


def source_statuses(ctx: Context) -> list[SourceStatus]:
    files = [p for p in ctx.workspace.rglob("*") if p.is_file()] if ctx.workspace.is_dir() else []
    state = ctx.desk.state
    syn_path = Path(ctx.desk.path).with_name("synthesis.json")
    return [
        SourceStatus(id="mandate", label="Fund mandate", owner="Lane 5 platform (fund dashboard)", location="funds.json", status="present", detail=f"{ctx.fund.get('risk')} risk, {len(ctx.fund.get('universe', []))} tickers"),
        SourceStatus(id="desk", label="Desk records", owner=OWNERS["desk"], location=src.rel(ctx.desk.path), status="present" if state["strategies"] or state["policy"] else "empty", detail=f"{len(state['strategies'])} strategies, {len(state['reviews'])} reviews, {len(state['tests'])} tests, {len(state['orders'])} orders"),
        SourceStatus(id="workspace", label="Shared fund files", owner="Fund agents", location=src.rel(ctx.workspace), status="present" if files else "empty", detail=f"{len(files)} files"),
        SourceStatus(id="activity", label="Agent activity logs (tool calls)", owner="Every agent in the fund", location="agents.json and each agent's state", status="present" if ctx.calls else "empty", detail=f"{len(ctx.calls)} tool calls by {len(ctx.agents)} agents"),
        SourceStatus(id="watchdog", label="Watchdog feedback and events", owner=OWNERS["watchdog"], location=src.rel(feedback.log_path(ctx.desk)), status="present" if feedback.entries(ctx.desk) else "empty", detail=f"{len(feedback.entries(ctx.desk))} entries"),
        SourceStatus(
            id="synthesis", label="Synthesis seed and significance", owner=OWNERS["synthesis"], location=src.rel(syn_path),
            status="present" if ctx.synthesis else ("empty" if src.SYNTHESIS_CODE.is_dir() else "not_on_main"),
            detail=f"{len(ctx.synthesis)} run records" if ctx.synthesis else ("No runs for this fund yet" if src.SYNTHESIS_CODE.is_dir() else "backend/app/synthesis is not on main yet"),
        ),
        SourceStatus(
            id="walk_forward", label="Walk-forward evaluation", owner=OWNERS["wf"], location=src.rel(ctx.wf["dir"]) if ctx.wf else "reports/wf/",
            status="present" if ctx.wf else "empty",
            detail=f"{ctx.wf['n_decisions']} weekly decision records; shown in the team panel, not as this fund's results" if ctx.wf else "reports/wf/ is not in this deployment (set SCORES_WF_DIR or copy reports/wf into the image)",
        ),
    ]


def build_scorecard(fund_id: str, fund: dict, manager, strategy_id: str | None = None, wf_root: Path | None = None) -> Scorecard:
    desk = desk_for(manager)
    agents = src.roster(manager)
    calls = src.tool_calls(agents)
    ctx = Context(
        fund_id=fund_id, fund=fund, manager=manager, desk=desk, agents=agents, calls=calls,
        authors=src.file_authors(calls), workspace=src.workspace(manager),
        strategy=pick_strategy(desk, strategy_id), synthesis=src.synthesis_runs(desk),
        wf=src.walk_forward(wf_root or src.WF_ROOT),
    )
    scores = [ring(ctx) for ring in RINGS]
    strategies = sorted(
        ({"id": s["id"], "name": s["name"], "created_at": s["created_at"], "verdict": desk.state["tests"].get(s["id"], {}).get("verdict")} for s in desk.state["strategies"].values()),
        key=lambda s: s["created_at"], reverse=True,
    )
    notes = []
    return Scorecard(
        fund_id=fund_id,
        fund_name=fund.get("name", fund_id),
        generated_at=datetime.now(UTC).isoformat(),
        strategy={k: ctx.strategy[k] for k in ("id", "name", "author", "created_at", "weights", "cutoff", "end")} if ctx.strategy else None,
        strategies=strategies,
        scores=scores,
        team_title=TEAM_TITLE,
        team_note=team_note(ctx.wf),
        team=[ring(ctx) for ring in TEAM_RINGS],
        sources=source_statuses(ctx),
        agents=[src.agent_ref(agents, a) for a in agents],
        inputs=[ToolCall(agent=src.agent_ref(agents, c["agent_id"]), tool=c["tool"], summary=src.summarize_args(c["args"]), time=c["time"]) for c in calls[-300:]],
        notes=notes,
    )
