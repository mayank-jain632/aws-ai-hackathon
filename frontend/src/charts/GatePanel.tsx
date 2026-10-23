import { asFraction, fmtNum, fmtPct, fmtSignedPct, linear, niceTicks } from './chartMath'
import { Empty, Panel } from './Panel'
import type { AllocationCharts, BacktestCharts } from './types'

interface Row { name: string; detail: string; value: number | null; target: number | null; format: (v: number) => string; pass: boolean | null; dir: 'min' | 'max' }

function Bullet({ row }: { row: Row }) {
  const W = 300, H = 26
  if (row.value === null) return <span className="chart-note" style={{ border: 0, padding: 0 }}>No value recorded</span>
  const vals = [row.value, row.target ?? 0, 0]
  const { domain } = niceTicks(Math.min(...vals), Math.max(...vals), 3)
  const x = linear(domain, [4, W - 4])
  const zero = x(0)
  return <svg className="gate-bar" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${row.name}: ${row.format(row.value)}${row.target === null ? '' : `, ${row.dir === 'min' ? 'minimum' : 'limit'} ${row.format(row.target)}`}`}>
    <rect x={4} y={9} width={W - 8} height={8} fill="#e5ded5"/>
    <rect x={Math.min(zero, x(row.value))} y={9} width={Math.abs(x(row.value) - zero)} height={8} fill="var(--fund-accent)"/>
    {row.target !== null && <line x1={x(row.target)} x2={x(row.target)} y1={3} y2={23} stroke="var(--fund-ink)" strokeWidth={2}/>}
  </svg>
}

export function GatePanel({ bt, allocation }: { bt: BacktestCharts | null; allocation: AllocationCharts | null }) {
  const sub = 'Recorded backtest metrics against the mandate thresholds (bar = result, black tick = threshold)'
  if (!bt) return <Panel title="Gate checks" subtitle={sub}><Empty>No gate has been evaluated for this fund yet.</Empty></Panel>
  const { metrics: m, thresholds: t, checks: c } = bt
  const dd = t.max_drawdown === null ? null : Math.abs(asFraction(t.max_drawdown))
  const weights = allocation ? Object.values(allocation.weights) : []
  const scale = weights.reduce((s, w) => s + w, 0) > 1.5 ? 0.01 : 1
  const maxW = weights.length ? Math.max(...weights) * scale : null
  const cap = t.max_position === null ? null : asFraction(t.max_position)
  const rows: Row[] = [
    { name: 'Excess return vs SPY', detail: t.min_excess_return === null ? 'No minimum recorded' : `Minimum ${fmtSignedPct(asFraction(t.min_excess_return))}`, value: m.portfolio.total_return - m.baseline.total_return, target: t.min_excess_return === null ? null : asFraction(t.min_excess_return), format: v => fmtSignedPct(v), pass: c?.excess_return ?? null, dir: 'min' },
    { name: 'Max drawdown', detail: dd === null ? 'No limit recorded' : `Limit ${fmtPct(dd, 0)}`, value: Math.abs(m.portfolio.max_drawdown), target: dd, format: v => fmtPct(v), pass: c?.drawdown ?? null, dir: 'max' },
    { name: 'Sharpe ratio', detail: t.min_sharpe === null ? 'No minimum recorded' : `Minimum ${fmtNum(t.min_sharpe)}`, value: m.portfolio.sharpe, target: t.min_sharpe, format: v => fmtNum(v), pass: c?.sharpe ?? null, dir: 'min' },
    { name: 'Mandate fit', detail: cap === null ? 'No position cap recorded' : `Largest position vs ${fmtPct(cap, 0)} cap`, value: maxW, target: cap, format: v => fmtPct(v, 0), pass: c?.mandate ?? null, dir: 'max' },
  ]
  return <Panel title="Gate checks" subtitle={sub} note={c ? undefined : 'The backend has not recorded pass/fail marks for this strategy.'}>
    <ul className="gate-rows">{rows.map(r => <li className="gate-row" key={r.name}>
      <div className="gate-name">{r.name}<small>{r.value === null ? r.detail : `${r.format(r.value)} · ${r.detail}`}</small></div>
      <Bullet row={r}/>
      <span className={`gate-mark ${r.pass === null ? 'na' : r.pass ? 'pass' : 'fail'}`}>{r.pass === null ? 'Not checked' : r.pass ? '✓ Pass' : '✕ Fail'}</span>
    </li>)}</ul>
  </Panel>
}
