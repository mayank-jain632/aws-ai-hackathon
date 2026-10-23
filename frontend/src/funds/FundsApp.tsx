import { useEffect, useRef, useState } from 'react'
import AgentWorkspace from '../AgentWorkspace'
import { AwsBrand } from './AwsBrand'
import { FundOverview } from './FundOverview'
import { FundSetup } from './FundSetup'
import { FundPreview } from './FundPreview'
import { ShareFundButton } from './ShareFundButton'
import { api, json, money, objectives, type Fund, type Mandate } from './types'
import './funds.css'

function route() { const parts = window.location.hash.replace(/^#\/?/,'').split('/'); return { id: parts[0] === 'funds' ? parts[1] || '' : '', tab: parts[2] || 'overview' } }
const go = (id = '', tab = 'overview') => { window.location.hash = id ? `/funds/${id}/${tab}` : '/' }

export default function FundsApp() {
  const [location, setLocation] = useState(route)
  const main = useRef<HTMLElement>(null)
  const [funds, setFunds] = useState<Fund[]>([])
  const [identity, setIdentity] = useState({ email: 'local', hosted: false })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [setup, setSetup] = useState<'new' | 'edit' | null>(null)
  const [busy, setBusy] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState('')
  const selected = funds.find(fund => fund.id === location.id)
  function allFunds() { setShowArchived(false); setQuery('') }
  useEffect(() => { main.current?.scrollTo({top: 0}) }, [location.id, location.tab])
  async function refresh() { const data = await api<{ funds: Fund[] }>('/api/funds'); setFunds(data.funds); setLoading(false) }
  useEffect(() => { const update = () => setLocation(route()); window.addEventListener('hashchange',update); return () => window.removeEventListener('hashchange',update) }, [])
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const update = () => api<{funds: Fund[]}>('/api/funds', {signal: controller.signal}).then(data => { if (active) { setFunds(data.funds); setLoading(false); setError(current => current === 'Could not refresh funds. Reconnecting…' ? '' : current) } }).catch(() => { if (active) { setError('Could not refresh funds. Reconnecting…'); setLoading(false) } })
    void update(); void api<typeof identity>('/api/me', {signal: controller.signal}).then(value => { if(active) setIdentity(value) }).catch(() => {})
    const timer = window.setInterval(update,4000)
    return () => { active = false; controller.abort(); clearInterval(timer) }
  }, [])
  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(''),4500); return () => clearTimeout(timer) }, [notice])
  async function save(mandate: Mandate) {
    const fund = await api<Fund>(setup === 'edit' && selected ? `/api/funds/${selected.id}/mandate` : '/api/funds', json(setup === 'edit' ? 'PUT' : 'POST',mandate))
    setFunds(previous => [...previous.filter(item => item.id !== fund.id), fund]); setSetup(null); setNotice(setup === 'edit' ? 'Fund mandate updated.' : 'Fund created.'); go(fund.id)
  }
  async function plan() {
    if (!selected) return
    setBusy(true); setError('')
    try { await api(`/api/funds/${selected.id}/plan`,{method:'POST'}); go(selected.id,'agents'); setNotice('Fund planning started.') } catch(e) { setError(e instanceof Error ? e.message : 'Could not start planning.') } finally { setBusy(false) }
  }
  async function status(next: Fund['status']) {
    if (!selected) return
    setBusy(true); setError('')
    try { await api(`/api/funds/${selected.id}/status`,json('PATCH',{status:next})); await refresh(); setNotice(next === 'active' ? 'Fund resumed.' : next === 'paused' ? 'Fund paused. Running agents stopped.' : 'Fund archived. You can restore it from archived funds.'); if(next === 'archived') go() } catch(e) { setError(e instanceof Error ? e.message : 'Could not update this fund.') } finally { setBusy(false) }
  }
  const activeFunds = funds.filter(f => f.status !== 'archived')
  const visible = funds.filter(f => (showArchived ? f.status === 'archived' : f.status !== 'archived') && `${f.name} ${f.objective}`.toLowerCase().includes(query.toLowerCase()))
  const capital = activeFunds.reduce((sum,fund) => sum + fund.metrics.nav,0)
  const totalAgents = activeFunds.reduce((sum,fund) => sum + fund.metrics.agents,0)
  const working = activeFunds.reduce((sum,fund) => sum + fund.metrics.working,0)
  return <div className="fund-shell">
    <aside className="fund-sidebar"><a className="desk-brand" href="#/" onClick={allFunds}><strong>Fund desk<span>Research & capital</span></strong></a><span className="workspace-label">Team 4 workspace</span><nav className="primary-nav" aria-label="Main navigation"><a href="#/" onClick={allFunds} className={!location.id ? 'selected' : ''}>All funds<span className="nav-count">{activeFunds.length}</span></a><button onClick={() => setSetup('new')}>Create fund</button></nav><div className="sidebar-funds"><p>Your funds</p>{activeFunds.map(fund => <a key={fund.id} href={`#/funds/${fund.id}/overview`} className={selected?.id === fund.id ? 'selected' : ''}><i className={`dot ${fund.status}`}/><span>{fund.name}</span></a>)}</div><div className="sidebar-bottom"><div className="aws-status"><i/>Amazon Bedrock agents</div><div className="user-row"><span className="user-avatar">{identity.email === 'local' ? 'T' : identity.email[0].toUpperCase()}</span><div><strong>{identity.email === 'local' ? 'Local team' : identity.email.split('@')[0]}</strong><small>Shared workspace</small></div>{identity.hosted && <a href="/logout" aria-label="Sign out" title="Sign out">↪</a>}</div></div></aside>
    <main ref={main} className={`fund-main ${selected && location.tab === 'agents' ? 'canvas-page' : ''}`}>
      <header className="desk-topbar"><div className="breadcrumb"><a className="all-funds-link" href="#/" onClick={allFunds}>All funds <span>{activeFunds.length}</span></a>{selected && <><span>/</span>{selected.name}</>}</div><div className="topbar-right"><AwsBrand/></div></header>
      {error && <div className="fund-alert" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
      {notice && <div className="fund-toast" role="status"><span>✓</span>{notice}</div>}
      {loading ? <div className="fund-loading"><span className="loader"/>Loading your workspace…</div> : location.id && !selected ? <div className="fund-loading"><h2>Fund not found</h2><p>It may have been removed or this link is incorrect.</p><button className="primary" onClick={() => go()}>Back to funds</button></div> : selected ? <><div className="fund-heading"><div><div className="fund-title-row"><h1>{selected.name}</h1><span className={`status-tag ${selected.status}`}>{selected.status === 'active' ? 'Research' : selected.status}</span></div><p>{selected.description || objectives[selected.objective]}</p></div><div className="fund-heading-actions"><ShareFundButton fundId={selected.id} name={selected.name} view={location.tab}/><button className="secondary" onClick={() => setSetup('edit')}>Settings</button></div></div><nav className="fund-tabs" aria-label="Fund views"><a href={`#/funds/${selected.id}/overview`} aria-current={location.tab !== 'agents' ? 'page' : undefined}>Overview</a><a href={`#/funds/${selected.id}/agents`} aria-current={location.tab === 'agents' ? 'page' : undefined}>Agent canvas <span>{selected.metrics.agents}</span></a></nav>{location.tab === 'agents' ? <div className="fund-canvas"><AgentWorkspace key={selected.id} fundId={selected.id} fundName={selected.name}/></div> : <FundOverview fund={selected} busy={busy} onCanvas={() => go(selected.id,'agents')} onPlan={() => void plan()} onEdit={() => setSetup('edit')} onStatus={next => void status(next)}/>}</> : <div className="home-content">
        <div className="home-heading"><div><h1>All funds</h1><p>{activeFunds.length} funds · {money(capital)} paper capital · {totalAgents} agents{working ? ` · ${working} working` : ''}</p></div><button className="primary" onClick={() => setSetup('new')}>Create fund</button></div>
        <div className="fund-list-heading"><div className="list-switch"><button className={!showArchived ? 'current' : ''} onClick={() => setShowArchived(false)}>Funds <span>{activeFunds.length}</span></button><button className={showArchived ? 'current' : ''} onClick={() => setShowArchived(true)}>Archived <span>{funds.length - activeFunds.length}</span></button></div><label className="fund-search"><input aria-label="Search funds" placeholder="Search funds" value={query} onChange={e => setQuery(e.target.value)}/></label></div>
        <div className="fund-card-grid">{visible.map(fund => <article className="fund-card" key={fund.id}>
          <a className="fund-card-link" href={`#/funds/${fund.id}/overview`} aria-label={`Open ${fund.name}`}><FundPreview fund={fund}/><div className="fund-card-title"><div><h2>{fund.name}</h2><p>{objectives[fund.objective]}</p></div><span className={`status-tag ${fund.status}`}>{fund.status === 'active' ? fund.metrics.working ? 'Working' : 'Ready' : fund.status}</span></div></a>
          <div className="fund-card-footer"><div><strong>{money(fund.metrics.nav)}</strong><span>{fund.metrics.agents} {fund.metrics.agents === 1 ? 'agent' : 'agents'}</span></div><ShareFundButton fundId={fund.id} name={fund.name}/></div>
        </article>)}</div>
        {!visible.length && <div className="fund-list-empty"><h3>{query ? 'No matching funds' : showArchived ? 'No archived funds' : 'No funds yet'}</h3>{!query && !showArchived && <button className="primary" onClick={() => setSetup('new')}>Create fund</button>}</div>}
        <footer className="home-footer">All funds are shared with your team. Previews update automatically.</footer></div>}
    </main>{setup && <FundSetup initial={setup === 'edit' && selected ? selected : undefined} onClose={() => setSetup(null)} onSave={save}/>}</div>
}
