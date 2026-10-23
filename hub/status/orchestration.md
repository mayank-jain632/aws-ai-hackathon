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

**Completion evidence so far**
- Data slice finished at `9342757`: native finance breadth, Jev/FRED/Apify wiring; real Exa/FRED requests, mocked credential-dependent Jev/Apify. Deployment owner has the handoff.
- Frontend slice finished at `994b10b`: requested visual refinement and AWS branding, existing checks passed; final combined deployment pending.
- Role/runtime slice finished at `df2f088`: expanded role delegation/tools, four-slot queueing and cancellation; 36 Python tests, 15 worker tests, builds and real isolated Bedrock recursive role/file handoff passed. Deployment owner has the handoff.
- Provider state changed after the first data report: Jev passed a real local API call; OpenRouter and Apify keys are configured locally. Deployment owner was told to refresh and forward configured secrets privately. No secret values are recorded here.
- Hosted verification owner has exercised Exa and URL fetch through Bedrock, plus frozen strategy/review/historical evaluation/backend gate. Final newer role slice and combined image checks remain pending. Alpaca execution remains unverified without paper credentials.
