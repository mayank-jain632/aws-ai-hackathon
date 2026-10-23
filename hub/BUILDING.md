# Building on the existing app

Read `AGENTS.md`, `hub/DECISIONS.md`, `hub/PRD.md`, and every status file. The product is a working hosted Dexter canvas being extended into a portfolio workflow, not a blank project.

## Before each slice

1. Run `scripts/hub-sync.sh`, then integrate with `git pull --rebase` or `git rebase origin/main` from a clean checkout. Read the changed shared files before coding. Never force-push main.
2. Check `hub/status/` for active claims. Work in the existing suitable checkout/worktree; isolate edits when another agent is changing the same files. Do not create another implementation of a claimed feature.
3. Inspect the actual implementation and its callers. Separate existing behavior from the target in the PRD. Record substantial work in your status file, including cross-lane files.
4. Re-sync before another slice, before pushing, and at least every 15 minutes during long work. If another agent is using the same checkout, never stage or discard its edits.

## Reuse Dexter first

Before adding research, finance, search, fetching, or delegation code:

1. Inspect the pinned source in `.local/dexter` or `/app/vendor/dexter`, especially `src/tools/registry.ts` and the relevant provider module. `backend/worker/setup.py` owns the pin.
2. Check our overridden `getTools`, `toolAllowlist`, model adapter, and environment forwarding in `backend/worker/run.ts` and `backend/app/agent.py`. An installed dependency or an API key does not prove a tool is enabled or tested.
3. Import and enable the existing upstream implementation when it fits. Exa already has `exaSearch`; finance, market data, filings, screening, URL fetch, and X also have upstream tools. Do not add another provider client just to expose one of them.
4. Add only application-specific checks or adapters the existing tool cannot provide, such as backend authorization, role permissions, order approval, or point-in-time data filtering. Keep those checks outside a duplicate provider implementation.

The upstream Agent remains the loop. Our create/list/message tools retain persistent canvas identity, ownership, and shared files. Preserve them when restricting role capabilities. Historical evaluation uses the Desk loaders/backtest; turning on a live Dexter provider does not make it historical-safe.

## Integration boundaries

| Area | Rule |
|---|---|
| `backend/worker/run.ts` | Coordinate changes to the registry and allowlist. Native tools first; custom modules only for missing app behavior. |
| `backend/app/main.py` | New routes go in a router module with a small registration change. Reuse existing worker authentication and manager lookup. |
| `backend/app/agent.py` | Preserve roster/history/layout persistence, descendant ownership, cancellation and shared board files. Coordinate fund and role changes. |
| `backend/app/data.py`, `backtest.py` | Preserve cutoff filtering and the recorded experiment method. Do not substitute present-day provider responses. |
| `backend/app/schema.py`, `frontend/src/types.ts` | Change a contract and all callers together; state compatibility/migration needs. The two files serve different existing contracts, not automatically identical shapes. |
| `frontend/` | Extend the current canvas and fund work. Do not replace existing login, chat, activity, files, collaboration or tree controls. |
| Deployment | One app image/container; use existing scripts and secrets. Main's code and the deployed image are separate states. |
| Lockfiles | Regenerate with the package manager; never hand-merge dependency entries. |

## Checks and shipping

Run checks relevant to the change:

```sh
uv run pytest backend/tests
npm run check:python
npm run lint
npm run build
```

`MOCK_AGENTS=1` applies to the Desk analyst helpers. It does not make the Dexter canvas or external APIs offline. Mocked providers prove wiring, not a live integration. Documentation-only changes need reference/fact checks, not a new funded model run or deployment.

For runtime/tool changes, verify the actual worker path and account for missing keys, provider errors, stop behavior, and persistence. For hosted changes, check login, API/SSE, shared state, and a real invocation where relevant. Preserve user-created agents, files, and conversation history.

Before pushing: sync and integrate, recheck affected behavior, update your own status, append proposed cross-lane/product decisions, stage only your files, and push without rewriting main. If a rebase conflicts, preserve the other lane's intent and reapply your change; ask when the intent is unclear. If current main is already an ancestor of your merge, do not flatten a completed merge just to satisfy a literal rebase command.

Keep docs short: current facts, target behavior, integration constraints, and remaining gaps. Do not reproduce chat history, invent delivery estimates, or turn proposed requirements into completed features.
