export interface Scale { (v: number): number; domain: [number, number]; range: [number, number] }

export function linear(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain
  const span = d1 - d0 || 1
  const fn = (v: number) => range[0] + ((v - d0) / span) * (range[1] - range[0])
  return Object.assign(fn, { domain, range })
}

export function niceStep(span: number, count: number): number {
  const raw = span / Math.max(1, count)
  if (!(raw > 0) || !Number.isFinite(raw)) return 1
  const mag = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / mag
  return (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag
}

/** Round the extent outward to "nice" bounds and return evenly spaced ticks. */
export function niceTicks(min: number, max: number, count = 5): { ticks: number[]; domain: [number, number] } {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { ticks: [0, 1], domain: [0, 1] }
  if (min === max) { const pad = Math.abs(min) * 0.05 || 1; min -= pad; max += pad }
  const step = niceStep(max - min, count)
  const lo = Math.floor(min / step) * step
  const hi = Math.ceil(max / step) * step
  const ticks: number[] = []
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.round(v / step) * step)
  return { ticks, domain: [lo, hi] }
}

export function extent(arrays: readonly (readonly number[])[]): [number, number] {
  let lo = Infinity
  let hi = -Infinity
  for (const a of arrays) for (const v of a) if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v }
  return lo > hi ? [0, 1] : [lo, hi]
}

export function linePath(xs: readonly number[], ys: readonly number[]): string {
  let d = ''
  xs.forEach((x, i) => { if (Number.isFinite(ys[i])) d += `${d ? 'L' : 'M'}${x.toFixed(1)},${ys[i].toFixed(1)}` })
  return d
}

export function areaPath(xs: readonly number[], ys: readonly number[], baseline: number): string {
  if (!xs.length) return ''
  return `${linePath(xs, ys)}L${xs[xs.length - 1].toFixed(1)},${baseline.toFixed(1)}L${xs[0].toFixed(1)},${baseline.toFixed(1)}Z`
}

export function evenTicks(n: number, count: number): number[] {
  if (n <= 0) return []
  const k = Math.min(count, n)
  if (k === 1) return [0]
  return Array.from({ length: k }, (_, i) => Math.round((i * (n - 1)) / (k - 1)))
}

export function nearestIndex(px: number, xs: readonly number[]): number {
  let best = 0
  for (let i = 1; i < xs.length; i++) if (Math.abs(xs[i] - px) < Math.abs(xs[best] - px)) best = i
  return best
}

export const fmtMoney = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
export const fmtMoneyShort = (n: number) => {
  const a = Math.abs(n)
  const s = a >= 1e6 ? `${+(a / 1e6).toFixed(2)}M` : a >= 1e3 ? `${+(a / 1e3).toFixed(1)}k` : `${Math.round(a)}`
  return `${n < 0 ? '-' : ''}$${s}`
}
export const fmtPct = (f: number, digits = 1) => `${(f * 100).toFixed(digits)}%`
export const fmtSignedPct = (f: number, digits = 1) => `${f > 0 ? '+' : ''}${(f * 100).toFixed(digits)}%`
export const fmtNum = (n: number, digits = 2) => n.toFixed(digits)

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function fmtDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}` : iso
}
export function fmtMonth(ym: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(ym)
  return m ? `${MONTHS[Number(m[2]) - 1]} '${m[1].slice(2)}` : ym
}

/** Accept either a fraction (0.2) or a percent (20) and return a fraction. */
export const asFraction = (v: number): number => (Math.abs(v) > 1 ? v / 100 : v)
