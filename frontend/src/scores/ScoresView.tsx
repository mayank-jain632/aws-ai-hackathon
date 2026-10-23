import { type RefObject, useEffect, useMemo, useRef, useState } from 'react'
import { DEFINITIONS, GUIDE } from './definitions'
import { ScoreRing } from './ScoreRing'
import type { AgentRef, Factor, Scorecard, Score } from './types'

const STATUS: Record<Factor['status'], string> = { pass: 'Pass', fail: 'Fail', pending: 'Pending', info: 'Context' }
const SOURCE_STATUS = { present: 'Present', empty: 'No records yet', not_on_main: 'Not on main yet' }

function when(value: string | null) {
  if (!value) return ''
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

function Agents({ agents }: { agents: AgentRef[] }) {
  if (!agents.length) return <span className="muted-inline">No agent recorded</span>
  return <span className="agent-chips">{agents.map((a, i) => <span key={`${a.id}-${a.name}-${i}`} className={`agent-chip ${a.attribution.replace(' ', '-')}`} title={`${a.role}; ${a.attribution === 'recorded' ? 'named in the record' : a.attribution === 'role holder' ? 'holds this role in the fund; not named per record' : 'deterministic code or offline run'}`}>{a.name}<small>{a.role}</small></span>)}</span>
}

function ScoreDetail({ score, factor, onFactor }: { score: Score; factor: string; onFactor: (key: string) => void }) {
  return <section className="fund-panel score-detail">
    <header><div><h3>{score.label}</h3><p>{score.question}</p></div><span className="subtle-tag">{score.status === 'scored' ? (score.scope === 'firm' ? 'Frozen team run, not this fund' : 'This fund') : 'Not produced yet'}</span></header>
    {DEFINITIONS[score.key] && <p className="score-definition"><strong>What this score means.</strong> {DEFINITIONS[score.key]}</p>}
    {score.status === 'scored' ? <dl className="fact-list score-facts">
      <div><dt>Score</dt><dd><strong>{score.value} / 100</strong></dd></div>
      <div><dt>Raw metric</dt><dd>{score.raw}</dd></div>
      <div><dt>Formula</dt><dd>{score.formula}</dd></div>
      <div><dt>Source</dt><dd>{score.source?.label} <code>{score.source?.location}</code></dd></div>
      <div><dt>Owner</dt><dd>{score.owner}</dd></div>
      <div><dt>Contributing agents</dt><dd><Agents agents={score.contributors}/></dd></div>
    </dl> : <dl className="fact-list score-facts">
      <div><dt>Status</dt><dd>Not produced yet. No number is shown until a lane records one.</dd></div>
      <div><dt>What is missing</dt><dd>{score.missing}</dd></div>
      <div><dt>Owner</dt><dd>{score.owner}</dd></div>
    </dl>}
    {score.factors.length > 0 && <div className="factor-table" role="list">
      <div className="factor-row factor-head" aria-hidden="true"><span>Factor (click a row for reasoning and sources)</span><span>Value</span><span>Weight</span><span>Result</span><span>Produced by</span></div>
      {score.factors.map(f => <button type="button" role="listitem" key={f.key} className={`factor-row${factor === f.key ? ' selected' : ''}`} onClick={() => onFactor(f.key)}>
        <span>{f.label}</span><span>{f.value}</span><span>{f.weight === null ? 'Context' : `${Math.round(f.weight * 100)}%`}</span>
        <span className={`factor-status ${f.status}`}>{f.status === 'info' && f.weight !== null ? 'Weighted' : STATUS[f.status]}</span><span>{f.agents.length ? f.agents[0].name + (f.agents.length > 1 ? ` +${f.agents.length - 1} more` : '') : 'Not recorded'}</span>
      </button>)}
    </div>}
  </section>
}

// The factor shown before anyone clicks: the first with recorded reasoning, then the first with cited sources.
function firstInformative(score: Score) {
  return score.factors.find(f => f.reasoning) ?? score.factors.find(f => f.provenance.citations.length) ?? score.factors[0]
}

function FactorDetail({ factor, panel }: { factor: Factor | undefined; panel: RefObject<HTMLElement | null> }) {
  if (!factor) return <section className="fund-panel factor-detail" ref={panel}><header><div><h3>Reasoning and provenance</h3><p>This score is not produced yet, so there is no reasoning or source to show. The panel on the left says what is missing and which lane owns it.</p></div></header></section>
  const p = factor.provenance
  return <section className="fund-panel factor-detail" ref={panel}>
    <header><div><p className="muted reasoning-kicker">Reasoning and provenance</p><h3>{factor.label}</h3><p>{factor.value}</p></div><span className={`factor-status ${factor.status}`}>{STATUS[factor.status]}</span></header>
    <div className="factor-body">
      {factor.detail && <p className="factor-detail-text"><strong>What was looked at.</strong> {factor.detail}</p>}
      <h4>Produced by</h4><Agents agents={factor.agents}/>
      <h4>{factor.reasoning_label}</h4>
      {factor.reasoning ? <pre className="reasoning-text">{factor.reasoning}</pre> : <p className="muted-inline">No reasoning text was recorded for this factor.</p>}
      <h4>Provenance</h4>
      <dl className="fact-list provenance-list">
        <div><dt>Record</dt><dd><code>{p.record}</code></dd></div>
        {p.file && <div><dt>File</dt><dd><code>{p.file}</code></dd></div>}
        {p.time && <div><dt>Produced</dt><dd>{when(p.time)}</dd></div>}
      </dl>
      <h4>Cited sources ({p.citations.length})</h4>
      {p.citations.length ? <ol className="citation-list">{p.citations.map((c, i) => <li key={`${c.id}-${i}`}>
        <div><span className="subtle-tag">{c.kind}</span> <strong>{c.title}</strong>{c.date && <span className="muted-inline"> · {c.date}</span>}</div>
        {c.url && <a href={c.url} target="_blank" rel="noreferrer">{c.url}</a>}
        {c.excerpt && <p>{c.excerpt}</p>}
      </li>)}</ol> : <p className="muted-inline">No sources are cited in this record.</p>}
    </div>
  </section>
}

export function ScoresView({ card, initial, onClose, onStrategy, onRefresh, loading }: { card: Scorecard; initial: string; onClose: () => void; onStrategy: (id: string) => void; onRefresh: () => void; loading: boolean }) {
  const [selected, setSelected] = useState(initial)
  const [factor, setFactor] = useState('')
  const panel = useRef<HTMLElement>(null)
  const score = [...card.scores, ...card.team].find(s => s.key === selected) ?? card.scores[0]
  const active = score.factors.find(f => f.key === factor) ?? firstInformative(score)
  const tools = useMemo(() => Object.entries(card.inputs.reduce<Record<string, number>>((all, call) => ({ ...all, [call.tool]: (all[call.tool] ?? 0) + 1 }), {})).sort((a, b) => b[1] - a[1]), [card.inputs])
  useEffect(() => { const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close) }, [onClose])
  const produced = card.scores.filter(s => s.status === 'scored').length
  return <div className="scores-overlay" role="dialog" aria-modal="true" aria-label="Scores and reasoning">
    <div className="scores-sheet">
      <header className="scores-head">
        <div><p className="muted">Scores and reasoning · {produced} of {card.scores.length} produced</p><h2>{card.fund_name}</h2>
          <p className="scores-strategy">{card.strategy ? <>Strategy <strong>{card.strategy.name}</strong> registered {when(card.strategy.created_at)} · test window {card.strategy.cutoff} to {card.strategy.end} · {Object.entries(card.strategy.weights).map(([t, w]) => `${t} ${(w * 100).toFixed(0)}%`).join(', ')}</> : 'No strategy registered in this fund yet.'}</p></div>
        <div className="scores-actions">
          {card.strategies.length > 1 && <select aria-label="Strategy" value={card.strategy?.id ?? ''} onChange={event => onStrategy(event.target.value)}>{card.strategies.map(s => <option key={s.id} value={s.id}>{s.name}{s.verdict ? ` (${s.verdict})` : ''}</option>)}</select>}
          <button className="secondary" onClick={onRefresh} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button>
          <button className="primary" onClick={onClose}>Close</button>
        </div>
      </header>
      <p className="scores-note">Each ring shows its raw metric, the formula that maps it to 0 to 100, and the record it was read from. Reasoning is the text each agent recorded, not the model's hidden chain of thought. A ring with no data says so and names the lane that owns it.{card.notes.map(n => ` ${n}`)}</p>
      <details className="scores-guide"><summary>How to read this view</summary><ul>{GUIDE.map(line => <li key={line}>{line}</li>)}</ul></details>
      <div className="ring-row">{card.scores.map(s => <ScoreRing key={s.key} score={s} selected={s.key === score.key} onSelect={() => { setSelected(s.key); setFactor('') }}/>)}</div>
      {card.team.length > 0 && <section className="team-panel" aria-label={card.team_title}>
        <h3>{card.team_title}</h3><p className="scores-note">{card.team_note}</p>
        <div className="ring-row team-rings">{card.team.map(s => <ScoreRing key={s.key} score={s} selected={s.key === score.key} onSelect={() => { setSelected(s.key); setFactor('') }}/>)}</div>
      </section>}
      <div className="scores-detail">
        <ScoreDetail score={score} factor={active?.key ?? ''} onFactor={key => { setFactor(key); if (panel.current && panel.current.getBoundingClientRect().top > window.innerHeight * 0.6) panel.current.scrollIntoView({ block: 'start' }) }}/>
        <FactorDetail factor={active} panel={panel}/>
      </div>
      <div className="scores-detail">
        <section className="fund-panel"><header><div><h3>Where the data comes from</h3><p>Every record this view reads, and whether it exists yet</p></div></header>
          <div className="source-table">{card.sources.map(s => <div key={s.id} className="source-row"><span><strong>{s.label}</strong><small>{s.owner}</small></span><span className={`source-status ${s.status}`}>{SOURCE_STATUS[s.status]}</span><span>{s.detail}<small><code>{s.location}</code></small></span></div>)}</div>
        </section>
        <section className="fund-panel"><header><div><h3>Inputs the agents used</h3><p>{card.inputs.length} tool calls from this fund's agent activity logs</p></div></header>
          {tools.length ? <div className="tool-counts">{tools.map(([tool, count]) => <span key={tool} className="subtle-tag">{tool} × {count}</span>)}</div> : <p className="empty-text inputs-empty">No agent in this fund has called a tool yet.</p>}
          <div className="input-list">{card.inputs.slice(-40).reverse().map((call, i) => <div key={`${call.time}-${i}`} className="input-row"><time>{when(call.time)}</time><span>{call.agent.name}<small>{call.agent.role}</small></span><strong>{call.tool}</strong><span className="input-summary">{call.summary}</span></div>)}</div>
        </section>
      </div>
      <p className="scores-generated muted">Generated {when(card.generated_at)} · read-only · <code>GET /api/funds/{card.fund_id}/scores</code></p>
    </div>
  </div>
}
