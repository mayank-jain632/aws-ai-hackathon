import type { BarGroup } from './BarChart'

const HOUR = 3_600_000
export const MAX_BUCKETS = 24
export interface ActivityEvent { id: string; time: string; kind: string }

export function bucketEvents(events: ActivityEvent[]): { groups: BarGroup[]; kinds: string[]; unit: 'hour' | 'day' } {
  const times = events.map(e => Date.parse(e.time)).filter(Number.isFinite)
  if (!times.length) return { groups: [], kinds: [], unit: 'hour' }
  const unit = Math.max(...times) - Math.min(...times) > 48 * HOUR ? 'day' : 'hour'
  const size = unit === 'day' ? 24 * HOUR : HOUR
  const map = new Map<number, Record<string, number>>()
  for (const e of events) {
    const t = Date.parse(e.time)
    if (!Number.isFinite(t)) continue
    const b = Math.floor(t / size) * size
    map.set(b, { ...(map.get(b) ?? {}), [e.kind]: ((map.get(b) ?? {})[e.kind] ?? 0) + 1 })
  }
  const keys = [...map.keys()].sort((a, b) => a - b).slice(-MAX_BUCKETS)
  const fmt = (b: number) => unit === 'day' ? new Date(b).toLocaleDateString([], { month: 'short', day: 'numeric' }) : new Date(b).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric' })
  const groups = keys.map(b => ({ label: fmt(b), tip: fmt(b), values: map.get(b) ?? {} }))
  const kinds = [...new Set(groups.flatMap(g => Object.keys(g.values)))]
  return { groups, kinds, unit }
}
