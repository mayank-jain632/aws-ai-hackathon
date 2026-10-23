import type { Score } from './types'

const RADIUS = 30
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function ScoreRing({ score, selected, onSelect, size = 76 }: { score: Score; selected?: boolean; onSelect?: () => void; size?: number }) {
  const produced = score.status === 'scored' && score.value !== null
  const filled = produced ? (CIRCUMFERENCE * (score.value ?? 0)) / 100 : 0
  return <button type="button" className={`score-ring${selected ? ' selected' : ''}${produced ? '' : ' absent'}`} onClick={onSelect} aria-pressed={selected} title={produced ? `${score.label}: ${score.value} of 100. ${score.raw}` : `${score.label}: not produced yet`}>
    <svg width={size} height={size} viewBox="0 0 76 76" aria-hidden="true">
      <circle cx="38" cy="38" r={RADIUS} className="ring-track"/>
      {produced && <circle cx="38" cy="38" r={RADIUS} className="ring-value" strokeDasharray={`${filled} ${CIRCUMFERENCE}`} transform="rotate(-90 38 38)"/>}
      <text x="38" y="38" textAnchor="middle" dominantBaseline="central" className={produced ? 'ring-number' : 'ring-dash'}>{produced ? Math.round(score.value ?? 0) : '?'}</text>
    </svg>
    <span className="ring-label">{score.label}</span>
    <span className="ring-sub">{produced ? (score.scope === 'firm' ? 'Firm-wide walk-forward' : 'This fund') : 'Not produced yet'}</span>
  </button>
}
