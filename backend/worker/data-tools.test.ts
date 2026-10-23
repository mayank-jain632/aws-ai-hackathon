import { afterEach, expect, test } from 'bun:test';
import { analyzeSentiment, apifyActor, apifyRun, getMacroSeries, JEV_MODEL } from './data-tools';

const originalFetch = globalThis.fetch;
const originalKeys = { OPENROUTER_API_KEY: process.env.OPENROUTER_API_KEY, APIFY_TOKEN: process.env.APIFY_TOKEN };
afterEach(() => {
  globalThis.fetch = originalFetch;
  for (const [name, value] of Object.entries(originalKeys)) {
    if (value === undefined) delete process.env[name]; else process.env[name] = value;
  }
});
function mockFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  globalThis.fetch = ((url, init) => Promise.resolve(handler(String(url), init || {}))) as typeof fetch;
}
const evidence = { subject: 'AAPL', items: [{ id: 'news-1', text: 'Synthetic test excerpt.', source_url: 'https://example.com/test', published_at: '2026-10-23' }] };
const answer = { type: 'choice', choice: 'positive', confidence: 0.8, probabilities: { negative: 0.1, neutral: 0.2, positive: 0.7 } };

test('sentiment uses only Jev on the Decisions endpoint, preserving evidence and probabilities', async () => {
  process.env.OPENROUTER_API_KEY = 'test-only';
  mockFetch((url, init) => {
    expect(url).toBe('https://openrouter.ai/api/alpha/decisions');
    expect((init.headers as Record<string,string>).Authorization).toBe('Bearer test-only');
    const body = JSON.parse(String(init.body));
    expect(body.model).toBe(JEV_MODEL);
    expect(body.messages).toBeUndefined();
    expect(body.state.items[0].id).toBe('news-1');
    expect(body.questions.sentiment_0.type).toBe('choice');
    return Response.json({ model: 'typesafe/jev-1.14-20261014', id: 'test', answers: { sentiment_0: answer }, usage: { input_tokens: 50 } });
  });
  const output = JSON.parse(await analyzeSentiment.invoke(evidence));
  expect(output.items[0].score).toBeCloseTo(0.6);
  expect(output.items[0].source_url).toBe(evidence.items[0].source_url);
  expect(output.model).toBe('typesafe/jev-1.14-20261014');
});

test('missing keys fail without network calls or alternate model fallback', async () => {
  delete process.env.OPENROUTER_API_KEY;
  delete process.env.APIFY_TOKEN;
  mockFetch(() => { throw new Error('Unexpected network'); });
  await expect(analyzeSentiment.invoke(evidence)).rejects.toThrow('OPENROUTER_API_KEY');
  await expect(apifyActor.invoke({ action: 'inspect', actor_id: 'test~scraper' })).rejects.toThrow('APIFY_TOKEN');
});

test('malformed or incomplete Jev probabilities are not accepted as sentiment', async () => {
  process.env.OPENROUTER_API_KEY = 'test-only';
  mockFetch(() => Response.json({ model: 'typesafe/jev-1.14', answers: { sentiment_0: { ...answer, probabilities: { negative: 0.9, neutral: 0.9, positive: 0.9 } } } }));
  await expect(analyzeSentiment.invoke(evidence)).rejects.toThrow('Probabilities');
  mockFetch(() => Response.json({ model: 'typesafe/jev-1.14', answers: {} }));
  await expect(analyzeSentiment.invoke(evidence)).rejects.toThrow();
});

test('sentiment rejects repeated IDs and unexpected model identities', async () => {
  await expect(analyzeSentiment.invoke({ ...evidence, items: [evidence.items[0], evidence.items[0]] })).rejects.toThrow();
  process.env.OPENROUTER_API_KEY = 'test-only';
  mockFetch(() => Response.json({ model: 'another/model', answers: { sentiment_0: answer } }));
  await expect(analyzeSentiment.invoke(evidence)).rejects.toThrow('Jev model identity');
});

test('provider authentication and rate errors stay explicit and omit credentials', async () => {
  process.env.OPENROUTER_API_KEY = 'private-test-key';
  mockFetch(() => new Response('private-test-key', { status: 429 }));
  await expect(analyzeSentiment.invoke(evidence)).rejects.toThrow('HTTP 429');
});

test('FRED returns real-shaped values and null gaps, marked current vintage', async () => {
  mockFetch((url) => {
    expect(url).toContain('id=VIXCLS');
    expect(url).not.toContain('api_key');
    return new Response('observation_date,VIXCLS\n2026-10-20,17.31\n2026-10-21,.\n2026-10-22,19.03\n');
  });
  const result = JSON.parse(await getMacroSeries.invoke({ series_id: 'VIXCLS', start_date: '2026-10-20', end_date: '2026-10-22', limit: 2 }));
  expect(result.vintage).toBe('current');
  expect(result.truncated).toBe(true);
  expect(result.rows).toEqual([{ date: '2026-10-21', value: null }, { date: '2026-10-22', value: 19.03 }]);
});

