import { AreaChart } from './AreaChart'
import { GroupedBarChart, HBarChart } from './BarChart'
import { LineChart } from './LineChart'
import { asFraction, fmtDate, fmtMoney, fmtMoneyShort, fmtMonth, fmtNum, fmtPct, fmtSignedPct } from './chartMath'
import { Empty, Panel } from './Panel'
import type { AllocationCharts, BacktestCharts, ChartStrategy, LineSeries, TeamCharts } from './types'

const NO_REPLAY = <Empty>No registered strategy has been replayed for this fund yet, so there is nothing to chart. Nothing here is estimated.</Empty>
const windowText = (s: ChartStrategy) => `${fmtDate(s.cutoff)} to ${fmtDate(s.end)}`
const first = (a: number[]) => a[0]
const last = (a: number[]) => a[a.length - 1]

export function ReplayPanel({ bt, strategy }: { bt: BacktestCharts | null; strategy: ChartStrategy | null }) {
  const subtitle = 'Historical replay of the frozen strategy, not paper-account performance'
  if (!bt || !strategy || !bt.dates.length) return <Panel title="Replay P&L" subtitle={subtitle} wide>{NO_REPLAY}</Panel>
  const m = bt.metrics
  const series: LineSeries[] = [
    { key: 'p', label: 'Strategy', values: bt.portfolio, color: 'var(--fund-accent)', width: 2.2 },
    { key: 'b', label: 'SPY', values: bt.benchmark, color: 'var(--fund-ink)', opacity: 0.7, width: 1.5 },
    ...(bt.equal_weight && !sameCurve(bt.equal_weight, bt.portfolio) ? [{ key: 'e', label: 'Equal weight', values: bt.equal_weight, color: 'var(--fund-muted)', dash: '5 4', width: 1.5 }] : []),
  ]
  const verdict = strategy.verdict
  const aria = `Replay P&L of ${strategy.name}: from ${fmtMoney(first(bt.portfolio))} to ${fmtMoney(last(bt.portfolio))} versus SPY ${fmtMoney(first(bt.benchmark))} to ${fmtMoney(last(bt.benchmark))}, ${windowText(strategy)}.`
  return <Panel title="Replay P&L" wide tag={verdict ? `Gate ${verdict}` : 'Gate not run'}
    subtitle={`${subtitle} · ${strategy.name} by ${strategy.author} · ${windowText(strategy)} · ${strategy.engine === 'wf' ? 'walk-forward engine' : 'legacy engine'}${strategy.label ? ` · ${strategy.label}` : ''}`}
    note={`${bt.note}${bt.consistent ? '' : ' Warning: the recorded gate metrics and this replayed curve do not agree exactly.'}`}>
    <div className="chart-headline">
      <div><span>Total return</span><strong>{fmtSignedPct(m.portfolio.total_return)}</strong></div>
      <div><span>vs SPY (points)</span><strong>{fmtNum((m.portfolio.total_return - m.baseline.total_return) * 100, 1)}</strong></div>
      <div><span>Max drawdown</span><strong>{fmtPct(m.portfolio.max_drawdown)}</strong></div>
      <div><span>Sharpe</span><strong>{fmtNum(m.portfolio.sharpe)}</strong></div>
      {strategy.label && <div><span>Data label</span><strong>{strategy.label}</strong></div>}
    </div>
    <div className="chart-body"><LineChart dates={bt.dates} series={series} yLabel="Portfolio value (USD)" yFormat={fmtMoneyShort} tipFormat={fmtMoney} ariaLabel={aria}/></div>
  </Panel>
}

export function DrawdownPanel({ bt, strategy }: { bt: BacktestCharts | null; strategy: ChartStrategy | null }) {
  const sub = 'Fall from the previous peak during the replay, with the mandate limit'
  if (!bt || !strategy || !bt.dates.length) return <Panel title="Drawdown" subtitle={sub}>{NO_REPLAY}</Panel>
  const limit = bt.thresholds.max_drawdown === null ? null : asFraction(bt.thresholds.max_drawdown)
  const worst = Math.min(...bt.drawdown)
  return <Panel title="Drawdown" subtitle={`${sub} · ${windowText(strategy)}`} note={limit === null ? 'No drawdown limit is recorded for this strategy.' : undefined}>
    <div className="chart-body"><AreaChart dates={bt.dates} fund={bt.drawdown} benchmark={bt.benchmark_drawdown} fundLabel="Strategy" limit={limit}
      ariaLabel={`Drawdown of the strategy: worst ${fmtPct(worst)}${limit === null ? '' : `, limit ${fmtPct(-Math.abs(limit), 0)}`}.`}/></div>
  </Panel>
}

