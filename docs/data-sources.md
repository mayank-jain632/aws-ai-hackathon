# Data access and sentiment

Data tools run inside the existing Dexter worker. There is no extra research API, agent loop, or conversation mode lock. `backend/app/roles.py` gives orchestrator, research, adversarial and strategy roles the broader data access. The blind backtester has no live-data or sentiment tools; other role restrictions still apply.

| Input family | Tools/provider | Credentials |
|---|---|---|
| Financial statements | Native income, balance-sheet, cash-flow and combined-statement tools | `FINANCIAL_DATASETS_API_KEY` |
| Valuation and company performance | Native current/historical ratios, financial segments and earnings | Same |
| Equity and crypto prices | Native snapshots, OHLCV history and available ticker lists | Same |
| Company and market news | Native company-news tool and market-data router | Same |
| Insider activity | Native insider trades, names and ownership statements | Same |
| Institutional and beneficial ownership | Native holdings/investor lookup and 13D/13G ownership tools | Same |
| Filings and screening | Native filing metadata, 10-K/10-Q/8-K sections, filing reader and stock screener | Same |
| Live web research | Native Dexter Exa `web_search`; `web_fetch` for page content | `EXASEARCH_API_KEY`; URL summarization uses Bedrock |
| X/Twitter | Native Dexter `x_search` | `X_BEARER_TOKEN` with appropriate API access |
| Macro | `get_macro_series` reads FRED observations. Examples: FEDFUNDS, CPIAUCSL, UNRATE, DGS10, T10Y2Y, VIXCLS. Discover other exact IDs with Exa. | No key |
| Other public-web/social data | `apify_actor` inspects/starts an existing Actor; `apify_run` reads status/results or aborts. Coverage depends on the chosen Actor and its input schema. | `APIFY_TOKEN` and provider credits/access |
| Sentiment | `analyze_sentiment` classifies retrieved excerpts with TypeSafe Jev through OpenRouter Decisions | `OPENROUTER_API_KEY` |

The native natural-language finance routers remain available. Their direct tools are also exposed so an agent can fetch precise inputs without another routing model call. Missing provider keys fail explicitly or omit the native search tool; registration does not prove an account has access to every dataset.

## Sentiment flow

