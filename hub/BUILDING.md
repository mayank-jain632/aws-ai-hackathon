# How to build here

For coding agents and the people driving them. `AGENTS.md` says what the rules are; this file says how to work so six people and their agents can push to one repo at once without building on stale code or burying each other in merge conflicts. Product direction is in `hub/PRD.md`.

## The core problem

Six people and their agents push to `main` all day. An agent that starts a 40-minute task is building against the `main` it saw at minute zero. If a teammate's 20-minute task lands in between, the long task finishes on stale assumptions and lands as a conflict, or worse, as code that merges cleanly but calls something that changed. Everything below exists to keep that window short.

## The loop for every piece of work

1. **Sync.** Run `scripts/hub-sync.sh`. It fetches, lists what landed on `origin/main` since your base, and flags shared files and files you also touched. If anything is flagged, rebase now and re-read the flagged files before writing code.
2. **Claim.** If the work will take more than about 20 minutes, first add it to "In flight" and "Files I am working in" in your `hub/status/<name>.md`, then commit and push just that. Teammates' agents read status files before they start, so a pushed claim prevents duplicate work.
3. **Slice.** Cut the work into pieces of 20 minutes or less, each one ending with something that runs. Long agent tasks stop at each slice boundary to sync again.
4. **Re-sync every slice.** Before each slice, and at least every 15 minutes during a long one, run `scripts/hub-sync.sh` again. If a shared file you depend on changed, stop, rebase, re-read it, and adjust before continuing.
5. **Check.** Run `uv run pytest backend/tests` and `npm run check:python`; add `npm run lint` and `npm run build` if you touched `frontend/`. Run once with `MOCK_AGENTS=1` so the pipeline works without AWS.
6. **Ship.** Rebase on the latest `origin/main`, run the checks again if the rebase pulled anything in, update your status file, and push. If the push is rejected, someone beat you to it: fetch, rebase, check, push again.

Ship small and often, at least every 30 to 45 minutes. A half-finished feature that runs is easier to merge than a finished one that conflicts with everything.

## Branches and worktrees

- Work in your own worktree on a short-lived branch, so your agent's half-done edits never sit in the checkout you test the demo from:
  ```sh
  git fetch origin
  git worktree add ../aws-ai-hackathon-<name> -b <name>/<topic> origin/main
  ```
- Ship from the branch straight to `main` once it is rebased and green: `git rebase origin/main && git push origin HEAD:main`.
- Delete the branch after it lands and start the next topic from a fresh `origin/main`. No long-lived branches, except the parked `agent-canvas`.
- Never force-push `main`. Never commit a merge with conflict markers left in it.

## Shared files and how not to collide on them

| File | Owner | How to change it |
|---|---|---|
| `backend/app/schema.py` | lane 1 (orchestration) | log a **Proposed** decision first; lane 1 merges it; callers update in the same commit |
| `frontend/src/types.ts` | lane 5 (canvas) | the canvas `Agent` types; change them together with the backend code that sends them |
| `backend/worker/run.ts` | lane 1 (the bridge) | new canvas tools go in their own module and are added to the `tools` array with one line each |
| `backend/app/main.py` | lane 1 | do not add routes here; see "New API route" below |
| `backend/app/data.py` | lane 3 (data) | do not add inputs here; see "New data input" below |
| `README.md` | everyone, one section each | edit only your lane's section |
| `package.json`, `pyproject.toml` | anyone | add one dependency per commit and say why in the message |
| `package-lock.json`, `uv.lock` | nobody by hand | on a conflict, take `main`'s copy with `git checkout origin/main -- <file>`, rerun `npm install` or `uv lock`, and commit the regenerated file |
| `hub/DECISIONS.md` | append only | add new entries at the end of the log; on a conflict keep both sides |
| `hub/status/<name>.md` | that person | never edit someone else's |
| `AGENTS.md`, `hub/PRD.md`, `hub/BUILDING.md` | humans | an agent edits them only when its human says so, with a decision logged |

The general rule: **new work goes in new files.** Two agents adding separate files almost never conflict; two agents editing the same function always do.

## Recipes

### New data input

1. `data/fetch_<input>.py` downloads it once and writes a snapshot under `data/<input>/`, with an `available` column saying when each row became public. Live-only inputs write a small cached sample for the demo.
2. `backend/app/sources/<input>.py` exposes `load(cutoff: str) -> pandas.DataFrame` that drops every row whose `available` date is after the cutoff. Live-only inputs say so in the module docstring and refuse a historical cutoff.
3. `backend/tests/test_source_<input>.py` asserts that nothing after the cutoff comes back.
4. Add a row to `data/README.md` and update the input's status in the table in `hub/PRD.md` section 7.
5. Tell lane 1 in your status file so the research team can use it.

### New agent

1. One file in `backend/app/agents/<name>.py`. Call the model through `run_structured` in `backend/app/agents/base.py`, and return a shape from `backend/app/schema.py`.
2. Read data only through the loaders. Before returning, run `assert_no_lookahead` from `base.py` on every source the agent cites.
3. Support `MOCK_AGENTS=1` so the pipeline runs without AWS, the way `backend/app/agents/_analyst.py` does.
4. Add a short test that the mock path returns a valid shape.

### New API route

1. Put it in `backend/app/routes/<lane>.py` as a FastAPI `APIRouter`.
2. Register it with one `app.include_router(...)` line in `backend/app/main.py`. That one line is the only edit to `main.py`, so two lanes adding routes conflict on at most one line.

## When a rebase conflicts

- In a file you own: resolve it, rerun the checks, continue.
- In a file someone else owns: keep their version, then reapply your change on top of it. If you cannot tell what they intended, stop and ask your human; do not guess.
- In a lockfile: regenerate it, as in the table above.
- If the conflict shows two lanes building the same thing, stop both and write it in `hub/DECISIONS.md` as **Proposed**, so the humans pick one.

## Definition of done for any slice

- Checks pass, and the pipeline runs with `MOCK_AGENTS=1`.
- Rebased on the latest `origin/main` and pushed.
- Your `hub/status/<name>.md` says what shipped.
- Any change to a shared shape, the demo, or cloud spend has a decision logged.
- Nothing invented: every ticker, date, route, and model ID in the change exists in the repo or was verified.
