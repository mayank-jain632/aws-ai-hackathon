# Track 3 (Financial Portfolio Management): plan and leakage-safe backtest design

Event: Austin Agentic AI Hackathon, 2026-10-23 (today). Hosts: AWS, Arpio, Posit.
Sources: atx.rahman.dev/track-3.html, index.html, and `hackathon-kit/` (README + code).
No scoring rubric, agenda or deliverable list is published. Judges are AWS solutions architects and support
staff, so expect questions on credibility, reproducibility and AWS usage.

## 1. Executive summary

**Task.** Build agents that read price patterns, company financials, macro, sentiment and geopolitics, and turn them
into a portfolio. Then backtest it against what actually happened.

**Required shape (from the page).**
1. Pick 5-15 tickers and state the evaluation cutoff.
2. Specialist analyst agents (price/technical, fundamentals, macro, sentiment, geopolitical).
3. A portfolio-manager agent reconciles them into explicit target weights with a rationale per position.
4. Backtest from the cutoff forward. Report return, max drawdown, and performance vs a simple baseline.

**Demo checklist.** State universe, cutoff and baseline; show the reasoning behind at least one allocation; compare
the equity curve and key metrics with the baseline.

**Credibility guardrails (the page is explicit).** Use only data available on or before the cutoff (no look-ahead);
keep it reproducible; explain the benchmark; document universe, data window, assumptions and rebalancing rules;
present as a historical experiment, not advice.

**Data sources offered.** SEC Financial Statement Data Sets (needs a descriptive User-Agent), Stooq daily prices,
FRED macro series, two Kaggle price datasets, GDELT (events and media tone).

**Infrastructure.** Workshop Studio account (`WSParticipantRole`); CLI credentials expire after 60 minutes.
Starter kit = Bedrock Converse smoke test (`infer.py`), AgentCore role script, and a minimal AgentCore handler
(`agent.py`). **It contains no trading or backtest engine**, so we write that ourselves. Default model in the kit is
OpenAI GPT-5.6 Luna (`us.openai.gpt-5.6-luna`); GPT-5.4/5.5/5.6 Sol/Terra also listed.
AgentCore runtimes cost money; clean up after.

## 2. Data leakage, in simple terms

A backtest pretends it is a past date and asks "what would the system have done?". Leakage means the system
secretly knew something it could not have known on that date. There are **three** ways this happens.

### A. The data is "from the future" (classic look-ahead)
The number exists in your file, but nobody could have seen it yet.

| Source | Trap | Fix |
|---|---|---|
| SEC financials | Quarter *ends* Sep 30 but the filing is public weeks later | Key every fact on the filing's `filed`/`accepted` date (in `sub.txt`), never the period end. Ignore amendments until their own filing date. |
| FRED | CPI/GDP/jobs get **revised** later; the file shows the final number | Use FRED's real-time (vintage) parameters `realtime_start`/`realtime_end` (ALFRED) with a free API key. Fallback: only never-revised series (Fed funds, Treasury yields) plus a release-lag. |
| GDELT | Event date is not publish date | Use the `DATEADDED` timestamp, only items <= decision time. |
| Prices | Signal at today's close, trade at today's close | Decide on close of day t, **trade at the next open (t+1)**, with costs. |
| Stops/targets on daily bars | Both hit the same day: which first? | Assume the stop hits first (pessimistic); gap through a stop fills at the open, not the stop price. |
| Universe | Picking today's winners (survivorship/hindsight) | Choose the universe by a rule applied to data as of the cutoff, written down before looking at returns. |

### B. The LLM already "remembers" the future (specific to agentic AI, the one judges will ask about)
Even with perfectly timed data, the model was *trained* on text up to its training cutoff. If the backtest period is
before that, the model may simply recall that e.g. a stock soared, and "predict" it. It is an exam where the student
has already seen the answer key. **The data cutoff and the model's knowledge cutoff are two separate clocks.**

What we measured (see `model_cutoff_report.md`, `probe/`): models know real market history well past their documented
"reliable" cutoff, and they often abstain rather than say nothing, so the probe only gives a *lower bound*.
Using documented training cutoffs (supplied by you; not verified by me):

| Model (Bedrock, allowed in this account) | Documented training cutoff | Earliest safe backtest start | Clean months to 2026-09 |
|---|---|---|---|
| Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) | 2025-07 | 2025-09 | 13 |
| Claude Opus 4.6 (`us.anthropic.claude-opus-4-6-v1`) | 2025-08 | 2025-10 | 12 |
| Claude Sonnet 4.6 / Opus 4.8 | 2026-01 | 2026-03 | 7 |
| GPT-5.4 / 5.5 / 5.6 (kit default) | **not documented to us** | **unknown** | **unknown** |

**Big consequence:** the kit's default GPT-5.6 models probably have recent cutoffs. If so, most of any backtest
would be contaminated. Pick the model by the backtest window, not by the kit default. Also: the two Kaggle price
datasets are old (I believe they end about 2017/2018, verify), so any modern LLM has seen that period. They are fine
for plain quant baselines, **not** for an LLM-driven backtest.

Mitigations, in order of strength:
1. **Choose a window after the model's cutoff** (plus a month of buffer). Strongest, and the only one that is a proof.
2. **Mask identities** in prompts: "Stock A", relative dates, no company-specific proper nouns. Reduces recall, does not eliminate it.
3. **Instruct** the model to use only the provided evidence (weak, but costs nothing).
4. **Audit**: run the A/B "real names vs masked names" and a closed-book probe; large gaps = contamination signal.

