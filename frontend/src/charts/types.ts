export interface Metrics { total_return: number; cagr: number; max_drawdown: number; sharpe: number }
export interface ChartStrategy {
  id: string; name: string; author: string; created_at: string; cutoff: string; end: string
  verdict: 'PASS' | 'FAIL' | null; engine: 'wf' | 'legacy'; label: string | null
}
export interface StrategyOption { id: string; name: string; created_at: string; verdict: string | null }
export interface MonthlyReturn { month: string; portfolio: number; benchmark: number }
export interface GateChecks { drawdown: boolean; sharpe: boolean; excess_return: boolean; mandate: boolean }
export interface Thresholds { max_drawdown: number | null; min_sharpe: number | null; min_excess_return: number | null; max_position: number | null }
export interface BacktestCharts {
  dates: string[]; portfolio: number[]; benchmark: number[]; equal_weight: number[] | null
  drawdown: number[]; benchmark_drawdown: number[]; monthly: MonthlyReturn[]
  metrics: { portfolio: Metrics; baseline: Metrics }
  checks: GateChecks | null; thresholds: Thresholds; consistent: boolean; note: string
}
export interface AllocationCharts { strategy_id: string; weights: Record<string, number>; max_position: number | null }
export interface ChartOrder { client_order_id: string; symbol: string; side: 'buy' | 'sell'; notional: number; status: string; time: string }
export interface TeamCharts {
  title: string; first: string; last: string; dates: string[]; note: string
  series: { pipeline: number[]; equal_weight_buy_hold: number[]; spy_buy_hold: number[] }
}
export interface FundChartsData {
  fund_id: string; fund_name: string; capital: number; generated_at: string
  strategy: ChartStrategy | null; strategies: StrategyOption[]
  backtest: BacktestCharts | null; allocation: AllocationCharts | null
  orders: ChartOrder[]; team: TeamCharts | null; notes: string[]
}
export interface LineSeries { key: string; label: string; values: number[]; color: string; dash?: string; opacity?: number; width?: number }
export interface BarDatum { label: string; value: number; color?: string; tip?: string }
