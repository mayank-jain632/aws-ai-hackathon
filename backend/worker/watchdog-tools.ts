import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';

async function bridge(action: string, input?: unknown, signal?: AbortSignal) {
  const response = await fetch(`http://127.0.0.1:8000/api/internal/watchdog/${action}`, {
    method: input ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', 'X-Agent-Token': process.env.AGENT_CONTROL_TOKEN || '', 'X-Agent-ID': process.env.LOCAL_AGENT_ID || '' },
    body: input ? JSON.stringify(input) : undefined,
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(90000)]) : AbortSignal.timeout(90000),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(result.detail || 'Watchdog request failed'));
  return JSON.stringify(result);
}

export function createWatchdogTools() {
  return [
    new DynamicStructuredTool({ name: 'watchdog_lessons', description: 'Read the watchdog lessons for this fund: which order limits keep tripping, recent blocked orders with reasons, close calls, and moderator events. Read it before proposing a strategy or submitting orders, and adjust to it. Also reports whether an emergency stop is on.', schema: z.object({}), func: async (_, _m, c) => bridge('lessons', undefined, c?.signal) }),
    new DynamicStructuredTool({ name: 'watchdog_audit', description: 'Run the watchdog audit for this fund now: runaway order bursts, agents retrying blocked orders, orders with unknown broker outcomes, holdings past the mandate, and strategy memos that cite missing files or dates after the cutoff. Returns new moderator events and refreshed lessons. A runaway trips the firm-wide stop; only a person clears it.', schema: z.object({}), func: async (_, _m, c) => bridge('audit', {}, c?.signal) }),
  ];
}