### C. We fool ourselves (process leakage)
Tweaking prompts until the backtest looks good is leakage through the researcher. Fix: **freeze** the prompts, universe,
rules and parameters *before* the final run; develop on an earlier dev window, run the held-out window **once**; log
everything. Report the frozen run even if it loses to the baseline.

## 3. How to build the backtest so leakage is structurally impossible

**Point-in-time (PIT) data layer.** Every record gets `available_at` (price: close time; filing: SEC acceptance time;
FRED: vintage release date; GDELT: DATEADDED). One gateway, `snapshot(as_of)`, returns only rows with
`available_at <= as_of`. The backtest engine injects the clock; **agents and their tools never take a date argument**,
so an agent cannot ask for the future even by accident.

**Walk-forward loop.** For each rebalance date t (weekly, Friday close): build `snapshot(t)` -> code computes features
(returns, vol, ratios, trends; the LLM never does arithmetic) -> analyst agents -> PM agent -> weights/positions ->
execute at the next open with costs -> mark to market -> log.

**Automated leakage tests (write these first, TDD; they are the core of the test suite):**
1. *Future-poison test:* overwrite all data after t with absurd values; the snapshot and decision at t must be identical.
2. *Truncation invariance:* run on data cut at t vs the full dataset; weights at t must match exactly.
3. *Availability assert:* `max(available_at) <= as_of` for every record handed to an agent.
4. *Execution test:* no fill uses a price from the same bar as the signal.
5. *Memory audit:* closed-book probe of the chosen model (done) + masked-vs-named A/B on a sample.

**Reproducibility.** Pin model ID, `maxTokens`, prompt versions, data snapshot hashes and git commit. Cache every LLM
call by hash of (model, prompt, inputs) so a rerun replays identically. Use temperature 0 where supported (Haiku 4.5
and Opus 4.6 accept it; Opus 4.7+/Sonnet 5 reject the parameter).

**Leakage statement for the demo (judges will ask):** universe + rule; per-rebalance data cutoff; model + its
documented cutoff + window start; the five tests above with pass status; what was frozen and when.

## 4. Recommendations on the design decisions

**1. Instrument universe.** 10 liquid US large caps, about two per sector across five sectors, chosen by a scripted rule
(largest market cap per sector as of the cutoff date) and written down **before** looking at returns; plus a cash/T-bill
sleeve so "no position" is a valid answer. Rules of thumb: fundamentals data (SEC) makes single stocks worthwhile;
avoid names that only look good in hindsight.

**2. Baseline.** Your buy-and-hold idea is right as the primary baseline: equal-weight buy-and-hold of the *same* universe,
same start date, same costs. Add (a) SPY as the market reference, and (b) a dumb non-LLM rule (e.g. 12-1 momentum or
trend filter), so we can show the agents add something beyond a trivial rule. Optional: random-weights distribution.

**3. Agent fleet and decisions.** Your fleet idea fits. Use 4 analysts (technical, fundamentals, macro, sentiment +
geopolitics merged) feeding a PM agent. The track asks for **target weights with a rationale per position**, so make that the
primary output. Your stop-loss/target/direction can be an overlay: the PM emits long/flat (shorts optional: borrow cost,
complexity) plus a stop and target per position, and a small deterministic **risk layer in code** enforces sizing,
max weight and the stops. You do not need Nautilus: the kit has no engine at all, a ~150-line daily loop is enough.
Code computes numbers; the LLM interprets and argues. Every claim in a rationale should cite evidence with its
`available_at`, which also powers the demo's "inspectable thesis" requirement.

**4. Logistics.**
- Region us-east-1; refresh Workshop CLI credentials every 60 minutes (long runs need credential refresh/retry).
- Run the backtest locally or in the workshop IDE; use AgentCore only to host the live agent/demo (costs, cleanup).
- Weekly rebalance over about 13 months is roughly 56 decisions x 10 tickers x 4 analysts, about 2,200 cheap calls with
  Haiku; parallelize with a thread pool, set `maxTokens` explicitly, cache to disk, make it resumable.
- Costs: assume 5-10 bps per trade. Metrics: total return, max drawdown, Sharpe, turnover, hit rate, each vs baselines.
- Honest framing: about 13 months in one regime cannot prove skill; present as an experiment and show sensitivity.
- Data reality: Stooq now serves a JavaScript bot challenge to scripts (I hit it), so use its bulk download from a browser,
  or Yahoo's chart API (worked for me, month-end closes verified) as the price source; get a FRED API key for vintages.

**5. Frontend.** One page, built fast (Streamlit, or Posit Shiny since Posit sponsors): header with universe, cutoff,
baseline and model; equity curve vs baselines with a drawdown panel; weights over time; a rebalance-date slider that opens
the agents' reasoning and cited evidence for each ticker; and a "Leakage audit" panel (tests passed, model cutoff vs
window start). Keep the visual direction editorial/terminal rather than a default dashboard.

## 5. Open decisions for the team
1. Model: Haiku 4.5 (longest clean window) vs Opus 4.6 (stronger). Need OpenAI's documented cutoffs if we want GPT.
2. Window: start 2025-09 (Haiku 4.5) to the latest complete data date.
3. Long-only weights vs long/short with stops.
4. Rebalance frequency (weekly recommended).
5. GDELT in or out given the time left today (stretch goal).
