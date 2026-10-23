import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';

const contextShape = {
  mode: z.enum(['historical', 'live']).describe('Use historical for dated decisions; live only for current research.'),
  cutoff: z.string().optional().describe('Required YYYY-MM-DD for historical; omit for live.'),
};

async function bridge(action: string, input?: unknown, signal?: AbortSignal): Promise<string> {
  const response = await fetch(`http://127.0.0.1:8000/api/internal/research/${action}`, {
    method: input ? 'POST' : 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-Agent-Token': process.env.AGENT_CONTROL_TOKEN || '',
      'X-Agent-ID': process.env.LOCAL_AGENT_ID || 'dexter',
    },
    body: input ? JSON.stringify(input) : undefined,
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(result.detail || 'Research request failed'));
  return JSON.stringify(result);
}

export function createResearchTools(liveSearch: (query: string, signal?: AbortSignal) => Promise<unknown>) {
  return [
    new DynamicStructuredTool({
      name: 'list_data_sources',
      description: 'Discover cached datasets, supported tickers, FRED series, availability fields and source limitations. Also reports whether live web context search is configured.',
      schema: z.object({}),
      func: async (_input, _manager, config) => JSON.stringify({
        ...JSON.parse(await bridge('sources', undefined, config?.signal)),
        live_web_search: { provider: 'Exa', configured: Boolean(process.env.EXASEARCH_API_KEY), historical: false },
      }),
    }),
    new DynamicStructuredTool({
      name: 'query_research_data',
      description: 'Read dated price closes, daily OHLCV, SEC fundamentals, FRED macro, unverified curated events, or optional GDELT tone. Offline snapshots, not current feeds. Historical mode requires cutoff. Results include provider, warnings, dates and bounded rows. Start filters the availability date. OHLCV requires one ticker. A conversation tree keeps one research mode and cutoff.',
      schema: z.object({
        ...contextShape,
        source: z.enum(['prices', 'ohlcv', 'fundamentals', 'macro', 'events', 'tone']),
        tickers: z.array(z.string()).max(11).optional(),
        subjects: z.array(z.string()).max(20).optional(),
        series: z.array(z.string()).max(4).optional(),
        start: z.string().optional().describe('Optional YYYY-MM-DD lower bound on availability date.'),
        limit: z.number().int().min(1).max(200).optional(),
      }),
      func: async (input, _manager, config) => bridge('query', input, config?.signal),
    }),
    new DynamicStructuredTool({
      name: 'search_live_context',
      description: 'Search current web context, company news, or Reddit discussions via Exa. LIVE ONLY, never evidence for a historical decision or backtest. Returns source URLs and excerpts, not verified sentiment scores. Requires EXASEARCH_API_KEY. Locks this conversation tree to live research.',
      schema: z.object({ mode: z.literal('live'), query: z.string().min(1).max(1000) }),
      func: async (input, _manager, config) => {
        if (!process.env.EXASEARCH_API_KEY) throw new Error('Live search unavailable: EXASEARCH_API_KEY is not configured. Cached datasets remain available.');
        await bridge('context', { mode: input.mode }, config?.signal);
        const result = await liveSearch(input.query, config?.signal);
        return JSON.stringify({ mode: 'live', provider: 'Exa', retrieved_at: new Date().toISOString(), warning: 'Current web results; publication dates and claims require verification. Never use for historical decisions.', result });
      },
    }),
  ];
}
