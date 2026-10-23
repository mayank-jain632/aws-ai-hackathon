import { expect, test } from 'bun:test';
import { createWatchdogTools } from './watchdog-tools';

test('lessons tool reads the watchdog route with the agent identity', async () => {
  const tool = createWatchdogTools().find(t => t.name === 'watchdog_lessons')!;
  const original = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (url, options) => {
    calls.push(String(url));
    expect(options?.method).toBe('GET');
    return Response.json({ lessons: '# Watchdog lessons', halted_reason: null });
  }) as typeof fetch;
  try {
    expect(await tool.invoke({})).toContain('Watchdog lessons');
    expect(calls).toEqual(['http://127.0.0.1:8000/api/internal/watchdog/lessons']);
  } finally { globalThis.fetch = original; }
});
