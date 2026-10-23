# Mayank · Lane 2b: leakage-safe walk-forward evaluation (with Chaithu's lane 2)

Updated 12:55 by Claude Code

**Shipped**
- Nothing on `main` yet. Local design only: `docs/track3-plan.md`, closed-book model-cutoff probe (not committed, see below).

**In flight**
- Weekly walk-forward backtest of research -> strategy -> execution agents on Claude Opus 4.6, window 2025-10-03 .. 2026-10-16, all in NEW files: `backend/app/wf/`, `backend/app/agents/strategy.py`, `backend/app/agents/execution.py`, `data/fetch_wf.py`, `data/wf/`, `backend/tests/wf/`.
- Why Opus 4.6 and that window: see D15 in `hub/DECISIONS.md` (Proposed). The current baseline runs gpt-5.6-luna on 2022-2024 data, which the model has almost certainly seen.
- Leakage audit (masked vs named tickers, with a contaminated-window positive control) and the stage-by-stage attribution; answers Q4 and PRD P1 items.

**Blocked, or need from someone**
- Chaithu (lane 2): ack that `wf/` complements the Phase 3 gate (same metrics module, no edits to `backtest.py`). Any call on exact windows is logged in D15.
- Aaron: accept or reject D15.

**Files I am working in right now**
- New files only (see above). I do not edit `schema.py`, `main.py`, `data.py`, `_analyst.py`, `data_access.py` or `base.py`; strict-mode behaviour lives in `backend/app/wf/`.
