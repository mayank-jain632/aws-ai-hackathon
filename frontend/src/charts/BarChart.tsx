import { useState } from 'react'
import { linear, niceTicks } from './chartMath'
import type { BarDatum } from './types'
import { useContainerWidth } from './useContainerWidth'

export interface HBarProps { data: BarDatum[]; format: (v: number) => string; marker?: { value: number; label: string } | null; ariaLabel: string; xLabel: string }

/** Horizontal bars by label (allocation), with an optional dashed cap marker. */
export function HBarChart({ data, format, marker, ariaLabel, xLabel }: HBarProps) {
  const { ref: wrap, width: W } = useContainerWidth(720)
  const row = 26, M = { t: 22, r: 60, b: 40, l: 64 }
  const H = M.t + M.b + data.length * row
  const max = Math.max(...data.map(d => d.value), marker?.value ?? 0)
  const { ticks, domain } = niceTicks(0, max, 5)
  const x = linear(domain, [M.l, W - M.r])
  return <div className="chart-wrap" ref={wrap}><svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel}>
    {ticks.map(t => <g key={t}><line className="grid" x1={x(t)} x2={x(t)} y1={M.t} y2={H - M.b}/><text x={x(t)} y={H - M.b + 14} textAnchor="middle">{format(t)}</text></g>)}
    <line className="axis" x1={M.l} x2={M.l} y1={M.t} y2={H - M.b}/>
    <text className="axis-title" x={(M.l + W - M.r) / 2} y={H - 6} textAnchor="middle">{xLabel}</text>
    {data.map((d, i) => <g key={d.label}><text x={M.l - 8} y={M.t + i * row + row / 2 + 3} textAnchor="end" className="direct">{d.label}</text>
      <rect x={M.l} y={M.t + i * row + 4} width={Math.max(0, x(d.value) - M.l)} height={row - 8} fill="var(--fund-accent)"><title>{d.label}: {format(d.value)}</title></rect>
      <text x={x(d.value) + 6} y={M.t + i * row + row / 2 + 3}>{format(d.value)}</text></g>)}
    {marker && <g><line x1={x(marker.value)} x2={x(marker.value)} y1={M.t - 6} y2={H - M.b} stroke="var(--fund-ink)" strokeWidth={1.3} strokeDasharray="5 4"/><text className="direct" x={x(marker.value)} y={M.t - 9} textAnchor="middle">{marker.label}</text></g>}
  </svg></div>
}

export interface BarSeries { key: string; label: string; color: string; pattern?: boolean }
export interface BarGroup { label: string; values: Record<string, number>; tip?: string }
export interface GroupedBarProps {
  groups: BarGroup[]; series: BarSeries[]; format: (v: number) => string; yLabel: string; xLabel: string
  ariaLabel: string; stacked?: boolean; maxLabels?: number; signed?: boolean
}

/** Vertical grouped or stacked bars; each bar is keyboard focusable and reveals its value. */
export function GroupedBarChart({ groups, series, format, yLabel, xLabel, ariaLabel, stacked = false, maxLabels = 8, signed = false }: GroupedBarProps) {
  const [focus, setFocus] = useState<string | null>(null)
  const { ref: wrap, width: W } = useContainerWidth(720)
  const H = 270, M = { t: 16, r: 14, b: 50, l: 62 }
  const totals = groups.map(g => series.reduce((s, k) => s + (g.values[k.key] ?? 0), 0))
  const all = groups.flatMap(g => series.map(k => g.values[k.key] ?? 0))
  const hiV = stacked ? Math.max(0, ...totals) : Math.max(0, ...all)
  const loV = signed && !stacked ? Math.min(0, ...all) : 0
  const { ticks, domain } = niceTicks(loV, hiV || 1, 5)
  const y = linear(domain, [H - M.b, M.t])
  const slot = (W - M.l - M.r) / Math.max(1, groups.length)
  const barW = Math.max(2, (slot * 0.72) / (stacked ? 1 : series.length))
  const step = Math.max(1, Math.ceil(groups.length / maxLabels))
  const zero = y(0)
  return <div className="chart-wrap" ref={wrap}><svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel}>
    <defs><pattern id="bar-hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="4" fill="var(--fund-surface,#faf9f6)"/><rect width="2" height="4" fill="var(--fund-ink)" opacity=".7"/></pattern></defs>
    {ticks.map(t => <g key={t}><line className="grid" x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)}/><text x={M.l - 8} y={y(t) + 3} textAnchor="end">{format(t)}</text></g>)}
    <line className="axis" x1={M.l} x2={W - M.r} y1={zero} y2={zero}/>
    <text className="axis-title" x={(M.l + W - M.r) / 2} y={H - 6} textAnchor="middle">{xLabel}</text>
    <text className="axis-title" transform={`translate(13 ${(M.t + H - M.b) / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
    {groups.map((g, gi) => {
      const gx = M.l + gi * slot + (slot - barW * (stacked ? 1 : series.length)) / 2
      let acc = 0
      return <g key={`${g.label}-${gi}`}>
        {gi % step === 0 && <text x={M.l + gi * slot + slot / 2} y={H - M.b + 15} textAnchor="middle">{g.label}</text>}
        {series.map((k, ki) => {
          const v = g.values[k.key] ?? 0
          if (!v && stacked) return null
          const top = stacked ? y(acc + v) : y(Math.max(v, 0))
          const h = stacked ? y(acc) - y(acc + v) : Math.abs(y(v) - zero)
          const bx = stacked ? gx : gx + ki * barW
          const bid = `${gi}:${k.key}`
          if (stacked) acc += v
          return <g key={k.key}><rect x={bx} y={top} width={barW - 1} height={Math.max(1, h)} fill={k.pattern ? 'url(#bar-hatch)' : k.color} stroke={k.pattern ? 'var(--fund-ink)' : 'none'} strokeOpacity=".7" tabIndex={0}
            aria-label={`${g.tip ?? g.label}, ${k.label}: ${format(v)}`} onFocus={() => setFocus(bid)} onBlur={() => setFocus(null)} onPointerEnter={() => setFocus(bid)} onPointerLeave={() => setFocus(null)}><title>{`${g.tip ?? g.label} · ${k.label}: ${format(v)}`}</title></rect>
            {focus === bid && <text className="direct" x={bx + barW / 2} y={Math.max(11, top - 4)} textAnchor="middle">{format(v)}</text>}</g>
        })}
      </g>
    })}
  </svg>
  <ul className="chart-legend">{series.map(k => <li key={k.key}><i className="box" style={{ background: k.pattern ? 'repeating-linear-gradient(45deg,var(--fund-ink) 0 2px,transparent 2px 4px)' : k.color }}/>{k.label}</li>)}</ul></div>
}
