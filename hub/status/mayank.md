# Mayank · Lane 2b: leakage-safe walk-forward evaluation and backtester (with Chaithu's lane 2)

Updated 14:00 by Claude Code

**Shipped (branch `mayank/wf-walkforward`, tag `wf-frozen-v1`; `main` merged INTO the branch, nothing merged to `main`)**
- Harness in new files: `backend/app/wf/` (strict point-in-time data layer, daily-bar engine with closed-loop mode, baselines, stats, runner, masking audit, plug-in interfaces, hashed run spec, registry, standard results + JSON schema, replay, CLI, adapters, conformance suite, leakage proof, gate), `backend/app/agents/strategy.py` + `execution.py`, `data/fetch_wf.py`, `data/wf/` (prices to 2026-10-22, FRED, SEC fundamentals, 8-K filings), `specs/`, 332 tests in `backend/tests`, ruff clean.
- **D21 and D22 are Accepted** (Mayank, explicit instruction in chat, recorded in `hub/DECISIONS.md`).
- **Blind backtester on our engine (opt-in):** `BACKTEST_ENGINE=wf` makes the existing `run_backtest` tool (role `backtester`) evaluate on `data/wf` through our engine. Result shape is unchanged plus `engine`, `label` (model-clean / contaminated / unknown-cutoff from the AUTHORING model), `assumptions`, `leakage`. Default behaviour untouched. Edit outside my files: `backend/app/desk.py` (new `import os`, `_author_model`, `_evaluate_wf`, 3 lines in `evaluate`); new module `backend/app/wf/gate.py`.
- Proofs: frozen run reproduced through the plug-in layer with max equity difference 0.0, replay OK x3; leakage proof PASS on all 55 real decision dates (real, truncated and poisoned data give byte-identical agent inputs).
- Results and diagnosis: `docs/wf-results-and-alignment.md` (frozen test window: pipeline -1.3% vs equal weight +18.8%; selection, cash drag and execution/stops split; clean-window masked audit shows no memory advantage).

**In flight**
- Nothing running.

**Blocked, or need from someone**
- **Chaithu (Lane 2):** (1) please merge `chaithu/synthesis-layer` to `main`; it conflicts with current `main` in `backend/app/main.py` (router import) and `backend/app/roles.py` (executor tools and instructions), both small additive hunks I did not resolve in your files. My `synthesis_planner` and `synthesis_seed` adapters import your `plan_orders` and `seed_from_memos` lazily and already ran against them locally. (2) **Bug in `backend/app/backtest.py::rebalanced_curve`:** the portfolio's return on the first trading day of each month is zero (units sized with yesterday's value, marked at today's prices). 22 of 29 month-start sessions are exactly zero on 2023-01..2025-06 equal weight, about 3.2% of cumulative return; SPY is unaffected, so the gate understates portfolios relative to SPY. Fix: mark the old units at today's prices, then rebalance.
- **Kushagra (Lane 1/5):** to use the new engine in the canvas set `BACKTEST_ENGINE=wf` in the backend environment (deployment secrets or `.env`). Suggested one-line addition to the `backtester` role instructions in `roles.py`: also report `label` and `leakage` verbatim. D20: main agents (Sol 6.1, Opus 5.5) have no documented training cutoff, so strategies they author are labelled `unknown-cutoff`; the Opus 4.6 pin on the evaluator does not remove leakage.
- Team: how to present a negative result honestly (the method is the strength).

**Files I am working in right now**
- New files under `backend/app/wf/`, `specs/`, `reports/wf/`, `data/wf/`, `docs/wf-results-and-alignment.md`. One edit in another lane's file: `backend/app/desk.py` (opt-in, described above). Untracked local copy of `backend/app/synthesis/` is Chaithu's, not committed by me.
