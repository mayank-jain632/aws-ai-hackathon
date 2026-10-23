# Finance track research brief

Written the morning of 2026-10-23 by a research agent working from the track prompt, with three research passes (AWS tooling, public data, prior art on agentic portfolios). Reference only. Anything marked unverified needs checking before the team relies on it, and `hub/DECISIONS.md` wins over this page.

## What the prompt asks for

> Build agents that analyze historical price patterns, company financials, macroeconomic indicators, market sentiment, and geopolitical factors to construct investment portfolios. Use open-source SEC data and past market data; portfolios will be evaluated against actual performance.

- **The output is a portfolio**: holdings and weights. Everything else serves that.
- **Five signal families are named**: price patterns, company financials, macro, sentiment, geopolitical. Covering all five visibly checks the rubric; skipping geopolitics leaves points on the table.
- **"SEC data"** means EDGAR: filings, XBRL financial facts, insider and institutional holdings.
- **"Evaluated against actual performance"** means a backtest over a historical window with a benchmark.

## The model memorization problem

Most published LLM trading systems with spectacular backtests share one flaw: the model has already read the news and prices of the test period.

- LLMs recall exact pre-cutoff stock returns and macro values. Telling the model "pretend it is 2023" does not stop it, and masking ticker names only partly helps because the model reconstructs the company from context. ("The Memorization Problem", Lopez-Lira, Tang and Zhu: https://arxiv.org/html/2504.14765v2)
- Re-tests of FinGPT, FinMem, and similar agents on periods after the model's training cutoff saw headline returns collapse to roughly zero. ("Profit Mirage": https://arxiv.org/abs/2510.07920)
- StockBench, a contamination-free live benchmark, found most frontier LLM agents failed to beat buy-and-hold. (https://arxiv.org/abs/2510.02209)

Ways to design against it:

- Filter SEC facts by their `filed` date, not the period end, so an agent sees only what was public on the decision date.
- Use the universe as it stood on the start date, to avoid survivorship bias.
- Let the LLM reason over data we hand it while a deterministic layer computes factors and weights. The model never produces a return number from memory.
- Run a leakage ablation (tickers masked against unmasked) and report the gap as a test, not a fix.
- Always show the boring baselines next to ours: SPY, equal weight of the same universe, and a quant core with no LLM.

## AWS tooling

AWS doc pages could not be fetched when this was written; confirm specifics with the AWS solutions architects.

- **Strands Agents SDK** (open-source Python): agent loop with plain Python `@tool` functions, plus Swarm, Graph, and agents-as-tools for multi-agent work. https://github.com/strands-agents/sdk-python
- **Bedrock AgentCore**: Runtime (serverless hosting), Gateway (APIs and Lambdas as MCP tools), Memory, Code Interpreter, Observability. Deploy once the local version works. https://github.com/aws/agentcore-cli
- **Bedrock Agents (classic console)**: supervisor plus collaborators. Third-party reports say it is in maintenance mode for new customers (unverified).
- **Chronos-Bolt and Chronos-2**: Amazon's time-series forecasting models (`pip install chronos-forecasting`, runs on CPU). An Amazon-built model in the price-pattern agent is a good AWS story. https://huggingface.co/amazon/chronos-2
- **Amazon FinSpace is discontinued** (support ended 2026-10-07).

Starter code, best first:

1. `strands-agents/samples`, `python/04-industry-use-cases/finance/finance-assistant-swarm-agent`: Strands swarm with orchestrator, price, financial-metrics, and news agents. https://github.com/strands-agents/samples/tree/main/python/04-industry-use-cases/finance/finance-assistant-swarm-agent
2. Same folder, `genai-powered-financial-advisor-tools`: Strands Graph plus MCP, portfolio analysis, PDF reports.
3. `awslabs/amazon-bedrock-agent-samples`, `examples/multi_agent_collaboration/portfolio_assistant_agent`: the classic Bedrock Agents version.
4. `awslabs/amazon-bedrock-agentcore-samples`, finance personal assistant lab 3: deploying a Strands multi-agent to AgentCore.
5. TradingAgents (Tauric Research): reference multi-agent trading design with analysts, a bull and bear debate, trader, risk team, and portfolio manager; supports Bedrock and SEC data dated as filed. https://github.com/TauricResearch/TradingAgents

## Public data map

Setup times assume one engineer. The first column is the core; the second is where a team can stand out on breadth of data inputs.

| Family | Core | Differentiated add | Setup |
|---|---|---|---|
| Company financials (SEC) | EDGAR XBRL `companyfacts` and `frames` (no key, User-Agent header required, 10 requests per second); `edgartools` package | **Form 4 insider-buying clusters** (open-market "P" codes); year-over-year text diff of 10-K Item 1A risk factors; 13F crowding | 15 to 60 min |
| Price patterns | Daily prices, downloaded once and cached | Chronos forecasting; Fama-French factors for attribution | 10 min |
| Macro | FRED: yield curve T10Y2Y, high-yield spread, VIX | ALFRED vintages (unrevised data, avoids look-ahead); CFTC Commitments of Traders positioning | 10 to 30 min |
| Sentiment | FinBERT on news or filing text | **Earnings-call transcripts** (Hugging Face `kurry/sp500_earnings_transcripts`, 2005 to 2025, MIT) scored for tone and hedging; GDELT news tone (recent months only) | 20 min |
| Geopolitical | | **Geopolitical Risk index** (Caldara and Iacoviello, daily, free download, includes an oil sub-index); Economic Policy Uncertainty index (also in FRED); OFAC sanctions list | 15 min |

Dead ends checked that morning: Google Trends through pytrends (archived, returns 429s), Reddit API (paid), Nasdaq Data Link free prices (frozen in 2018), AAII sentiment history (members only), congressional trade trackers (offline), ACLED (approval would not land in time), Stooq (now behind a CAPTCHA; `data/README.md` confirms the team fell back to Yahoo).

Practical rule: download and cache every dataset early. A rate limit during the demo is the most likely way to lose.

## Build ideas

1. **Point-in-time investment committee.** A quant core with no LLM (momentum, value, quality, low volatility from point-in-time SEC facts and cached prices) is both a valid portfolio and the baseline. Analyst agents each emit a bounded view with a confidence; a bull and bear critique runs on the top candidates; a risk manager agent can only shrink positions. Black-Litterman (PyPortfolioOpt) turns views into weights, so the optimizer, not the LLM, sets the numbers.
2. **Geopolitical regime allocator.** A macro and geopolitical agent reads the GPR index, EPU, credit spreads, the yield curve, and CFTC positioning, labels the regime, and tilts across the 11 SPDR sector ETFs plus TLT and GLD. Small universe, fast robust backtest, strong live demo; thin on company-level SEC data, so it works best as the risk manager inside idea 1.
3. **SEC filing-diff scout.** Rank companies where insiders are buying (Form 4) while 10-K risk language and earnings-call tone get more confident. Deepest use of SEC data, but the parsing is real work and sparse signals make the backtest noisy.
4. **Auditor agent.** A final agent red-teams the portfolio before submission: concentration, survivorship, turnover and cost drag, leakage. It prints a "what could be wrong with this portfolio" card next to the results. Cheap, and shows judges the team thinks like an investment committee.
