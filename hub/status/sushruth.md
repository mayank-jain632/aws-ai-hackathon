# Sushruth · Lane 4b: firm-wide exposure roll-up

Updated 14:30 by Claude Code

**Where this lives: branch `sushruth/firm-exposure`, not `main`.**
It was briefly on main at `4599ad5` and `2bb325f`, reverted at Sushruth's instruction in
`5b42f19`. The branch is rebased onto `main` at `a694705`, so it is current with the
walk-forward harness, synthesis layer, scores view and AgentCore work. Re-landing it means
reverting the revert, not a rebase: the original commits are ancestors of `main`, so
`git rebase main` silently drops the whole feature. Held, not queued to merge, so under
D31 it is not in the demo. `main`'s copy of this file is only a pointer here; the detail
lives in this copy and `docs/firm-exposure.md`.

**Checked at 14:30 on the branch, rebased onto `a694705`**
- 16 firm tests pass on their own. Whole suite on the branch: 399 passed, 1 failed, 1
  skipped, 4 errors. On `main` alone at the same commit: 383 passed, 1 failed, 1 skipped,
  4 errors. So the branch adds 16 passing tests and no new failure.
- The 1 failure is `test_scores.py::test_frozen_walk_forward_gets_its_own_panel_...`, which
  fails the same way on `main` without this branch. It asserts
  `endswith("results_test/attribution.csv")` against a path that comes back with Windows
  separators, so it is a path-separator assumption rather than a logic break and should
  pass on Linux or macOS. Aaron's file, left alone; another agent may be in it.
- The 4 `test_delegation_capacity.py` errors are pre-existing and Windows-only
  (`os.killpg`), confirmed on a clean tree.
- `npm run check:python` clean. `npm run lint` and `npm run build` cannot run on this
  machine: `frontend/node_modules` is not installed. This change touches no frontend file,
  and I did not run `npm install` because regenerating lockfiles is not mine to do (D9).
- Re-checked after rebasing onto `a694705`: 16 firm tests still pass, ruff still clean, and none of the commits since `da3efee` touch `funds.py`, `desk.py`, `paper.py`, `sharing.py` or `main.py`.
- Nothing it reads has changed: `Mandate.capital`/`max_position`/`max_sector`, the
  `desk.json` keys, and the test record's `verdict`/`policy_hash` are all intact.
- No duplication. Nobody else aggregates across funds; I checked `scores/`, `synthesis/`
  and the new routes. Aaron's scores view uses `scope="firm"` for a different idea, a
  walk-forward result shared by every fund rather than aggregated exposure. Worth renaming
  one of them if both ever appear in the same UI.
- Chaithu's `execute_order_plan` submits a whole plan through `paper.submit` in sequence, so
  it inherits every per-fund check and still has no cross-fund one. The capacity findings
  apply more strongly to it than to single orders: the first fund to run a plan can consume
  the shared account's cash that other funds' approved books were already sized against.

**Shipped (branch only, locally checked, broker not reachable from this machine)**
- `GET /api/firm/exposure`: exposure across every fund at once, per symbol, per sector and
  per risk band, with cross-fund overlap and a capacity check against the single shared
  paper account. Human sessions only; a worker token gets 403. D27.
- Honours Kushagra's new fund membership: the roll-up covers the funds the caller belongs
  to, the same filter `GET /api/funds` uses, and the payload names its `scope`. Without
  that it would have put another member's fund names, capital and holdings in a
  "firm-wide" total. Covered by a two-account hosted test.
- New files: `backend/app/firm.py` (pure aggregation, no I/O), `backend/app/routes/firm.py`,
  `backend/tests/test_firm_exposure.py` (16 tests), `docs/firm-exposure.md`. One
  `app.include_router(firm_router)` line plus its import in `backend/app/main.py`.
- Exposure counts only recorded broker orders net of sells, and the newest strategy holding
  a current human approval and backend PASS. Proposals are never exposure; `unknown` and
  `submitting` orders are excluded and listed, so totals are an explicit lower bound.
  Archived funds leave firm capital, paused funds stay in it.
- No firm-level threshold is invented. Every limit used is either the shared account's
  balance or a limit a person already set in a mandate.

**Verified, and the limits of that**
- Ran the roll-up in process against the real local `.local/funds.json`: it read the real
  Team 4 fund, produced no findings because nothing is approved there, and degraded
  honestly when the broker was unreachable (`capacity_checked: false`, not a pass).
- Alpaca credentials are not on this machine, so the live capacity check is unexercised.
  Kushagra connected account `PA33F249I` in their own ignored `.env.local`.
- Exercised the findings over six mandates in a temp root across the three risk bands.
  That fixture is mandate configuration only, no prices, returns, orders or fills. It
  produced the critical capacity finding ($1.8m of approved books against a $100k account)
  and three real sector breaches.

**Two gaps this surfaced, not mine to fix**
- `max_sector` is enforced nowhere, and two lanes now refuse to trade rather than check it:
  `paper.py:135` and Chaithu's `synthesis/orders.py:52` ("sector limit has no enforcement
  engine yet"). `Desk.register` validates `max_position` only, so an approved book can hold
  60% of one sector under a 40% mandate. Since the default mandate sets 40, **a fund created
  with defaults cannot trade at all.** `firm.SECTORS` and `firm.sector_of` are the only
  sector classification in the repo and are what both call sites need.
- Chaithu / Mayank (order placers and engines): if several funds hold approved books, the
  first one to execute consumes capital the others were already approved to use. This is
  sharper for `execute_order_plan`, which submits a whole plan through `paper.submit` in
  sequence and inherits only per-fund checks. The capacity findings name it; the fix
  belongs in the order path.

**Blocked, or need from someone**
- Aaron (lane 4): I reused your risk bands and read desks read-only. I did not touch
  `watchdog/`, `paper.py` or the order gate. Say if you would rather own the firm aggregate.
- Kushagra (lane 1/5): no agent tool yet, because that needs a `roles.py` capability and a
  `run.ts` registry entry in your files. Tell me where you want `firm_exposure` placed and
  which roles get it. No UI either; `frontend/src/funds/` is yours and moving fast.

**Files I am working in right now**
- `backend/app/firm.py`, `backend/app/routes/firm.py`, `backend/tests/test_firm_exposure.py`,
  `docs/firm-exposure.md`, `hub/status/sushruth.md`
