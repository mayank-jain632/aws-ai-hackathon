import { expect, test } from 'bun:test';
import { createDeskTools } from './desk-tools';

test('backtest tool cannot accept weights or a search query', async () => {
  const tool = createDeskTools().find(t => t.name === 'run_backtest')!;
  const calls: Array<{ url: string; body: unknown }> = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url, options) => {
    calls.push({ url: String(url), body: JSON.parse(String(options?.body)) });
    return Response.json({ verdict: 'PASS' });
  }) as typeof fetch;
  try {
    await tool.invoke({ strategy_id: 'bound-id', weights: { AAPL: 1 }, query: 'future news' });
    expect(calls).toEqual([{ url: 'http://127.0.0.1:8000/api/internal/desk/backtest', body: { strategy_id: 'bound-id' } }]);
  } finally { globalThis.fetch = original; }
});

test('order tool preserves stable ID and surfaces backend denial', async () => {
  const tool = createDeskTools().find(t => t.name === 'submit_paper_order')!;
  const original = globalThis.fetch;
  globalThis.fetch = (async (_url, options) => {
    expect(JSON.parse(String(options?.body)).client_order_id).toBe('stable-order-001');
    return Response.json({ detail: 'Emergency stop is active' }, { status: 422 });
  }) as typeof fetch;
  try {
    await expect(tool.invoke({ strategy_id: 'id', symbol: 'AAPL', side: 'buy', notional: 10, client_order_id: 'stable-order-001' })).rejects.toThrow('Emergency stop');
  } finally { globalThis.fetch = original; }
});

test('paper status lookup uses GET and only the stable recorded order ID', async () => {
  const tool = createDeskTools().find(t => t.name === 'alpaca_paper_order')!;
  const original = globalThis.fetch;
  globalThis.fetch = (async (url, options) => {
    expect(String(url)).toBe('http://127.0.0.1:8000/api/internal/desk/orders/stable-order-001');
    expect(options?.method).toBe('GET');
    expect(options?.body).toBeUndefined();
    return Response.json({ status: 'filled', client_order_id: 'stable-order-001' });
  }) as typeof fetch;
  try {
    const result = await tool.invoke({ client_order_id: 'stable-order-001' });
    expect(JSON.parse(String(result)).status).toBe('filled');
    await expect(tool.invoke({ client_order_id: '../another-fund/order' })).rejects.toThrow();
  } finally { globalThis.fetch = original; }
});
