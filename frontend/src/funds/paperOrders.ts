export interface PaperOrder {
  client_order_id?: string; broker_id?: string; symbol: string; side: string
  notional: number | string; status: string; time?: string; submitted_at?: string | null
  filled_qty?: string | number | null; filled_avg_price?: string | number | null
  filled_at?: string | null; last_checked_at?: string
}
export function orderRows(orders: Record<string, PaperOrder>) {
  return Object.entries(orders).map(([key, order]) => ({ ...order, client_order_id: order.client_order_id || key }))
    .sort((a, b) => (b.submitted_at || b.time || '').localeCompare(a.submitted_at || a.time || ''))
}
export interface OrderPlanRecord {
  kind: string; time: string; strategy_id: string; orders: PaperOrder[]; blocked: string[]; ready: boolean
}
export function plannedTrades(runs: OrderPlanRecord[], receipts: PaperOrder[]) {
  const latest = runs.filter(run => run.kind === 'order_plan').sort((a,b) => a.time.localeCompare(b.time)).at(-1)
  if (!latest) return []
  const submitted = new Set(receipts.map(order => order.client_order_id))
  return latest.orders.filter(order => !submitted.has(order.client_order_id)).map(order => ({...order, planned_at:latest.time, blockers:latest.blocked || []}))
}
export function receiptStatus(order: PaperOrder) {
  if (order.status === 'filled') return 'Filled'
  if (order.status === 'partially_filled') return 'Partially filled'
  if (order.status === 'unknown') return 'Submission unconfirmed'
  if (order.status === 'submitting') return 'Submission in progress'
  if (['canceled','cancelled','expired','rejected'].includes(order.status)) return order.status[0].toUpperCase()+order.status.slice(1)
  return order.broker_id ? 'Submitted to Alpaca' : 'No broker confirmation'
}
export function orderMoney(value: number | string | null | undefined) {
  if (value === undefined || value === null || value === '' || !Number.isFinite(Number(value))) return 'Not reported'
  return new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', minimumFractionDigits:2, maximumFractionDigits:6}).format(Number(value))
}
export function orderTime(value?: string | null) {
  if (!value) return 'Not reported'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString()
}
