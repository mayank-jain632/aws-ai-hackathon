import { useEffect, useRef, useState, type FormEvent } from 'react'
import { setupMandate, objectives, riskNames, money, type Mandate } from './types'

type Props = { initial?: Mandate; onClose: () => void; onSave: (mandate: Mandate) => Promise<void> }
export function FundSetup({ initial, onClose, onSave }: Props) {
  const [value, setValue] = useState<Mandate>(() => setupMandate(initial))
  const dialog = useRef<HTMLElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    return () => previous?.focus()
  }, [])
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [symbols, setSymbols] = useState(value.universe.join(', '))
  const change = <K extends keyof Mandate>(key: K, next: Mandate[K]) => setValue(v => ({ ...v, [key]: next }))
  function preset(risk: Mandate['risk']) {
    setValue(v => ({ ...v, risk, objective: risk === 'conservative' ? 'capital_preservation' : risk === 'aggressive' ? 'long_term_growth' : 'balanced_growth', max_drawdown: risk === 'conservative' ? 8 : risk === 'aggressive' ? 25 : 15, max_position: risk === 'conservative' ? 10 : risk === 'aggressive' ? 25 : 20, min_cash: risk === 'conservative' ? 15 : 5 }))
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    if (step < 2) { setStep(step + 1); return }
    const universe = [...new Set(symbols.split(/[\s,]+/).map(s => s.trim().toUpperCase()).filter(Boolean))]
    if (!universe.length) { setError('Add at least one ticker in step 2.'); return }
    setBusy(true)
    try { await onSave({ ...value, universe }) } catch (e) { setError(e instanceof Error ? e.message : 'Could not save your fund.') } finally { setBusy(false) }
  }
  return <div className="setup-backdrop" onKeyDown={e => { if (e.key === 'Escape' && !busy) onClose() }}><section ref={dialog} onKeyDown={event => {
    if (event.key !== 'Tab') return
    const items = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, textarea, summary')
    if (!items?.length) return
    const first = items[0], last = items[items.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }} role="dialog" aria-modal="true" aria-labelledby="setup-title" className="setup-dialog">
    <header className="setup-heading"><div><h1 id="setup-title">{initial ? 'Fund settings' : 'Create a fund'}</h1></div><button type="button" className="quiet icon" aria-label="Close fund setup" disabled={busy} onClick={onClose}>×</button></header>
    <nav className="setup-steps" aria-label="Fund setup steps">{['Your mandate','Risk & investments','Permissions & review'].map((title,i) => <button type="button" key={title} className={step === i ? 'current' : step > i ? 'done' : ''} disabled={busy || i > step} onClick={() => setStep(i)}><span>{step > i ? '✓' : i + 1}</span>{title}</button>)}</nav>
    <form onSubmit={submit}><div className="setup-content" key={step}>
      {step === 0 && <><div className="section-intro"><h2>Investment goal</h2><p>Set the brief for your agents.</p></div>
        <label className="field">Fund name<input autoFocus required minLength={2} maxLength={80} placeholder="Fund name" value={value.name} onChange={e => change('name',e.target.value)} /></label>
        <div className="field-row"><label className="field">Starting paper capital (USD)<input type="number" min={0} max={10000000000} step={1000} required value={value.capital} onChange={e => change('capital',Number(e.target.value))}/></label><label className="field">Investment horizon<select value={value.horizon_months} onChange={e => change('horizon_months',Number(e.target.value))}><option value={6}>6 months</option><option value={12}>1 year</option><option value={36}>3 years</option><option value={60}>5 years</option><option value={120}>10 years</option></select></label></div>
        <label className="field">Primary objective<select value={value.objective} onChange={e => change('objective',e.target.value)}>{Object.entries(objectives).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <fieldset className="risk-options"><legend>Choose a starting approach</legend>{(['conservative','balanced','aggressive'] as const).map(risk => <button type="button" key={risk} aria-pressed={value.risk === risk} className={value.risk === risk ? 'chosen' : ''} onClick={() => preset(risk)}><strong>{riskNames[risk]}</strong><small>{risk === 'conservative' ? 'Lower risk' : risk === 'balanced' ? 'Moderate risk' : 'Higher risk'}</small><span className="choice-check">{value.risk === risk ? '✓' : ''}</span></button>)}</fieldset>
        <label className="field">Description <span className="optional">Optional</span><textarea rows={2} maxLength={2000} placeholder="Investment thesis, client context, or priorities…" value={value.description} onChange={e => change('description',e.target.value)} /></label>
      </>}
      {step === 1 && <><div className="section-intro"><h2>Investment limits</h2><p>These are your recorded mandate limits. You can adjust them before agents run.</p></div>
        <div className="field-row three"><label className="field">Max single position (%)<input type="number" min={1} max={100} required value={value.max_position} onChange={e => change('max_position',Number(e.target.value))}/></label><label className="field">Max drawdown (%)<input type="number" min={1} max={100} required value={value.max_drawdown} onChange={e => change('max_drawdown',Number(e.target.value))}/></label><label className="field">Cash reserve (%)<input type="number" min={0} max={100} required value={value.min_cash} onChange={e => change('min_cash',Number(e.target.value))}/></label></div>
        <label className="field">Investment universe<input required value={symbols} onChange={e => setSymbols(e.target.value)} placeholder="AAPL, MSFT, NVDA, …"/><small>Comma-separated US equity ticker symbols. Default: the team's research universe.</small></label>
        <div className="field-row"><label className="field">Rebalancing cadence<select value={value.rebalance} onChange={e => change('rebalance',e.target.value)}><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option></select></label><label className="field">Liquidity needs<select value={value.liquidity} onChange={e => change('liquidity',e.target.value)}><option value="daily">Daily access</option><option value="monthly">Monthly access</option><option value="quarterly">Quarterly access</option></select></label></div>
        <details className="advanced"><summary>More investment constraints <span>Sector exposure, return target, exclusions, leverage</span></summary><div className="field-row"><label className="field">Maximum sector exposure (%)<input type="number" min={1} max={100} value={value.max_sector} onChange={e => change('max_sector',Number(e.target.value))}/></label><label className="field">Annual return target (%) <span className="optional">Optional</span><input type="number" min={0} max={100} placeholder="No target" value={value.target_return ?? ''} onChange={e => change('target_return',e.target.value === '' ? null : Number(e.target.value))}/><small>A goal, never a forecast or guarantee.</small></label></div><label className="field">Exclusions<input placeholder="e.g. no tobacco, no energy, no small caps" value={value.exclusions} maxLength={500} onChange={e => change('exclusions',e.target.value)}/></label><div className="field-row"><label className="check-field"><input type="checkbox" checked={value.allow_short} onChange={e => change('allow_short',e.target.checked)}/>Allow short positions in the mandate</label><label className="field">Maximum leverage<select value={value.max_leverage} onChange={e => change('max_leverage',Number(e.target.value))}><option value={1}>1× · no leverage</option><option value={1.5}>1.5×</option><option value={2}>2×</option></select></label></div></details>
      </>}
      {step === 2 && <><div className="section-intro"><h2>Review fund</h2><p>Review the mandate and choose how this fund should work.</p></div>
        <div className="review-strip"><div><small>Fund</small><strong>{value.name}</strong></div><div><small>Paper capital</small><strong>{money(value.capital)}</strong></div><div><small>Approach</small><strong>{riskNames[value.risk]}</strong></div></div>
        <div className="field-row"><label className="field">Research mode<select value={value.mode} onChange={e => change('mode',e.target.value)}><option value="paper">Live paper research</option><option value="historical">Historical research</option></select></label><label className="field">Historical research cutoff<input type="date" disabled={value.mode !== 'historical'} required={value.mode === 'historical'} value={value.cutoff} onChange={e => change('cutoff',e.target.value)}/><small>{value.mode === 'historical' ? 'Use evidence available by this date. Benchmark: SPY.' : 'Inactive for live research. Historical backtests use their own evaluation dates.'}</small></label></div>
        <div className="permission-box"><label className="toggle-row"><span><strong>Permit paper trading</strong><small>Agents may place Alpaca paper orders after strategy, evaluation and risk checks pass.</small></span><input type="checkbox" checked={value.trading_allowed} onChange={e => change('trading_allowed',e.target.checked)}/></label><label className="toggle-row"><span><strong>Require human approval</strong><small>Enable to require a person’s approval before paper execution.</small></span><input type="checkbox" checked={value.approval_required} onChange={e => change('approval_required',e.target.checked)}/></label></div>
        <label className="field">Additional instructions <span className="optional">Optional</span><textarea rows={2} maxLength={2000} placeholder="Reporting requirements, investment restrictions, or approval notes…" value={value.notes} onChange={e => change('notes',e.target.value)}/></label>
        <div className="info-note">{value.mode === 'historical' ? 'Research uses the historical cutoff. Switch to live paper research to execute at current prices.' : !value.trading_allowed ? 'Live market research only. Enable paper trading to let agents execute.' : value.approval_required ? 'Agents research and evaluate strategies, then wait for your approval before paper execution.' : 'Agents research, evaluate and trade autonomously within your mandate using the Alpaca paper account.'}</div>
      </>}
      {error && <p role="alert" className="fund-error">{error}</p>}
    </div><footer className="setup-footer"><span>Step {step + 1} of 3</span><div>{step > 0 && <button type="button" className="secondary" disabled={busy} onClick={() => setStep(step - 1)}>Back</button>}<button type="submit" className="primary" disabled={busy}>{busy ? 'Saving fund…' : step < 2 ? 'Continue' : initial ? 'Save mandate' : 'Create fund'}</button></div></footer></form>
  </section></div>
}
