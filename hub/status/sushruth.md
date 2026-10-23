# Sushruth · Lane 4b: firm-wide exposure roll-up

Updated 14:55 by Claude Code

**Where this lives: branch `sushruth/firm-exposure`, not `main`.**
It was briefly on main at `4599ad5` and `2bb325f` and is reverted there by `main`'s next
commit; the revert removes only my files and the two `include_router` lines. Nothing else
on main changes, and D27 stays in the log because D28 was appended after it. Pull the
branch to review or run it.

**Shipped (branch only, locally checked, broker not reachable from this machine)**
- `GET /api/firm/exposure`: exposure across every fund at once, per symbol, per sector and
  per risk band, with cross-fund overlap and a capacity check against the single shared
  paper account. Human sessions only; a worker token gets 403. D27.
- Honours Kushagra's new fund membership: the roll-up covers the funds the caller belongs
  to, the same filter `GET /api/funds` uses, and the payload names its `scope`. Without
  that it would have put another member's fund names, capital and holdings in a
  "firm-wide" total. Covered by a two-account hosted test.
- New files: `backend/app/firm.py` (pure aggregation, no I/O), `backend/app/routes/firm.py`,
  `backend/tests/test_firm_exposure.py` (15 tests), `docs/firm-exposure.md`. One
  `app.include_router(firm_router)` line plus its import in `backend/app/main.py`.
- Exposure counts only recorded broker orders net of sells, and the newest strategy holding
  a current human approval and backend PASS. Proposals are never exposure; `unknown` and
  `submitting` orders are excluded and listed, so totals are an explicit lower bound.
  Archived funds leave firm capital, paused funds stay in it.
- No firm-level threshold is invented. Every limit used is either the shared account's
  balance or a limit a person already set in a mandate.
- Checks: 16 new tests pass, 141 passed overall, `npm run check:python` clean. The 4 errors
  in `test_delegation_capacity.py` are pre-existing and Windows-only (`os.killpg`); I
  confirmed them on a clean tree before my change.

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
- `max_sector` is enforced nowhere. `Desk.register` validates `max_position` only, so an
  approved book can hold 60% of one sector under a 40% mandate, and `paper.py:133` refuses
  any mandate that sets a sector limit instead of enforcing it. Since the default mandate
  sets 40, **a fund created with defaults cannot trade at all.** `firm.SECTORS` and
  `firm.sector_of` are the classification that check needs.
- Chaithu / Mayank (order placers and engines): if several funds hold approved books, the
  first one to execute consumes capital the others were already approved to use. The
  capacity findings name this; the fix belongs in the order path.

**Blocked, or need from someone**
- Aaron (lane 4): I reused your risk bands and read desks read-only. I did not touch
  `watchdog/`, `paper.py` or the order gate. Say if you would rather own the firm aggregate.
- Kushagra (lane 1/5): no agent tool yet, because that needs a `roles.py` capability and a
  `run.ts` registry entry in your files. Tell me where you want `firm_exposure` placed and
  which roles get it. No UI either; `frontend/src/funds/` is yours and moving fast.

**Files I am working in right now**
- `backend/app/firm.py`, `backend/app/routes/firm.py`, `backend/tests/test_firm_exposure.py`,
  `docs/firm-exposure.md`, `hub/status/sushruth.md`
