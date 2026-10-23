import { LineChart, type RefLine } from './LineChart'
import { fmtPct } from './chartMath'
import type { LineSeries } from './types'

interface AreaChartProps { dates: string[]; fund: number[]; benchmark: number[]; fundLabel: string; limit: number | null; ariaLabel: string }

/** Drawdown: filled strategy curve, thin SPY line, optional dashed mandate limit. Values are fractions <= 0. */
export function AreaChart({ dates, fund, benchmark, fundLabel, limit, ariaLabel }: AreaChartProps) {
  const series: LineSeries[] = [
    { key: 'fund', label: fundLabel, values: fund, color: 'var(--fund-accent)' },
    { key: 'spy', label: 'SPY', values: benchmark, color: 'var(--fund-ink)', opacity: 0.7, width: 1 },
  ]
  const refLines: RefLine[] = limit === null ? [] : [{ value: -Math.abs(limit), label: `Limit ${fmtPct(-Math.abs(limit), 0)}`, color: 'var(--fund-ink)' }]
  return <LineChart dates={dates} series={series} refLines={refLines} area yLabel="Drop from peak (%)" yFormat={v => fmtPct(v, 0)} tipFormat={v => fmtPct(v, 1)} ariaLabel={ariaLabel}/>
}
