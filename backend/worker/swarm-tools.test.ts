import {afterEach, expect, test} from 'bun:test';
import {createSwarmTools} from './swarm-tools';
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const tools = createSwarmTools();
function tool(name: string) { return tools.find(t => t.name === name)!; }

test('background delegation preserves defaults and thread reads are authenticated GET requests', async () => {
  const requests: any[] = [];
  globalThis.fetch = (async (url, init) => {requests.push({url: String(url), ...init}); return Response.json({ok: true});}) as typeof fetch;
  await tool('create_agent').invoke({name: 'Research', task: 'Find evidence', role: 'research', wait_for_result: false});
  expect(JSON.parse(requests[0].body).wait_for_result).toBe(false);
  await tool('message_agent').invoke({agent_id: 'child', task: 'Review'});
  expect(JSON.parse(requests[1].body).wait_for_result).toBe(true);
  await tool('read_agent_thread').invoke({agent_id: 'child', cursor: 20, limit: 3});
  expect(requests[2].method).toBe('GET');
  expect(requests[2].url).toContain('/child/thread?');
  expect(requests[2].url).toContain('cursor=20');
  expect(requests[2].headers).toHaveProperty('X-Agent-Token');
});

test('wait forwards cancellation, limits and server failures without retries', async () => {
  let count = 0;
  const controller = new AbortController();
  globalThis.fetch = (async (_url, init) => {count++; expect(init?.signal).toBe(controller.signal); return Response.json({detail: 'fund paused'}, {status: 409});}) as typeof fetch;
  await expect(tool('wait').invoke({seconds: 60, agent_ids: ['child']}, {signal: controller.signal})).rejects.toThrow('fund paused');
  expect(count).toBe(1);
  await expect(tool('wait').invoke({seconds: 3601})).rejects.toThrow();
  expect(count).toBe(1);
});

test('result reads remain explicit and paginated', async () => {
  globalThis.fetch = (async (url, init) => {
    expect(String(url)).toEndWith('/result');
    expect(JSON.parse(String(init?.body))).toEqual({agent_id: 'child', path: '.dexter/tool-results/real.txt', offset: 100, limit: 200});
    return Response.json({content: 'actual result', next_offset: null});
  }) as typeof fetch;
  expect(await tool('read_tool_result').invoke({agent_id: 'child', path: '.dexter/tool-results/real.txt', offset: 100, limit: 200})).toContain('actual result');
});
