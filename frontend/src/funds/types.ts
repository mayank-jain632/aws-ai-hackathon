export type Risk = 'conservative' | 'balanced' | 'aggressive'
export interface Mandate {
  name: string; objective: string; description: string; capital: number; risk: Risk
  horizon_months: number; target_return: number | null; max_position: number; max_drawdown: number
  min_cash: number; max_sector: number; universe: string[]; exclusions: string; benchmark: string
  rebalance: string; liquidity: string; mode: string; cutoff: string; trading_allowed: boolean
  approval_required: boolean; allow_short: boolean; max_leverage: number; notes: string
}
export interface FundScheduleState {
  enabled: boolean; interval_seconds: number; next_run_at: string | null
  last_run_at: string | null; last_result: string | null
}
export interface Fund extends Mandate {
  schedule?: FundScheduleState
  id: string; owner: string; status: 'active' | 'paused' | 'archived'; created_at: string; updated_at: string
  portfolio_status: string; holdings: unknown[]; history: unknown[]
  metrics: { nav: number; cash: number; invested: number; pnl: number; return_pct: number; positions: number; agents: number; working: number; files: number; runs: number }
  activity: { id: string; time: string; label: string; detail: string; agent: string; kind: string }[]
  agents: { id: string; name: string; status: string; parentId: string | null }[]
}
export const defaults: Mandate = { name: '', objective: 'balanced_growth', description: '', capital: 100000, risk: 'balanced', horizon_months: 36, target_return: null, max_position: 20, max_drawdown: 15, min_cash: 5, max_sector: 40, universe: ['AAPL','MSFT','NVDA','AMZN','GOOGL','JPM','XOM','UNH','PG','CAT'], exclusions: '', benchmark: 'SPY', rebalance: 'monthly', liquidity: 'monthly', mode: 'historical', cutoff: '2024-06-01', trading_allowed: false, approval_required: true, allow_short: false, max_leverage: 1, notes: '' }
export const riskNames = { conservative: 'Conservative', balanced: 'Balanced', aggressive: 'Growth' }
export const objectives: Record<string, string> = { capital_preservation: 'Preserve capital', balanced_growth: 'Balanced growth', long_term_growth: 'Long-term growth', income: 'Generate income' }
export const money = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (response.status === 401) { window.location.assign('/login'); throw new Error('Sign in to continue.') }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.[0]?.msg || 'Could not complete this request. Try again.')
  return data
}
export const json = (method: string, body: unknown) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
