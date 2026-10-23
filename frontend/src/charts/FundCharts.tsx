import { useEffect, useState } from 'react'
import { api } from '../funds/types'
import { ActivityPanel, OrdersPanel } from './ActivityPanels'
import { GatePanel } from './GatePanel'
import { AllocationPanel, DrawdownPanel, MonthlyPanel, ReplayPanel, TeamPanel } from './ReplayPanels'
import type { FundChartsData } from './types'
import './charts.css'

interface FundChartsProps { fund: { id: string; activity: { id: string; time: string; kind: string }[] } }

// Mounted once from FundOverview. Reads the replay of the registered strategy; the fund's own NAV history is not recorded.
export function FundCharts({ fund }: FundChartsProps) {
  const [data, setData] = useState<FundChartsData | null>(null)
  const [strategy, setStrategy] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true
    const query = strategy ? `?strategy_id=${encodeURIComponent(strategy)}` : ''
    api<FundChartsData>(`/api/funds/${fund.id}/charts${query}`)
      .then(next => { if (active) { setData(next); setError('') } })
      .catch(problem => { if (active) setError(problem instanceof Error ? problem.message : 'Could not load charts.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [fund.id, strategy])
  const pick = (id: string) => { setLoading(true); setStrategy(id) }
  const bt = data?.backtest ?? null
  const current = data?.strategy ?? null
  return <section className="fund-charts" aria-labelledby={`charts-${fund.id}`} aria-busy={loading}>
    <div className="performance-heading"><div><h2 id={`charts-${fund.id}`}>Charts</h2><p>Strategy replay, risk, allocation, orders and agent activity. Strategy figures come from a historical replay, not from this fund's paper account.</p></div></div>
    {error && <p className="charts-error" role="alert">{error}</p>}
    {loading && !data && <div className="loader" role="status" aria-label="Loading charts"/>}
    {data && <>
      <div className="charts-meta">
        {data.strategies.length > 1 && <label>Strategy <select value={current?.id ?? ''} onChange={event => pick(event.target.value)}>
          {data.strategies.map(s => <option key={s.id} value={s.id}>{s.name} · {new Date(s.created_at).toLocaleDateString()}{s.verdict ? ` · ${s.verdict}` : ''}</option>)}</select></label>}
        {current?.verdict && <span className={`subtle-tag ${current.verdict === 'PASS' ? 'pass' : 'fail'}`}>{current.verdict === 'PASS' ? '✓' : '✕'} Gate {current.verdict}</span>}
        {!current && <span>No strategy has been registered and tested for this fund.</span>}
        {data.notes.map(note => <span key={note}>{note}</span>)}
      </div>
      <div className="charts-grid">
        <ReplayPanel bt={bt} strategy={current}/>
        <DrawdownPanel bt={bt} strategy={current}/>
        <MonthlyPanel bt={bt}/>
        <AllocationPanel allocation={data.allocation}/>
        <GatePanel bt={bt} allocation={data.allocation}/>
        <TeamPanel team={data.team}/>
        <OrdersPanel orders={data.orders}/>
        <ActivityPanel events={fund.activity}/>
      </div>
    </>}
  </section>
}
