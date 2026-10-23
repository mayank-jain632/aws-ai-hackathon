import { useEffect, useRef, useState } from 'react'
import { api } from './types'
import { needsBrokerRefresh, orderMoney, orderRows, orderTime, plannedTrades, receiptStatus, type OrderPlanRecord, type PaperOrder } from './paperOrders'
import './paperOrders.css'

export function PaperReceipt({ order }: { order: PaperOrder }) {
  const quantity = order.filled_qty
  const hasFill = quantity !== null && quantity !== undefined && Number(quantity) > 0
  return <article className="paper-receipt">
    <header><strong><span className="order-side">{order.side}</span> {orderMoney(order.notional)} of {order.symbol}</strong><span className="subtle-tag">{receiptStatus(order)}</span></header>
    <p className="order-state">{order.status || 'Status unavailable'}{!hasFill && order.broker_id && !['filled','canceled','cancelled','expired','rejected'].includes(order.status) ? ' · Awaiting fill' : ''}</p>
    {hasFill && <p className="order-fill">Filled {String(quantity)} shares at {orderMoney(order.filled_avg_price)}</p>}
    <details><summary>Order details</summary><dl><dt>Broker order ID</dt><dd>{order.broker_id || 'Not returned'}</dd><dt>Client order ID</dt><dd>{order.client_order_id || 'Not reported'}</dd>
      <dt>{order.submitted_at ? 'Broker submitted' : 'Recorded at'}</dt><dd>{orderTime(order.submitted_at || order.time)}</dd>
      {hasFill ? <><dt>Filled quantity</dt><dd>{String(quantity)}</dd><dt>Average fill price</dt><dd>{orderMoney(order.filled_avg_price)}</dd><dt>Filled at</dt><dd>{orderTime(order.filled_at)}</dd></> : <><dt>Fill</dt><dd>{order.status === 'filled' ? 'Fill details not returned' : 'No fill reported'}</dd></>}
      {order.last_checked_at && <><dt>Status checked</dt><dd>{orderTime(order.last_checked_at)}</dd></>}
    </dl></details>
  </article>
}

export function PaperOrderReceipts({ fundId }: { fundId: string }) {
  const [orders, setOrders] = useState<PaperOrder[] | null>(null)
  const [plans, setPlans] = useState<OrderPlanRecord[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const refresh = useRef<() => void>(() => {})
  useEffect(() => {
    const controller = new AbortController()
    let inFlight = false
    async function load(reconcile = false) {
      if (inFlight || controller.signal.aborted) return
      inFlight = true; setLoading(true)
      try {
        const [desk, activity] = await Promise.all([
          api<{orders: Record<string, PaperOrder>}>(`/api/funds/${fundId}/desk`, {signal:controller.signal}),
          api<{runs: OrderPlanRecord[]}>(`/api/funds/${fundId}/desk/runs`, {signal:controller.signal}),
        ])
        let receipts = orderRows(desk.orders || {})
        let refreshError = ''
        if (reconcile) {
          const checks = await Promise.allSettled(receipts.filter(needsBrokerRefresh).map(order => api<PaperOrder>(`/api/funds/${fundId}/desk/orders/${encodeURIComponent(order.client_order_id)}`, {signal:controller.signal})))
          for (const check of checks) {
            if (check.status === 'fulfilled') receipts = receipts.map(order => order.client_order_id === check.value.client_order_id ? check.value as typeof order : order)
            else refreshError = 'Could not refresh every broker status. Showing the latest saved receipts.'
          }
        }
        if (!controller.signal.aborted) { setOrders(receipts); setPlans(activity.runs || []); setError(refreshError) }
      } catch (problem) {
        if (!controller.signal.aborted) { setOrders(null); setError(problem instanceof Error ? problem.message : 'Could not load paper orders.') }
      } finally { inFlight = false; if (!controller.signal.aborted) setLoading(false) }
    }
    refresh.current = () => { void load(true) }
    void load()
    const interval = window.setInterval(() => { if (!document.hidden) void load() }, 5000)
    return () => { controller.abort(); window.clearInterval(interval) }
  }, [fundId])
  const intended = plannedTrades(plans, orders || [])
  return <section className="fund-panel paper-orders" aria-label="Paper order receipts">
    <header><div><h3>Paper orders</h3></div><button className="text-button" disabled={loading} onClick={() => refresh.current()}>{loading ? 'Refreshing…' : 'Refresh orders'}</button></header>
    {error && <p className="fund-error" role="alert">{error}</p>}
    {orders === null ? !error && <p className="empty-text">Loading paper orders…</p> : <>
      {intended.map(order => <article className="paper-receipt" key={`plan-${order.client_order_id}`}><header><strong>Agent plans to {order.side} {orderMoney(order.notional)} of {order.symbol}</strong><span className="subtle-tag">Prepared · not submitted</span></header><p className="order-state">Saved plan · {orderTime(order.planned_at)}</p>{order.blockers.map(reason => <p className="order-state" key={reason}>{reason}</p>)}</article>)}
      {!orders.length ? <p className="empty-text">No paper orders submitted</p> : orders.map(order => <PaperReceipt key={order.client_order_id} order={order}/>)}
    </>}
  </section>
}