1. Retrieve actual news, posts, filings or transcript excerpts with the appropriate source tool.
2. Pass a subject and up to ten excerpts to `analyze_sentiment`, retaining unique evidence IDs, source URLs and known publication dates. Each excerpt is capped at 2,000 characters.
3. The tool submits Choice questions to the [OpenRouter Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request), using the verified [`~typesafe/jev-latest`](https://openrouter.ai/~typesafe/jev-latest) alias. At implementation time it selects [Jev 1.14](https://openrouter.ai/typesafe/jev-1.14). It never falls back to another model.
4. Return per-item negative/neutral/positive probabilities, provider confidence, source metadata, and `positive probability - negative probability`. The aggregate is the equal-weight mean across the supplied sample. Preserve the resolved model version, request ID and usage.

Only this classification tool uses OpenRouter. Agent reasoning, finance routing, filing analysis and URL summarization remain on Bedrock. Jev does not generate explanations; any narrative synthesis comes from the agent. Sentiment describes a sample's expressed stance, not verified truth, market-wide sentiment, trading approval or a forecast. Publication dates supplied by the caller are retained, not independently certified.

## Apify collection

Use native finance/Exa/X/fetch first. For a missing source, find a real public-data Actor and inspect its current schema before supplying Actor-specific JSON input. This can extend coverage to Reddit discussions, transcripts or other sites where an appropriate scraper exists; those individual feeds are not preconfigured or verified by adding a generic Actor runner.

Runs are asynchronous, capped at 180 seconds and $1 per run, with a default $0.50 maximum. The default billed-item limit is 20, adjustable up to 100. As [Apify documents](https://docs.apify.com/api/v2/actors-runs-post), the item parameter limits billing for applicable Actors, not necessarily the number of output items. Result pages are bounded separately, with offset/limit. A failed/running run does not produce successful evidence. Do not blindly retry an uncertain start, and use the abort action to stop a remote run. Stopping a canvas worker does not automatically cancel the remote job. Use Actors only for public data collection, never messaging or external account changes.

## Dates and verification

These additions are for live research. FRED observation dates are not publication dates, and current-vintage values can include revisions. Scraper retrieval times are not publication times. Live providers, scraped records and sentiment must not become evidence for a historical decision without a cutoff-aware provenance adapter. The existing Desk evaluation method is unchanged.

## Hosted verification, 2026-10-23

All configured provider integrations below were exercised through the actual hosted Sol/Dexter agent, not just by calling their APIs from a laptop. The app used image `1792779772`, digest `sha256:d5abadad95b3d9613c26112e3f997a590de42cf5f629e22d728b06270d8038e2`, with credentials from the existing AWS Secrets Manager environment. Checks ran in verification fund `2fc7e21bf457417e` between 13:28 and 13:31 CDT and finished idle. No orders, strategies, policy changes or new AWS resources were created.

| Integration | Actual hosted path and observed result |
|---|---|
| Financial Datasets | `get_income_statements`, AAPL annual limit 1: FY2025 report period 2025-09-27, revenue 416161000000 and net income 112010000000, with provider source URL. |
| X | `x_search`: real AAPL posts with text, timestamps and source URLs; subsequent agent passed two exact returned excerpts into Jev. |
| Exa | `web_search`: found the official Federal Reserve FOMC page with source URLs. |
| Page content / Bedrock | `web_fetch`: fetched and summarized the actual FOMC page, HTTP 200. |
| FRED | `get_macro_series`, UNRATE limit 1: observation 2026-09-01, value 4.2, with FRED source URL. Current vintage, potentially revised. |
| Alpaca paper | `alpaca_paper_account`: ACTIVE/USD, $100,000 cash, zero positions and open orders. Read-only; no order/fill verified. |
| Apify | `apify_actor` inspected the official crawler schema and started a bounded one-page run; `apify_run` checked SUCCEEDED and retrieved one actual Federal Reserve page item with HTTP 200. |
| Jev / OpenRouter | `analyze_sentiment`: classified exact retrieved X excerpts and, separately, a real Apify page excerpt; returned labels, normalized probabilities, confidence, source metadata, usage and request IDs. Resolved model `typesafe/jev-1.14-20261014`; reasoning stayed on Bedrock. |

The completed Apify run is `49xh2c1N0o7aBAOqn`, dataset `RK8Q1ADMRu4WgC0ZV`, Actor `apify/website-content-crawler` build `0.3.101`. It collected only `https://www.federalreserve.gov/monetarypolicy/fomc.htm`, with `crawlerType: cheerio`, `maxCrawlDepth: 0`, `maxCrawlPages: 1`, `maxConcurrency: 1`, no sitemap/llms crawling, robots respected, and Apify Proxy enabled. Run limits were $0.50 and one billed item; final reported cost was $0.0015505566246559223. The first input with proxy disabled was rejected before a run existed; this Actor requires a proxy. Inspect each Actor's schema and validation requirements rather than copying this configuration to unrelated Actors.

The X sample sentiment request was `gen-dec-1792780276-Bt1f6h0RAKDHzBWS2pGc`. The Apify-page request was `gen-dec-1792780307-mvVbrdPjmgKRvFg3RfC5`, returning neutral with score 0. The page's crawl/update time was not asserted as a publication timestamp. Exact sentiment inputs were compared with source text/URLs, and X timestamps were compared with returned post metadata. Large activity previews truncate dataset JSON, so the complete Apify dataset was also checked independently.

This verifies each configured integration's exercised path. It does not prove access to every native financial endpoint, every ticker/date, Reddit/transcript Actors, historical publication vintages, representative market sentiment, or trading performance. Automated tests separately cover provider schemas, missing keys, rate errors, invalid probabilities, duplicate evidence IDs, cancellation, response limits, Apify budgets/status/results, and role filtering. See [role and paper-account controls](agent-roles.md).
