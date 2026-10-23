# Chaithu · Lane 2: synthesis layer (strategy from research, significance, order planning)

Updated 14:55 by Claude Code

**Shipped**
- The Desk pipeline end to end (earlier today): `data/` snapshots, `backend/app/data.py`, `backend/app/backtest.py`, `backend/app/agents/`, `POST /api/run`.
- `docs/agent-flow.md`, `.tex`, `.pdf`: high-level agent flow and per-agent variables table for the team.

**Shipped on `main`** (synthesis at `972a751` as a fast-forward; Mayank's walk-forward harness merged at `cc1dc62` with D21/D22 accepted; D30 proposed)
- `backend/app/synthesis/`: research bundle contract, `strategy.synthesize` (conviction seed from memos, mandate and policy clamping, optional one-call Bedrock refinement re-clamped in code), `significance.walk_forward` (monthly cutoffs, hit rate, mean excess, t-stat, bootstrap CI vs SPY and equal weight), `orders.plan_orders` (weights x capital minus holdings, sells first, within cash and limits).
- `backend/app/routes/synthesis.py`: `POST /api/internal/desk/synthesize` (strategy role, registers through `Desk.register`), `POST /api/internal/desk/plan-orders` (executor role, after `execution_checks`), human `GET .../desk/strategies/{id}/significance` and `GET .../desk/runs`; run records in `synthesis.json` beside `desk.json`.
- `POST /api/internal/desk/execute-plan` and executor tool `execute_order_plan`: submits a planned order list through Kushagra's verified `paper.submit` one order at a time with the full backend recheck, halts at the first blocked or uncertain order, and returns the remaining client_order_ids for a resumable batch. Needed because the adapter refuses a new order while one is open, and after the 3:00 PM close every market order stays open.
- Mayank's own registered adapters `synthesis_seed` and `synthesis_planner` wrap the synthesis seed and order planner on `main`; his conformance suite runs against the real modules (365 tests pass on the merged main).
- Cross-lane, named here: two tool names appended in `backend/app/roles.py` (strategy: `synthesize_strategy`; executor: `plan_paper_orders`, `execute_order_plan`), three bridge tools appended in `backend/worker/desk-tools.ts`, one import and one `include_router` line in `backend/app/main.py`. No change to desk gates, paper adapter, schema or policy model.
- Verified locally: `backend/tests/test_synthesis.py` plus the existing suites pass with `MOCK_AGENTS=1`; Bun worker tests pass; ruff clean. One live Bedrock run of the refinement step on the fixture memos returned a valid clamped book (model_used=true); no broker call; `test_delegation_capacity.py` cannot run on Windows (`os.killpg`).

**Blocked, or need from someone**
- Kushagra: the cross-lane edits are on `main` now; review there (the synthesis tools are optional capabilities on existing roles, not new roles or a fixed roster; diagram boxes are context per your audit); the worker registry needs a rebuilt image to expose the two new tools.
- Mayank: `significance.py` reuses `backtest.backtest` unchanged; your walk-forward on `wf/` stays separate and can replace the t-stat here if it lands first.

**Files I am working in right now**
- `backend/app/synthesis/`, `backend/app/routes/synthesis.py`, `backend/tests/test_synthesis.py`, `docs/agent-flow.*`, `hub/status/chaithu.md`
