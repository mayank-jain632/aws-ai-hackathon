# Kushagra · Four-chat coordination

Updated 2026-10-23 by the coordinating Codex chat.

**Authorization**
- Kushagra appointed this chat to guide the four existing project chats. Preserve their existing instructions and work; coordinate integration rather than start duplicate implementations.
- Latest direct clarification: do not expand scope. Finish each chat's current human-authorized work, then integrate and verify it end to end. Coordinator suggestions for extra UI panels or features are withdrawn.

**Active assignments**
- `Read AWS hackathon emails (2)`: deployment, provider verification, observed hosted defects, and final end-to-end checks. Owns `scripts/hosting.py`; coordinate worker fixes with data.
- `breath of data`: native finance breadth, Exa/X, Jev-only OpenRouter sentiment, FRED and bounded Apify. Owns new worker data modules; coordinate registry and role permissions.
- `different agents`: recursive role delegation, orchestrator capabilities, backend evaluation/approval/stop checks and paper configuration. Owns role/desk/paper modules; provide UI contracts to core product.
- `core product`: finish its current supplied-reference visual refinement while preserving fund dashboard and canvas behavior. Owns fund UI; no additional panels requested by the coordinator.

**Integration criteria**
- Verify the existing authorized flows against one coherent merged/deployed revision. Record unavailable steps accurately; do not add functionality merely to satisfy a broader demo checklist.
- Keep blind evaluation isolated; broader orchestrator tools do not bypass backend trading checks. Account for waiting parents consuming active-run capacity.
- Preserve existing users, collaboration, per-fund storage, shared files inside a fund and restart persistence.
- Record exact commits/images and distinguish mocked, real-provider and hosted evidence. Current provider/rollout details belong in lane reports because they are changing.
- No fabricated prices, returns, fills or default passing thresholds. Broker credentials and unsupported mandate constraints remain explicit prerequisites.

**Coordinator files**
- This file only. Runtime and frontend edits remain with the four owners. Retrieve their progress through thread tools; keep handoffs concrete and avoid duplicate shared-file work.

**Completed integration**
- Data slice `9342757`, frontend `994b10b`, role/runtime `df2f088`, later credential readiness and the separately owned watchdog are included in the deployment owner's verified runtime revision `4c776fe`.
- Hosted Bedrock chain: orchestrator → research → strategy → adversarial → research. The final researcher used FRED, native Exa search/URL fetch, Jev sentiment and Apify Actor schema access. Parents read the same shared result file. No scraping job was started.
- Hosted strategy/review/historical backtest/backend gate recheck passed with trading disabled and zero orders. Real Alpaca paper-account read reports ACTIVE. Watchdog firm-wide stop and an oversized blocked dry run were checked; prior stop state was restored.
- Login for all three accounts, fund controls, SSE, recursive branch cancellation and access boundaries passed. Six funds, 19 agents, 25 files, layouts and desk/watchdog records survived container restart. Deployment owner reports 73 backend tests and 16 tool tests passing.
- Remaining limits: Financial Datasets and X need credentials; broker order submission/fills remain untested. No successful broker execution is claimed. Existing policy/mandate requirements still apply. This coordination added no product features.
