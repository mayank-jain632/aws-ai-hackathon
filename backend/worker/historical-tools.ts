import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';

async function bridge(action: string, input: unknown, signal?: AbortSignal) {
  const response = await fetch('http://127.0.0.1:8000/api/internal/historical/' + action, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Agent-Token': process.env.AGENT_CONTROL_TOKEN || '', 'X-Agent-ID': process.env.LOCAL_AGENT_ID || '' },
    body: JSON.stringify(input), signal,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(result.detail || 'Historical replay failed'));
  return JSON.stringify(result);
}
const replay = { replay_id: z.string().min(1) };
const clock = { ...replay, clock: z.string().regex(/^\d{4}-\d{2}-\d{2}$/) };
export function createHistoricalTools() {
  return [
    new DynamicStructuredTool({ name: 'start_historical_replay', description: 'Start or inspect the fund historical simulation bound to its exact frozen strategy and current WF evaluation. Does not require or invent a PASS; no Alpaca access. Returns the initial historical clock, actual cached close quotes, virtual cash/equity and assumptions. Reusing this binding returns existing progress; cannot reset history.', schema: z.object({ strategy_id: z.string().min(1), evaluation_id: z.string().min(1) }), func: (input, _m, c) => bridge('start', input, c?.signal) }),
    new DynamicStructuredTool({ name: 'inspect_historical_replay', description: 'Read this fund historical simulation at its persisted clock: cached as-of quotes, simulated account, fills, orders and equity curve. Never exposes future quotes or advances time. Historical simulated fills are not broker receipts.', schema: z.object(replay), func: (input, _m, c) => bridge('inspect', input, c?.signal) }),
    new DynamicStructuredTool({ name: 'place_order', description: 'Place a REAL SIMULATED historical buy/sell using virtual funds, never Alpaca. Requires exact current replay clock and stable client_order_id; idempotent retries do not duplicate. Positive dollar notional sizes at decision close; existing WF engine attempts next-session open with slippage/volume/cash constraints. Advances one observed session and returns actual simulated fills/cash/positions/equity. Report gaps/partial/unfilled accurately. Stop and mandate limits apply.', schema: z.object({ ...clock, symbol: z.string().min(1), side: z.enum(['buy', 'sell']), notional: z.number().finite().positive(), client_order_id: z.string().regex(/^[a-zA-Z0-9_-]{8,48}$/) }), func: (input, _m, c) => bridge('order', input, c?.signal) }),
    new DynamicStructuredTool({ name: 'advance_historical_replay', description: 'Advance this historical simulation exactly one observed session without submitting an order. Requires the current saved clock; returns actual virtual account valuation and fills only through the new clock. No live data or Alpaca.', schema: z.object(clock), func: (input, _m, c) => bridge('advance', input, c?.signal) }),
  ];
}
