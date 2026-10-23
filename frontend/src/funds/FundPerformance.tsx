import { useState } from 'react'
import type { Fund } from './types'

const definitions = [
  ['Annualized return', 'The compounded annual growth rate over the recorded portfolio period. It requires a dated portfolio value history.'],
  ['Sharpe ratio', 'Return above the stated risk-free rate, divided by return volatility. Not calculated until a sufficient return series and risk-free assumption are recorded.'],
  ['Volatility', 'The annualized standard deviation of recorded portfolio returns. Not available from a starting balance alone.'],
  ['Max drawdown', 'The largest peak-to-trough decline in the recorded portfolio value history. This is an observed metric, separate from your mandate limit.'],
  ['Sortino ratio', 'Return above the stated target, divided by downside deviation. Requires a recorded return series and a stated target.'],
  ['S&P 500 correlation', 'The correlation between dated portfolio returns and benchmark returns over the same window. Requires both recorded series.'],
]
const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

export function FundPerformance({ fund }: { fund: Fund }) {
  const [definition, setDefinition] = useState<number | null>(null)
  const opened = new Date(fund.created_at)
  return <section className="fund-performance" aria-label="Fund performance">
    <div className="performance-heading"><div><h2>{fund.name}</h2><p>Growth of $100, net</p></div><span className="performance-period">Since inception <span>{opened.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}</span></span></div>
    <div className="performance-plot"><svg viewBox="0 0 1080 270" preserveAspectRatio="none" aria-hidden="true"><path d="M45 18V245H1055" fill="none" stroke="var(--fund-line)" strokeWidth="1"/><path d="M40 245H50" stroke="var(--fund-line)"/><circle cx="45" cy="245" r="3.5" fill="var(--fund-accent)"/></svg><span className="plot-baseline">100</span><div className="performance-empty"><span className="plot-seal">F</span><h3>Awaiting the first recorded valuation.</h3><p>Your starting capital is recorded. Portfolio performance will appear here<br className="desktop-break"/> when dated valuations and executions are connected.</p><span className="empty-caption">No market performance recorded</span></div><div className="plot-return"><strong>—</strong><span>Cumulative return, net</span></div></div>
    <div className="performance-caption"><span>Inception balance only. No historical returns have been generated.</span><span>USD · Paper portfolio</span></div>
    <div className="performance-metrics">{definitions.map(([label], index) => <button type="button" key={label} aria-expanded={definition === index} className={definition === index ? 'explained' : ''} onClick={() => setDefinition(definition === index ? null : index)}><span>{label}</span><strong>—</strong></button>)}</div>
    {definition !== null ? <div className="metric-explanation" role="status"><strong>{definitions[definition][0]}</strong><p>{definitions[definition][1]}</p><button className="text-button" aria-label="Close metric definition" onClick={() => setDefinition(null)}>×</button></div> : <p className="metric-help">Select a metric for its definition and methodology</p>}
    <div className="monthly-returns"><table><caption>Monthly returns, net <span>Recorded performance only</span></caption><thead><tr><th scope="col">Year</th>{months.map(month=><th scope="col" key={month}>{month}</th>)}<th scope="col">Total</th></tr></thead><tbody><tr><th scope="row">{opened.getFullYear()}</th>{months.map(month=><td key={month}>—</td>)}<td>—</td></tr></tbody></table><p>A dash means no recorded return for that period.</p></div>
  </section>
}
