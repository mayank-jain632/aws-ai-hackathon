# Mayank · Lane 2b: leakage-safe walk-forward evaluation (with Chaithu's lane 2)

Updated 13:50 by Claude Code

**Shipped (branch `mayank/wf-walkforward`, tag `wf-frozen-v1`; nothing merged to `main`, branch not rebased onto `main` yet)**
- Walk-forward harness in new files only: `backend/app/wf/` (strict PIT data layer, daily-bar engine, baselines, stats, runner, masking audit), `backend/app/agents/strategy.py` + `execution.py`, `data/fetch_wf.py`, `data/wf/` snapshot (prices to 2026-10-22, FRED, SEC fundamentals, 8-K filings; raw SEC cache not committed), `backend/tests/wf/` (115 tests, ruff clean).
- Frozen run on Opus 4.6, 55 weekly decisions 2025-10-03..2026-10-16: `reports/wf/final/` (`results_dev/`, `results_test/`, `results_all/`). Hygiene: 0 abstentions, 0 sources dated after their decision, 0 flagged contaminated.
- Memorization audits: `reports/wf/audit_clean/` (55 dates) and `reports/wf/audit_control/` (17 pre-cutoff dates).
- Write-up: `docs/wf-results-and-alignment.md` (results, diagnosis, how this fits the agent flow on `main`).
- Decisions logged as **Proposed**: D21 (experiment definition; drafted as "D15", renumbered because `main` already uses D15 to D20) and D22 (align with `main`'s execution model).

**Results (test window, 47 decisions, run once, not tuned)**
- Pipeline -1.3% vs equal-weight buy-and-hold +18.8%, SPY +12.5%, mechanical seed +9.5%, momentum +20.5%. Excess vs equal weight significantly negative; worse than 91.6% of 500 random policies.
- Gap of 20.1 points = about 13.8 stock selection + 3.7 cash drag (72% average invested) + 2.6 execution agent and stops.
- Why: analysts' "avoid" calls were followed by higher 4-week returns than their "long" calls; the strategist's weights rank-correlate -0.39 with realized returns; it tilted toward trailing winners and quality (GOOGL, JPM, NVDA) while energy, health and industrials rallied (XOM +54%, UNH +29%).
- Audits: clean window shows no named-over-masked advantage (11 of 12 rows no effect, 1 masked better), so this is not a ticker-memory artifact. Control window is inconclusive (low power).

**In flight**
- Nothing running. Waiting on the team's call on D22 before building an order-planner mode and a `frozen` evaluation mode.

**Blocked, or need from someone**
- Aaron/Chaithu: accept or reject D21 and D22. Chaithu: `backend/app/synthesis/significance.py` reruns the old engine on frozen weights; the `wf` rolling mode tests the weekly re-deciding process. Do you want `wf` as the gate's backend (needs the model-cutoff label) or kept as a separate evaluation?
- Kushagra/Lane 1 (D20): main agents default to Sol 6.1 / Opus 5.5, which the participant IAM role denies, and whose training cutoffs are not documented to us; the Opus 4.6 pin on the blind backtester does not address leakage (see D22 item 3).
- Decision needed from the team on how to present a negative result honestly (the leakage-safe method is the strength).

**Files I am working in right now**
- New files only under `backend/app/wf/`, `reports/wf/`, `data/wf/`, `docs/wf-results-and-alignment.md`; no edits to `schema.py`, `main.py`, `data.py`, `backtest.py`, `_analyst.py`, `data_access.py`, `base.py`.