export function MonthlyPanel({ bt }: { bt: BacktestCharts | null }) {
  const sub = 'Strategy and SPY return for each calendar month of the replay'
  if (!bt || !bt.monthly.length) return <Panel title="Monthly returns" subtitle={sub}>{NO_REPLAY}</Panel>
  const groups = bt.monthly.map(r => ({ label: fmtMonth(r.month), tip: fmtMonth(r.month), values: { p: r.portfolio, b: r.benchmark } }))
  const wins = bt.monthly.filter(r => r.portfolio > r.benchmark).length
  return <Panel title="Monthly returns" subtitle={sub}>
    <div className="chart-body"><GroupedBarChart groups={groups} signed yLabel="Monthly return (%)" xLabel="Month" format={v => fmtPct(v, 1)}
      series={[{ key: 'p', label: 'Strategy', color: 'var(--fund-accent)' }, { key: 'b', label: 'SPY', color: 'var(--fund-ink)', pattern: true }]}
      ariaLabel={`Monthly returns for ${bt.monthly.length} months; the strategy beat SPY in ${wins}.`}/></div>
  </Panel>
}

export function AllocationPanel({ allocation }: { allocation: AllocationCharts | null }) {
  const sub = 'Weight per ticker in the registered strategy, with the mandate position cap'
  const entries = allocation ? Object.entries(allocation.weights).filter(([, w]) => w > 0).sort((a, b) => b[1] - a[1]) : []
  if (!allocation || !entries.length) return <Panel title="Target allocation" subtitle={sub}><Empty>No target weights are recorded for the registered strategy.</Empty></Panel>
  const scale = entries.reduce((s, [, w]) => s + w, 0) > 1.5 ? 0.01 : 1
  const data = entries.map(([label, w]) => ({ label, value: w * scale }))
  const cap = allocation.max_position === null ? null : asFraction(allocation.max_position)
  return <Panel title="Target allocation" subtitle={sub}>
    <div className="chart-body"><HBarChart data={data} format={v => fmtPct(v, 0)} xLabel="Portfolio weight (%)" marker={cap === null ? null : { value: cap, label: `Cap ${fmtPct(cap, 0)}` }}
      ariaLabel={`Target allocation across ${data.length} tickers; largest is ${data[0].label} at ${fmtPct(data[0].value)}.`}/></div>
  </Panel>
}

export function TeamPanel({ team }: { team: TeamCharts | null }) {
  const sub = 'Firm-level frozen run of the research-to-strategy pipeline; identical for every fund'
  if (!team || !team.dates.length) return <Panel title="Team walk-forward (frozen run)" subtitle={sub} wide><Empty>No frozen team run is available.</Empty></Panel>
  const { pipeline, equal_weight_buy_hold: ew, spy_buy_hold: spy } = team.series
  const series: LineSeries[] = [
    { key: 'p', label: 'Pipeline', values: pipeline, color: 'var(--fund-accent)', width: 2.2 },
    { key: 'e', label: 'Equal weight', values: ew, color: 'var(--fund-muted)', dash: '5 4' },
    { key: 's', label: 'SPY', values: spy, color: 'var(--fund-ink)', opacity: 0.7, width: 1.5 },
  ]
  const big = first(pipeline) >= 1000
  return <Panel title="Team walk-forward (frozen run)" wide tag="Firm-level" subtitle={`${sub} · ${team.title} · ${fmtDate(team.first)} to ${fmtDate(team.last)}`} note={team.note}>
    <div className="chart-body"><LineChart dates={team.dates} series={series} yLabel={big ? 'Value (USD)' : 'Value (start = first point)'} yFormat={big ? fmtMoneyShort : v => fmtNum(v, 0)} tipFormat={big ? fmtMoney : v => fmtNum(v, 2)}
      ariaLabel={`Team walk-forward: pipeline from ${fmtNum(first(pipeline))} to ${fmtNum(last(pipeline))}, equal weight to ${fmtNum(last(ew))}, SPY to ${fmtNum(last(spy))}.`}/></div>
  </Panel>
}

/** True when two dollar curves are the same strategy, so the second line would only duplicate the first. */
function sameCurve(a: number[], b: number[]): boolean {
  return a.length === b.length && a.every((v, i) => Math.abs(v - b[i]) < 1)
}
