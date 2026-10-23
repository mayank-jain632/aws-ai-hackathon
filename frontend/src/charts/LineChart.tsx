import { useId, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { areaPath, evenTicks, extent, fmtDate, linear, linePath, nearestIndex, niceTicks } from './chartMath'
import type { LineSeries } from './types'
import { useContainerWidth } from './useContainerWidth'

export interface RefLine { value: number; label: string; color: string; dash?: string }
export interface LineChartProps {
  dates: string[]; series: LineSeries[]; ariaLabel: string; yLabel: string
  yFormat: (v: number) => string; tipFormat?: (v: number) => string
  refLines?: RefLine[]; area?: boolean; yMax?: number
}
const H = 290
const isCompact = (w: number) => w < 520

export function LineChart({ dates, series, ariaLabel, yLabel, yFormat, tipFormat, refLines = [], area = false, yMax }: LineChartProps) {
  const id = useId()
  const { ref: wrap, width: W } = useContainerWidth(720)
  const M = { t: 14, r: isCompact(W) ? 72 : 96, b: 44, l: isCompact(W) ? 52 : 64 }
  const ref = useRef<SVGSVGElement>(null)
  const [hover, setHover] = useState<number | null>(null)
  const n = dates.length
  const times = dates.map(d => Date.parse(d))
  const [t0, t1] = extent([times])
  const [lo, hi] = extent([...series.map(s => s.values), refLines.map(r => r.value)])
  const { ticks, domain } = niceTicks(lo, yMax !== undefined ? Math.max(hi, yMax) : hi, 5)
  const x = linear([t0, t1], [M.l, W - M.r])
  const y = linear(domain, [H - M.b, M.t])
  const xs = times.map(x)
  const fmt = tipFormat ?? yFormat
  const move = (e: PointerEvent<SVGSVGElement>) => {
    const box = ref.current?.getBoundingClientRect()
    if (box && box.width) setHover(nearestIndex(((e.clientX - box.left) / box.width) * W, xs))
  }
  const key = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); setHover(h => Math.min(n - 1, (h ?? -1) + 1)) }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); setHover(h => Math.max(0, (h ?? n) - 1)) }
    else if (e.key === 'Escape') setHover(null)
  }
  const xTicks = evenTicks(n, W < 640 ? 3 : 5)
  const lastY = series.map(s => ({ s, y: y(s.values[n - 1] ?? NaN) }))
  return <div className="chart-wrap" ref={wrap}>
    <svg ref={ref} className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel} tabIndex={0}
      onPointerMove={move} onPointerLeave={() => setHover(null)} onKeyDown={key} onFocus={() => setHover(h => h ?? n - 1)} onBlur={() => setHover(null)}>
      {ticks.map(t => <g key={t}><line className="grid" x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)}/><text x={M.l - 8} y={y(t) + 3} textAnchor="end">{yFormat(t)}</text></g>)}
      <line className="axis" x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b}/>
      {xTicks.map(i => <text key={i} x={xs[i]} y={H - M.b + 16} textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}>{fmtDate(dates[i])}</text>)}
      <text className="axis-title" x={(M.l + W - M.r) / 2} y={H - 6} textAnchor="middle">Date</text>
      <text className="axis-title" transform={`translate(13 ${(M.t + H - M.b) / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
      {area && series[0] && <path d={areaPath(xs, series[0].values.map(y), y(Math.min(0, domain[1])))} fill="var(--fund-accent-soft,#eee4df)"/>}
      {refLines.map(r => <g key={r.label}><line x1={M.l} x2={W - M.r} y1={y(r.value)} y2={y(r.value)} stroke={r.color} strokeDasharray={r.dash ?? '5 4'} strokeWidth={1.2}/><text className="direct" x={W - M.r + 6} y={y(r.value) + 3}>{r.label}</text></g>)}
      {series.map(s => <path key={s.key} d={linePath(xs, s.values.map(y))} fill="none" stroke={s.color} strokeWidth={s.width ?? 1.8} strokeDasharray={s.dash} opacity={s.opacity ?? 1} strokeLinejoin="round"/>)}
      {spread(lastY.filter(l => Number.isFinite(l.y))).map(l => <text key={l.s.key} className="direct" x={W - M.r + 6} y={l.y + 3}>{l.s.label}</text>)}
      {hover !== null && <g aria-hidden="true"><line x1={xs[hover]} x2={xs[hover]} y1={M.t} y2={H - M.b} stroke="var(--fund-ink)" strokeOpacity={0.4}/>{series.map(s => <circle key={s.key} cx={xs[hover]} cy={y(s.values[hover])} r={3.5} fill="var(--fund-surface,#faf9f6)" stroke={s.color} strokeWidth={1.6}/>)}</g>}
    </svg>
    {hover !== null && <div className="chart-tip" id={`${id}-tip`} role="status" style={{ left: `${Math.min(88, Math.max(12, (xs[hover] / W) * 100))}%`, top: 8 }}>
      <b>{fmtDate(dates[hover])}</b>{series.map(s => <div key={s.key}>{s.label}: {fmt(s.values[hover])}</div>)}</div>}
    <ul className="chart-legend">{series.map(s => <li key={s.key}><i style={{ color: s.color, borderTopStyle: s.dash ? 'dashed' : 'solid', opacity: s.opacity ?? 1 }}/>{s.label}</li>)}
      {refLines.map(r => <li key={r.label}><i style={{ color: r.color, borderTopStyle: 'dashed' }}/>{r.label}</li>)}</ul>
  </div>
}

/** Nudge end-of-line labels apart so direct labels do not overlap. */
function spread<T extends { y: number }>(items: T[]): T[] {
  const sorted = [...items].sort((a, b) => a.y - b.y)
  const out: T[] = []
  for (const it of sorted) {
    const prev = out[out.length - 1]
    out.push(prev && it.y - prev.y < 12 ? { ...it, y: prev.y + 12 } : it)
  }
  return out
}
