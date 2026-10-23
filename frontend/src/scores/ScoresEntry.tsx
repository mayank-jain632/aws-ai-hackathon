import { useEffect, useState } from 'react'
import { api } from '../funds/types'
import { ScoreRing } from './ScoreRing'
import { ScoresView } from './ScoresView'
import type { Scorecard } from './types'
import './scores.css'

// Mounted once from FundOverview. Everything else for the view lives in this folder.
export function ScoresEntry({ fund }: { fund: { id: string } }) {
  const [card, setCard] = useState<Scorecard | null>(null)
  const [strategy, setStrategy] = useState('')
  const [open, setOpen] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  useEffect(() => {
    let active = true
    const query = strategy ? `?strategy_id=${encodeURIComponent(strategy)}` : ''
    api<Scorecard>(`/api/funds/${fund.id}/scores${query}`)
      .then(data => { if (active) { setCard(data); setError('') } })
      .catch(problem => { if (active) setError(problem instanceof Error ? problem.message : 'Could not load scores.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [fund.id, strategy, version])
  const refresh = () => { setLoading(true); setVersion(value => value + 1) }
  const produced = card?.scores.filter(s => s.status === 'scored').length ?? 0
  return <section className="fund-panel scores-entry">
    <header><div><h3>Scores and reasoning</h3><p>{card ? `${produced} of ${card.scores.length} scores produced · click a ring for its factors, agents, reasoning and sources` : error || 'Loading scores…'}</p></div><button className="secondary" disabled={!card} onClick={() => setOpen(card?.scores[0]?.key ?? 'mandate_fit')}>Open scores</button></header>
    {card && <div className="ring-row compact">{card.scores.map(s => <ScoreRing key={s.key} score={s} size={58} onSelect={() => setOpen(s.key)}/>)}</div>}
    {card && open && <ScoresView card={card} initial={open} loading={loading} onClose={() => setOpen('')} onRefresh={refresh} onStrategy={id => { setLoading(true); setStrategy(id) }}/>}
  </section>
}
