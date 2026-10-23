# Data access and sentiment

Data tools run inside the existing Dexter worker. There is no extra research API, agent loop, or conversation mode lock. `backend/app/roles.py` gives orchestrator, research, adversarial and strategy roles the broader data access. The backtester retains only `run_backtest`; executor and moderator permissions remain unchanged.

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

Checks cover provider schemas, missing keys, rate errors, invalid probabilities, duplicate evidence IDs, cancellation, response limits, Apify budgets/status/results, and actual role-filtered registry contents for all seven roles. FRED VIX observations and native Exa search were exercised live. Jev also passed a real OpenRouter Decisions call on repository README text, returning `typesafe/jev-1.14-20261014`. Apify responses remain mocked; its token is now configured but a live collection check is still pending. Financial Datasets and X still need their account credentials. Exa verification and AWS rollout status are recorded in `hub/status/kushagra.md`.

Alpaca paper account reads are also verified in the deployed app as of 2026-10-23. The AWS-Hack account (`PA33F249I`) returned ACTIVE/USD, $100,000 cash/equity, zero positions and zero open orders through both the deployed backend and the real Dexter account tool. No order or fill was tested. See [agent roles](agent-roles.md#alpaca-deployment-verification).
