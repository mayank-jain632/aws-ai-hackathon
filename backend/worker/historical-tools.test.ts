import { afterEach, expect, test } from 'bun:test';
import { createHistoricalTools } from './historical-tools';
const original = globalThis.fetch;
afterEach(() => { globalThis.fetch = original; });
test('historical place_order stays on authenticated simulation API with exact clock and stable id', async () => {
  const tools = createHistoricalTools();
  const order = tools.find(tool => tool.name === 'place_order')!;
  let called = '';
  let sent: unknown;
  globalThis.fetch = (async (url, init) => {
    called = String(url); sent = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ mode: 'historical_simulation', fills: [] }), { status: 200 });
  }) as typeof fetch;
  const input = { replay_id: 'replay', clock: '2025-10-06', symbol: 'AAPL', side: 'buy', notional: 100, client_order_id: 'historical-tool-001' };
  const result = await order.invoke(input);
  expect(called).toBe('http://127.0.0.1:8000/api/internal/historical/order');
  expect(sent).toEqual(input);
  expect(JSON.parse(result).mode).toBe('historical_simulation');
  expect(tools.map(t => t.name)).toEqual(['start_historical_replay', 'inspect_historical_replay', 'place_order', 'advance_historical_replay']);
});
