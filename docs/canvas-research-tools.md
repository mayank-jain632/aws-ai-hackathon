# Canvas research tools

The canvas now exposes three research tools alongside file and delegation tools:

- `list_data_sources` lists datasets, supported tickers, FRED series, warnings, and whether Exa credentials are configured.
- `query_research_data` reads the committed snapshots through `backend/app/data.py`. Choose `prices`, `ohlcv`, `fundamentals`, `macro`, `events`, or `tone`. Historical mode requires an ISO cutoff. OHLCV requires one ticker. Results contain up to 200 rows, the provider, availability field, newest returned availability date, matching row count, and truncation flag. `start` filters availability dates.
- `search_live_context` searches current news, websites, and indexed social discussions through the existing Exa adapter. It requires `EXASEARCH_API_KEY` in the worker environment. It returns a retrieval timestamp and source output. Reddit search is web context, not a Reddit API feed. No X API, live quote API, or brokerage is enabled by these changes.

Try: "List your data sources, then compare AAPL and MSFT prices and SEC fundamentals using only information available by 2023-01-01."

For an independent live research board: "Search current news about semiconductor supply chains. Cite the URLs and distinguish reporting from speculation."

Research mode and historical cutoff are fixed for the conversation tree after the first data query. A child also locks its ancestors so a parent cannot combine live child results with a historical study. This restriction persists across restarts. A different cutoff or live study needs an independent board or fund, not a child of the existing tree. Existing shared files and user-provided text are not classified or scrubbed by this mechanism; do not import live evidence into historical research files or prompts.

Snapshots are not current market feeds. Prices end in June 2025. SEC facts are filtered by filing date but are not guaranteed historical vintages. FRED release dates are approximate and values may include revisions. Curated event headlines and scores are hand-written and unverified. Optional GDELT tone returns no rows when its snapshot is absent. No fixture or invented score replaces missing data.

The backend routes are private worker routes protected by the same token and agent identity checks as delegation. The container includes pandas and the committed snapshots. Rebuild with `npm run dev` for local use. AWS needs a normal image update before these tools are available there.

Verification: `uv run pytest backend/tests`, `npm run check:python`, `npm run lint`, `npm run build`, and `bun test backend/worker/research-tools.test.ts`. The container was also checked by invoking the real TypeScript tools against its authenticated FastAPI routes and all six snapshot query types, without external model calls.
