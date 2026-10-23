# Hosted fund walkthrough, 2026-10-23

Fund: [AWS source-to-strategy verification](https://dgvmahl7u2clq.cloudfront.net/#/funds/ac8b623ccc0a4acb/agents), ID `ac8b623ccc0a4acb`. Nine persisted agents performed actual Bedrock/Dexter research, strategy/document review and a separate historical evaluation on AWS. Research/strategy/review used Sol 6.1; the blind backtester used pinned Opus 4.6. This walkthrough ran against the existing hosted deployment; the combined rollout is tracked separately.

Kushagra explicitly chose live research and a forward-looking proposal, with historical data used only for a separately labeled backtest. Live evidence was not represented as available at the historical cutoff. The fund keeps trading disabled, approvals required and its desk stop engaged. No order tool was called and the fund's order/approval records remain empty. The shared Alpaca account already contained a small AAPL holding from outside this run; this walkthrough did not create or liquidate it.

## Completed workflow

| Stage | Actual actions and retained artifacts |
|---|---|
| Fundamentals research | Native AAPL/MSFT annual income statements; then full annual statements for both and valuation/risk snapshots for all ten eligible stocks. `fundamentals-research.md`, `live-financial-depth.md`, `live-growth-valuations.md`, `live-defensive-valuations.md`. |
| Macro and page evidence | FRED UNRATE, native Exa search, Fed FOMC page fetch, and status/results from completed Apify public crawl `49xh2c1N0o7aBAOqn`. No new Apify run. `macro-research.md`. |
| Social sentiment | Actual X excerpts/URLs/timestamps passed into Jev, resolved `typesafe/jev-1.14-20261014`, request `gen-dec-1792780456-g48cWisdwxVQdeW6w0QC`. Three neutral labels, with probabilities/confidence and tiny/promotional-sample caveats. `sentiment-research.md`. |
| Orchestration | Three separate research children, shared files read back by the orchestrator, real read-only Alpaca account check. `research-index.md`. |
| Live proposal | Separate strategy agent read the initial research and wrote `live-proposal.md`, dated 2026-10-23. It chose a provisional no-new-equity research hold, 100% undeployed cash, because the initial evidence did not justify allocations. This is not an optimized allocation or claim the shared account holds only cash. |
| Live review | A separate adversarial child read the actual initial proposal/memos and wrote `live-proposal-review.md`: PASS WITH LIMITATIONS for documentary consistency only, not investment/trading approval. |
| Historical registration/review | A separate author registered immutable baseline `e344522de9a34a84a5fe4e8f87d51ba2`, linked only to `historical-baseline.md`. Another agent recorded APPROVE narrowly for frozen experiment consistency before testing. |
| Blind backtest | One bound Opus 4.6 backtester called `run_backtest` once, with no research/file tools. The backend persisted FAIL, and the orchestrator wrote the actual result to `historical-backtest-result.md`. |

All exercised provider calls completed successfully. Research exposed real evidence limits: differing fiscal periods, undated ratio snapshots, missing statement currency/scale metadata after native normalization, missing values and unrepresentative X samples. Those were retained as limitations rather than filled from model memory.

The ten-stock snapshot/full-statement expansion completed after the first proposal review. A second proposal reassessment was intentionally stopped for the coordinated deployment before it wrote a replacement or obtained a new review. The retained proposal/review therefore cover the initial evidence set; they do **not** claim to synthesize the expanded memos. All artifacts remain available, no agents are running, and that optional reassessment is the explicit next step. No software defect was found that required changing the runtime in this slice.

## Historical baseline and actual result

Fixed weights: AAPL, MSFT, NVDA, AMZN, GOOGL, JPM, XOM, UNH, PG and CAT at 10% each. Cutoff 2024-06-01, end 2025-06-30; monthly rebalancing against SPY. These are uninformed fixed retrospective inputs for verifying handoff/engine behavior, not weights selected using today's research and not the live proposal's performance.

The previously configured verification policy was copied unchanged from fund `219bdc410ca64cd9` with Kushagra's approval: position cap 20%, drawdown gate 20%, minimum Sharpe 0 and minimum excess return 0. Trading remained false, approval required, maximum order notional $1,000 and daily orders 3. No threshold or weight was tuned after seeing results. The live mandate's separate 15% drawdown goal was not silently substituted for the 20% baseline gate.

| Backend metric | Fixed portfolio | SPY |
|---|---:|---:|
| Price return | 16.900584% | 17.061387% |
| CAGR | 15.661517% | 15.809752% |
| Maximum drawdown | -16.880863% | -18.998907% |
| Sharpe | 0.581243 | 0.574292 |

**Backend verdict: FAIL.** Drawdown, Sharpe and backend mandate checks passed; excess return failed by about 0.160803 percentage points. This is a functioning rejection gate, not a runtime error to bypass. The desk contains exactly one immutable strategy, one independent review and one test, with no orders or human execution approvals.

The engine uses cached historical closes, is fully invested and omits dividends and costs. It has no walk-forward/significance claim and does not implement the live cash/sector constraints. No assertion of unbiased historical strategy selection, investability, achieved live returns or trade approval follows from this test. Live research supports today's proposal only.
