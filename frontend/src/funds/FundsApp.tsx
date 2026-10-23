import { useEffect, useState } from 'react'
import AgentWorkspace from '../AgentWorkspace'
import { FundOverview } from './FundOverview'
import { FundSetup } from './FundSetup'
import { api, json, money, objectives, riskNames, type Fund, type Mandate } from './types'
import './funds.css'

function route() { const parts = window.location.hash.replace(/^#\/?/,'').split('/'); return { id: parts[0] === 'funds' ? parts[1] || '' : '', tab: parts[2] || 'overview' } }
const go = (id = '', tab = 'overview') => { window.location.hash = id ? `/funds/${id}/${tab}` : '/' }

export default function FundsApp() {
  const [location, setLocation] = useState(route)
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
    setFunds(previous => [...previous.filter(item => item.id !== fund.id), fund]); setSetup(null); setNotice(setup === 'edit' ? 'Fund mandate updated.' : 'Fund created. Your workspace is ready.'); go(fund.id)
  }
  async function plan() {
    if (!selected) return
    setBusy(true); setError('')
    try { await api(`/api/funds/${selected.id}/plan`,{method:'POST'}); go(selected.id,'agents'); setNotice('Your agent is preparing a plan from the fund mandate.') } catch(e) { setError(e instanceof Error ? e.message : 'Could not start planning.') } finally { setBusy(false) }
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
    <aside className="fund-sidebar"><a className="desk-brand" href="#/"><span className="desk-logo">f<span>.</span></span><strong>Fund desk</strong></a><span className="workspace-label">Team 4 workspace</span><nav className="primary-nav" aria-label="Main navigation"><a href="#/" className={!location.id ? 'selected' : ''}><span>▦</span>All funds<span className="nav-count">{activeFunds.length}</span></a><button onClick={() => setSetup('new')}><span>＋</span>Create fund</button></nav><div className="sidebar-funds"><p>Your funds</p>{activeFunds.map(fund => <a key={fund.id} href={`#/funds/${fund.id}/overview`} className={selected?.id === fund.id ? 'selected' : ''}><i className={`dot ${fund.status}`}/><span>{fund.name}</span></a>)}</div><div className="sidebar-bottom"><div className="aws-status"><i/>Amazon Bedrock agents</div><div className="user-row"><span className="user-avatar">{identity.email === 'local' ? 'T' : identity.email[0].toUpperCase()}</span><div><strong>{identity.email === 'local' ? 'Local team' : identity.email.split('@')[0]}</strong><small>Shared workspace</small></div>{identity.hosted && <a href="/logout" aria-label="Sign out" title="Sign out">↪</a>}</div></div></aside>
    <main className={`fund-main ${selected && location.tab === 'agents' ? 'canvas-page' : ''}`}>
      <header className="desk-topbar"><div className="breadcrumb"><a href="#/">Workspace</a><span>/</span>{selected ? selected.name : 'All funds'}</div><div className="topbar-right"><span className="paper-label">Paper trading & research</span><span className="team-avatars" title="Shared team workspace"><i>K</i><i>M</i><i>G</i></span></div></header>
      {error && <div className="fund-alert" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
      {notice && <div className="fund-toast" role="status"><span>✓</span>{notice}</div>}
      {loading ? <div className="fund-loading"><span className="loader"/>Loading your workspace…</div> : location.id && !selected ? <div className="fund-loading"><h2>Fund not found</h2><p>It may have been removed or this link is incorrect.</p><button className="primary" onClick={() => go()}>Back to funds</button></div> : selected ? <><div className="fund-heading"><div><div className="fund-title-row"><span className={`fund-monogram ${selected.risk}`}>{selected.name[0]}</span><h1>{selected.name}</h1><span className={`status-tag ${selected.status}`}>{selected.status === 'active' ? 'Research' : selected.status}</span></div><p>{selected.description || objectives[selected.objective]}</p></div><button className="secondary" onClick={() => setSetup('edit')}>Fund settings <span>⚙</span></button></div><nav className="fund-tabs" aria-label="Fund views"><a href={`#/funds/${selected.id}/overview`} aria-current={location.tab !== 'agents' ? 'page' : undefined}>Overview</a><a href={`#/funds/${selected.id}/agents`} aria-current={location.tab === 'agents' ? 'page' : undefined}>Agent canvas <span>{selected.metrics.agents}</span></a></nav>{location.tab === 'agents' ? <div className="fund-canvas"><AgentWorkspace key={selected.id} fundId={selected.id} fundName={selected.name}/></div> : <FundOverview fund={selected} busy={busy} onCanvas={() => go(selected.id,'agents')} onPlan={() => void plan()} onEdit={() => setSetup('edit')} onStatus={next => void status(next)}/>}</> : <div className="home-content"><div className="home-heading"><div><p className="welcome">Your investment workspace</p><h1>A clear view of every fund.</h1><p>Set the mandate. Put your agents to work. Keep the whole picture.</p></div><button className="primary" onClick={() => setSetup('new')}>＋ Create fund</button></div><section className="home-stats" aria-label="Workspace summary"><div><span>Total paper capital</span><strong>{money(capital)}</strong><small>Across {activeFunds.length} funds</small></div><div><span>Active funds</span><strong>{activeFunds.filter(f=>f.status==='active').length}<em> / {activeFunds.length}</em></strong><small>Research workspaces</small></div><div><span>Agent team</span><strong>{totalAgents}</strong><small>{working ? `${working} agents working` : 'Ready when you are'}</small></div><div className="summary-note"><span className="summary-icon">◈</span><strong>Research first.<br/>Evidence before execution.</strong><small>Every fund has its own mandate and agent team.</small></div></section>
      <div className="fund-list-heading"><div className="list-switch"><button className={!showArchived ? 'current' : ''} onClick={() => setShowArchived(false)}>Your funds <span>{activeFunds.length}</span></button><button className={showArchived ? 'current' : ''} onClick={() => setShowArchived(true)}>Archived</button></div><label className="fund-search"><span>⌕</span><input aria-label="Search funds" placeholder="Search funds…" value={query} onChange={e => setQuery(e.target.value)}/></label></div>
      <div className="fund-table"><div className="fund-table-header"><span>Fund</span><span>Net asset value</span><span>Approach</span><span>Agents</span><span>Status</span><span/></div>{visible.map(fund => <a href={`#/funds/${fund.id}/overview`} className="fund-table-row" key={fund.id}><div className="fund-cell-name"><span className={`fund-monogram ${fund.risk}`}>{fund.name[0]}</span><div><strong>{fund.name}</strong><small>{objectives[fund.objective]}</small></div></div><div className="fund-nav-value"><strong>{money(fund.metrics.nav)}</strong><small>USD · Paper capital</small></div><div><span className={`risk-label ${fund.risk}`}>{riskNames[fund.risk]}</span></div><div className="agent-count"><span>⌘</span>{fund.metrics.agents}<small>{fund.metrics.working ? 'Working' : 'Ready'}</small></div><div><span className={`status-tag ${fund.status}`}>{fund.status === 'active' ? 'Research' : fund.status}</span></div><span className="row-arrow">↗</span></a>)}{!visible.length && <div className="fund-list-empty"><h3>{query ? 'No matching funds.' : showArchived ? 'No archived funds.' : 'Your next fund starts here.'}</h3><p>{query ? 'Try another name.' : 'Give it a goal, set its boundaries, and build a dedicated agent team.'}</p>{!query && !showArchived && <button className="primary" onClick={() => setSetup('new')}>Create your first fund</button>}</div>}</div>
      {!showArchived && <button className="new-fund-banner" onClick={() => setSetup('new')}><span className="new-icon">＋</span><span><strong>A different goal deserves its own fund.</strong><small>Create a separate mandate, agent team, and research workspace.</small></span><span>New fund ↗</span></button>}<footer className="home-footer"><span>All demo accounts collaborate in this workspace.</span><span>Historical & paper-trading experiment. Not financial advice.</span></footer></div>}
    </main>{setup && <FundSetup initial={setup === 'edit' && selected ? selected : undefined} onClose={() => setSetup(null)} onSave={save}/>}</div>
}
