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

export function FundPerformance({ fund }: { fund: Fund }) {
  const [definition, setDefinition] = useState<number | null>(null)
  const opened = new Date(fund.created_at)
  return <section className="fund-performance" aria-label="Fund performance">
    <div className="performance-heading"><div><h2>Performance</h2><p>No recorded portfolio valuations yet.</p></div><span className="performance-period">Created {opened.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}</span></div>
    <details className="performance-details"><summary>Performance metrics</summary>
    <div className="performance-metrics">{definitions.map(([label], index) => <button type="button" key={label} aria-expanded={definition === index} className={definition === index ? 'explained' : ''} onClick={() => setDefinition(definition === index ? null : index)}><span>{label}</span><strong>—</strong></button>)}</div>
    {definition !== null ? <div className="metric-explanation" role="status"><strong>{definitions[definition][0]}</strong><p>{definitions[definition][1]}</p><button className="text-button" aria-label="Close metric definition" onClick={() => setDefinition(null)}>×</button></div> : null}
    </details>
  </section>
}
