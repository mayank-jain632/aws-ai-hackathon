import { afterEach, expect, test } from 'bun:test';
import { createResearchTools } from './research-tools';

const originalFetch = globalThis.fetch;
const originalKey = process.env.EXASEARCH_API_KEY;
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalKey === undefined) delete process.env.EXASEARCH_API_KEY;
  else process.env.EXASEARCH_API_KEY = originalKey;
});

test('missing credentials fail before network access', async () => {
  delete process.env.EXASEARCH_API_KEY;
  globalThis.fetch = (() => { throw new Error('unexpected network access'); }) as typeof fetch;
  const search = createResearchTools(async () => { throw new Error('unexpected search'); })[2];
  await expect(search.invoke({ mode: 'live', query: 'company news' })).rejects.toThrow('not configured');
});

test('historical context prevents live search even with credentials', async () => {
  process.env.EXASEARCH_API_KEY = 'test-only';
  globalThis.fetch = (async () => new Response(JSON.stringify({ detail: 'Research context conflicts' }), { status: 409 })) as typeof fetch;
  const search = createResearchTools(async () => { throw new Error('unexpected search'); })[2];
  await expect(search.invoke({ mode: 'live', query: 'company news' })).rejects.toThrow('conflicts');
});

test('live search returns timestamp and explicit mode with source output', async () => {
  process.env.EXASEARCH_API_KEY = 'test-only';
  globalThis.fetch = (async () => new Response(JSON.stringify({ mode: 'live' }))) as typeof fetch;
  const search = createResearchTools(async query => ({ query, url: 'https://www.sec.gov/' }))[2];
  const result = JSON.parse(await search.invoke({ mode: 'live', query: 'company news' }));
  expect(result.mode).toBe('live');
  expect(result.result.url).toBe('https://www.sec.gov/');
  expect(result.warning).toContain('Never use for historical');
});
