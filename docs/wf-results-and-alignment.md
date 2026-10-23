# Walk-forward results, diagnosis, and fit with the agent flow on `main`

Reference only; decisions live in `hub/DECISIONS.md` (D21, D22 are Proposed). Branch `mayank/wf-walkforward`,
frozen at tag `wf-frozen-v1`. Raw outputs: `reports/wf/final/`, `reports/wf/audit_clean/`, `reports/wf/audit_control/`.

## 1. What was run

Claude Opus 4.6 (`us.anthropic.claude-opus-4-6-v1`, temperature 0) as research, strategy and execution agents.
55 weekly decisions (Fri 2025-10-03 .. 2026-10-16), equity marked through 2026-10-22. The first 8 are the dev
window, the other 47 the test window; both come from one frozen run. Opus 4.6's documented training cutoff is
2025-08 (AWS lists the reliable knowledge cutoff as May 2025), so every decision is at least a month after it.
Universe: the 10 names on `main`. Daily bars, next-open fills, 5 bps slippage, long-only, price return (no dividends).

## 2. Results (test window, 47 weeks, run once, not tuned)

| Strategy | Total return | Max drawdown | Sharpe |
|---|---|---|---|
| Pipeline (research -> strategy -> execution) | -1.3% | -7.5% | -0.44 |
| Pipeline, no stops/targets | -0.9% | -8.8% | -0.37 |
| Pipeline, naive execution (all market-on-open) | +1.3% | -7.9% | -0.11 |
| Mechanical seed from the same memos (`pm.seed_weights`) | +9.5% | -9.7% | 0.57 |
| Equal-weight buy-and-hold | +18.8% | -7.3% | 1.39 |
| Equal-weight, weekly rebalanced | +21.4% | -7.8% | 1.56 |
| SPY buy-and-hold | +12.5% | -9.1% | 0.86 |
| Momentum 12-1, top 5 | +20.5% | -8.4% | 1.21 |

Excess weekly return vs equal-weight buy-and-hold: mean -0.40%, 95% block-bootstrap interval [-0.70%, -0.14%].
Worse than 91.6% of 500 random weekly policies. 47 weeks, one regime, 10 names: an experiment, not a verdict on LLMs.

## 3. Why it performed poorly

The 20.1-point gap to equal-weight splits into three pieces (all from the frozen decisions, no retuning):

| Piece | Points | How measured |
|---|---|---|
| Stock selection | about -13.8 | pipeline weights scaled to 100% invested, naive execution: +5.0% vs +18.8% |
| Cash drag | about -3.7 | the strategist averaged 72% invested; +5.0% (fully invested) vs +1.3% (as planned, naive execution) |
| Execution agent and stops | about -2.6 | +1.3% (naive execution) vs -1.3%; stops alone cost about 0.5 |

Costs were about 0.7 points of capital at 47% average weekly turnover. The selection problem, in order of evidence:

1. **The signals pointed the wrong way in this window.** For every analyst, names it marked "avoid" had a higher
   next-4-week return than names it marked "long" (4-week mean forward return, avoid vs long: fundamentals 3.8% vs
   1.4%, macro 4.1% vs 0.6%, geopolitics 3.2% vs 0.2%, technical 2.3% vs 1.1%; mean across all calls 2.2%). Rank IC at
   4 weeks: fundamentals -0.10, macro -0.15, technical -0.05, strategist weights -0.18 (t-stat inflated by overlap).
2. **The strategist's book was anti-correlated with outcomes.** Rank correlation of average weight with realized
   test-window return across the 10 names: -0.39. Largest average weights: GOOGL 13% (+1%), JPM 12% (+8%), NVDA 10%
   (+20%). The big winners got little: XOM 7% (+54%), UNH 2% (+29%), CAT 6% (+22%), PG 4% (+12%).
3. **It chased trailing winners and quality in a rotation.** Weights rank-correlate +0.49 with 12-week and +0.32 with
   26-week momentum, but cross-sectional momentum had a negative 4-week IC in these weeks (-0.08 and -0.10). The five
   mega-cap tech/communication names returned +11.9% on average, the other five (JPM, XOM, UNH, PG, CAT) +24.8%; the
   strategist held 41% in the first group and 31% in the second.
4. **It is not a ticker-memory artifact.** The masked-ticker audit on the clean window found no case where named beat
   masked (11 of 12 series no detectable difference, 1 where masked was better); masked ICs are also negative.

What this does not show: that the agents cannot work in general. Plausible reading: trailing-fundamentals and
trend priors lost in an energy/health/industrial rotation. A different regime could reverse it. The literature in
`docs/research/finance-track-brief.md` reports a similar collapse once a test period is after the model's cutoff.

## 4. Memorization audit

| Window | Dates | Rows named better | Rows no difference | Rows masked better |
|---|---|---|---|---|
| Clean (after cutoff) | 55 | 0 | 11 | 1 |
| Control (before cutoff, 2025-03..06) | 17 | 2 (macro and sentiment, 4-week) | 10 | 0 |

The control window was meant to show the test can see leakage. With 17 dates, 10 names and twelve tests, two lean-named
rows is weak evidence, so it is not a validated positive control. The masker also removes ticker-bearing source ids;
price magnitudes remain visible, so masking reduces but does not eliminate recall.

## 5. Fit with the agent flow on `main` (`agent-flow.pdf`, D17 to D20)

| Piece on `main` | What it does | What it means for the backtest |
|---|---|---|
| Executor + order planner | Long-only market/day dollar-notional orders to Alpaca paper; sells before buys; position, notional, daily-order caps; watchdog gate (D19) | The executor is still being built by Lane 4. The harness treats execution as a plug-in (`ExecutionPolicy`); the baseline is deterministic weights -> market orders at the next open with costs and the D19 limits as gates. Our LLM execution policy and stops stay as one ablation (they cost 2.1 and 0.5 points here), to be replaced by their planner or agent through an adapter. |
| Blind backtester + gate | Sees weights and dates only; old monthly-rebalanced, fully invested engine on closes to 2025-06-30; no costs or dividends | Our engine already takes numeric orders only. An `Evaluator` adapter (weights + dates) matches the gate's input; a `rolling` mode adds the weekly re-deciding process. When the backtesting agent advances it plugs in here. Needs refreshed data. |
| Significance (Chaithu, `chaithu/synthesis-layer`) | Same frozen weights from every monthly cutoff; measures allocation robustness | Complementary: it tests the allocation, ours tests the decision process. Overlapping windows make its t-stat optimistic. |
| Model pins (D20) | Main agents Sol 6.1 or Opus 5.5 (denied by the participant role); blind backtester Opus 4.6 | The leak-prone agents are the ones that choose weights, not the backtester. Their model needs a documented cutoff before the first decision; ours do not exist for Sol 6.1 or Opus 5.5. |
| Snapshot ends 2025-06-30 | All gate backtests fall inside every candidate model's cutoff | Only `data/wf/` supports a model-clean result. |

## 6. Limits to state in a demo

Price return only, 5 bps slippage and no commissions, long-only, 10 names, one regime. FRED monthly series are shown as
finally published (small revision risk); 8-K filings stand in for news (titles and item codes, no press-release text);
the daily Fed funds target series is used so the macro view is not a month stale. Frozen decisions used the commit tagged
`wf-frozen-v1` (the dev1 trial run in `reports/wf/dev1` predates the macro fix and is not part of the results).