test('FRED rejects provider HTML, invalid dates, and numeric corruption', async () => {
  mockFetch(() => new Response('<html>blocked</html>'));
  await expect(getMacroSeries.invoke({ series_id: 'VIXCLS' })).rejects.toThrow('CSV');
  await expect(getMacroSeries.invoke({ series_id: 'VIXCLS', start_date: '2026-02-30' })).rejects.toThrow();
  mockFetch(() => new Response('observation_date,VIXCLS\n2026-10-22,broken\n'));
  await expect(getMacroSeries.invoke({ series_id: 'VIXCLS' })).rejects.toThrow('numeric');
});

test('Apify start uses inspected actor input and bounded costs/runtime', async () => {
  process.env.APIFY_TOKEN = 'test-only';
  mockFetch((url, init) => {
    const target = new URL(url);
    expect(target.pathname).toBe('/v2/acts/test~scraper/runs');
    expect(target.searchParams.get('timeout')).toBe('180');
    expect(target.searchParams.get('maxTotalChargeUsd')).toBe('0.5');
    expect(target.searchParams.get('restartOnError')).toBe('false');
    expect(JSON.parse(String(init.body))).toEqual({ query: 'test' });
    return Response.json({ data: { id: 'run1', actId: 'actor1', status: 'RUNNING', defaultDatasetId: 'dataset1' } });
  });
  const result = JSON.parse(await apifyActor.invoke({ action: 'run', actor_id: 'test/scraper', input_json: '{"query":"test"}' }));
  expect(result.status).toBe('RUNNING');
  await expect(apifyActor.invoke({ action: 'run', actor_id: 'test~scraper', input_json: '{}', max_cost_usd: 100 })).rejects.toThrow();
});

test('Apify failed/running runs do not return fabricated results', async () => {
  process.env.APIFY_TOKEN = 'test-only';
  let calls = 0;
  mockFetch(() => { calls++; return Response.json({ data: { id: 'run1', status: 'FAILED' } }); });
  const result = JSON.parse(await apifyRun.invoke({ action: 'results', run_id: 'run1' }));
  expect(result.complete).toBe(false);
  expect(result.items).toBeUndefined();
  expect(calls).toBe(1);
});

test('Apify reads bounded completed results with original source records', async () => {
  process.env.APIFY_TOKEN = 'test-only';
  mockFetch(url => url.includes('/datasets/') ? Response.json([{ url: 'https://example.com/post', text: 'test', published_at: '2026-10-22' }]) : Response.json({ data: { id: 'run1', status: 'SUCCEEDED', defaultDatasetId: 'dataset1' } }));
  const result = JSON.parse(await apifyRun.invoke({ action: 'results', run_id: 'run1', limit: 1 }));
  expect(result.returned_items).toBe(1);
  expect(result.items[0].published_at).toBe('2026-10-22');
  expect(result.dataset_id).toBe('dataset1');
});

test('Apify can abort a remote run; inspection excludes private build configuration', async () => {
  process.env.APIFY_TOKEN = 'test-only';
  mockFetch((url, init) => {
    if (url.endsWith('/abort')) { expect(init.method).toBe('POST'); return Response.json({ data: { id: 'run1', status: 'ABORTING' } }); }
    return Response.json({ data: { buildNumber: '1.0.0', actorDefinition: { input: { type: 'object' }, environmentVariables: { SECRET: 'hidden' } } } });
  });
  const inspected = await apifyActor.invoke({ action: 'inspect', actor_id: 'test~scraper' });
  expect(inspected).not.toContain('hidden');
  expect(JSON.parse(await apifyRun.invoke({ action: 'abort', run_id: 'run1' })).status).toBe('ABORTING');
});

test('cancellation is forwarded before any request', async () => {
  process.env.OPENROUTER_API_KEY = 'test-only';
  mockFetch(() => { throw new Error('Should not request'); });
  const controller = new AbortController();
  controller.abort();
  await expect(analyzeSentiment.invoke(evidence, { signal: controller.signal })).rejects.toThrow();
});

test('large provider responses fail instead of flooding model context', async () => {
  process.env.OPENROUTER_API_KEY = 'test-only';
  mockFetch(() => new Response('x'.repeat(1_000_001)));
  await expect(analyzeSentiment.invoke(evidence)).rejects.toThrow('too large');
});
