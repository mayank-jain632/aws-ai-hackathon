import { bucketEvents, type ActivityEvent } from './activityBuckets'
import { GroupedBarChart, type BarGroup, type BarSeries } from './BarChart'
import { fmtMoney, fmtMoneyShort } from './chartMath'
import { Empty, Panel } from './Panel'
import type { ChartOrder } from './types'

const PALETTE = ['var(--fund-accent)', 'var(--fund-ink)', 'var(--fund-muted)', '#b38469', '#a38e7a', '#69816b']
const MAX_BUCKETS = 24

export function OrdersPanel({ orders }: { orders: ChartOrder[] }) {
  const sub = 'Notional (USD) of each recorded paper order, coloured by broker status; a submitted order is not a fill'
  if (!orders.length) return <Panel title="Paper orders" subtitle={sub}><Empty>No paper orders are recorded for this fund.</Empty></Panel>
  const sorted = [...orders].sort((a, b) => Date.parse(a.time) - Date.parse(b.time)).slice(-MAX_BUCKETS)
  const statuses = [...new Set(sorted.map(o => o.status))]
  const series: BarSeries[] = statuses.map((s, i) => ({ key: s, label: s, color: PALETTE[i % PALETTE.length], pattern: i % 2 === 1 }))
  const groups: BarGroup[] = sorted.map(o => ({ label: o.symbol, tip: `${o.side} ${o.symbol} ${new Date(o.time).toLocaleString()}`, values: { [o.status]: o.notional } }))
  return <Panel title="Paper orders" subtitle={sub} tag={`${orders.length} recorded`}>
    <div className="chart-body"><GroupedBarChart groups={groups} series={series} stacked xLabel="Recorded order, oldest to newest" yLabel="Notional (USD)" format={v => (v >= 1000 ? fmtMoneyShort(v) : fmtMoney(v))} maxLabels={12}
      ariaLabel={`${orders.length} recorded paper orders, statuses: ${statuses.join(', ')}.`}/></div>
  </Panel>
}

export function ActivityPanel({ events }: { events: ActivityEvent[] }) {
  const { groups, kinds, unit } = bucketEvents(events)
  const sub = `Agent events per ${unit} on this fund's canvas, by event type`
  if (!groups.length) return <Panel title="Agent activity" subtitle={sub}><Empty>No agent activity yet.</Empty></Panel>
  const series: BarSeries[] = kinds.map((k, i) => ({ key: k, label: k, color: PALETTE[i % PALETTE.length], pattern: i % 2 === 1 }))
  return <Panel title="Agent activity" subtitle={sub} tag={`${events.length} events`}>
    <div className="chart-body"><GroupedBarChart groups={groups} series={series} stacked xLabel={unit === 'day' ? 'Day' : 'Hour'} yLabel="Events" format={v => (Number.isInteger(v) ? String(v) : '')} maxLabels={6}
      ariaLabel={`${events.length} agent events in ${groups.length} ${unit} buckets, types: ${kinds.join(', ')}.`}/></div>
  </Panel>
}
