# Aaron · Lane 4 (moderator half): watchdog and moderator

Updated 13:02 by Claude Code

**Shipped**
- Hub v2: `AGENTS.md`, `hub/PRD.md` (D8), `hub/BUILDING.md` and `scripts/hub-sync.sh` (D9), tool pointer files
- `docs/`: event pages, AWS notes, sample-repo READMEs, research brief with a public data map

**In flight**
- Watchdog agent (PRD section 4 items 5 to 7, D17): deterministic pre-trade gate `review_order`, claim checks, firm-wide emergency stop with `is_halted()`, background monitor writing moderator events, Bedrock second opinion on flagged trades, feedback log and a lessons file the strategy and executor agents read
- Builds on the existing desk stop, moderator role and `paper.submit` checks from Lane 5 (D12); it does not replace them

**Blocked, or need from someone**
- Execution owners: the gate will be called from `paper.submit` after the account snapshot, one line. Interface lands here at the 13:30 checkpoint

**Files I am working in right now**
- New: `backend/app/watchdog/`, `backend/app/routes/watchdog.py`, `backend/tests/test_watchdog_*.py`, `backend/worker/watchdog-tools.ts`
- One-line hooks only: `backend/app/main.py` (include_router), `backend/app/paper.py` (gate call), `backend/worker/run.ts` (tool entry)
- `hub/status/aaron.md`, D17 in `hub/DECISIONS.md`
