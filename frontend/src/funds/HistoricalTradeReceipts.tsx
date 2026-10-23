import { useEffect, useState } from 'react'
import { orderMoney } from './paperOrders'
import './paperOrders.css'

export interface ReplayFill { date: string; ticker: string; side: string; shares: number; price: number }
export interface HistoricalReplay {
  mode: 'historical_simulation'; replay_id: string; clock: string; end: string; complete: boolean
  account: { cash: number; equity: number; positions: Record<string, number>; shares: Record<string, number> }
  orders: { id: string; symbol: string; side: string; requested_notional: number; status: string; decision_date: string; fill_date: string; fills: ReplayFill[]; skipped: {reason: string; detail?: string}[] }[]
  fills: ReplayFill[]
}

export function HistoricalTradeReceipts({ replay }: { replay: HistoricalReplay }) {
  if (replay.mode !== 'historical_simulation') return null
  const holdings = Object.entries(replay.account.positions).filter(([,value]) => value !== 0)
  return <section className="fund-panel paper-orders" aria-label="Historical simulated trades">
    <header><div><h3>Historical trades</h3><p>Historical simulation · {replay.clock}{replay.complete ? ' · Complete' : ''}</p></div></header>
    <dl className="replay-account"><div><dt>Virtual cash</dt><dd>{orderMoney(replay.account.cash)}</dd></div><div><dt>Virtual equity</dt><dd>{orderMoney(replay.account.equity)}</dd></div></dl>
    {holdings.length > 0 && <div className="replay-holdings">{holdings.map(([symbol,value]) => <p key={symbol}><strong>{symbol}</strong> {replay.account.shares[symbol]} shares · {orderMoney(value)}</p>)}</div>}
    {!replay.orders.length ? <p className="empty-text">No historical orders placed</p> : [...replay.orders].reverse().map(order => <article className="paper-receipt" key={order.id}>
      <header><strong><span className="order-side">{order.side}</span> {orderMoney(order.requested_notional)} of {order.symbol}</strong><span className="subtle-tag">{order.fills.length ? order.status === 'simulated_partial_fill' ? 'Simulated partial fill' : 'Simulated fill' : 'Unfilled in simulation'}</span></header>
      <p className="order-state">Decision {order.decision_date} · Historical simulation</p>
      {order.fills.map((fill,index) => <p className="order-fill" key={`${fill.date}-${index}`}>Simulated {fill.side} of {fill.shares} {fill.ticker} shares at {orderMoney(fill.price)} on {fill.date}</p>)}
      {order.skipped.map((skip,index) => <p className="order-state" key={index}>{skip.reason}{skip.detail ? `: ${skip.detail}` : ''}</p>)}
    </article>)}
  </section>
}

export function HistoricalReplayReceipts({ fundId, historical }: { fundId: string; historical: boolean }) {
  const [replay, setReplay] = useState<HistoricalReplay | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [available, setAvailable] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    let inFlight = false
    async function load() {
      if (inFlight || controller.signal.aborted) return
      inFlight = true
      try {
        const response = await fetch(`/api/funds/${fundId}/historical/replays`, {signal:controller.signal})
        if (controller.signal.aborted) return
        if (response.status === 404) { setReplay(null); setAvailable(false); setError(''); return }
        if (response.status === 401) { window.location.assign('/login'); return }
        if (!response.ok) throw new Error('Historical ledger could not be loaded.')
        const data: {replays: HistoricalReplay[]} = await response.json()
        const latest = data.replays?.at(-1)
        if (!controller.signal.aborted) { setReplay(latest?.mode === 'historical_simulation' ? latest : null); setAvailable(true); setError('') }
      } catch (problem) {
        if (!controller.signal.aborted) { setReplay(null); setError(problem instanceof Error ? problem.message : 'Historical ledger unavailable.') }
      } finally { inFlight = false; if (!controller.signal.aborted) setLoaded(true) }
    }
    void load()
    const interval = window.setInterval(() => { if (!document.hidden) void load() }, 5000)
    return () => { controller.abort(); window.clearInterval(interval) }
  }, [fundId])
  if (replay) return <HistoricalTradeReceipts replay={replay}/>
  if (!historical) return null
  return <section className="fund-panel paper-orders" aria-label="Historical simulated trades"><header><h3>Historical trades</h3></header><p className="empty-text">{error || (!loaded ? 'Loading historical ledger…' : !available ? 'Historical execution ledger unavailable' : 'No historical replay started')}</p></section>
}
