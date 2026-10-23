import { useState } from 'react'
import { api, json, type Fund, type FundScheduleState } from './types'

export function FundSchedule({ fund }: { fund: Fund }) {
  const [schedule, setSchedule] = useState(fund.schedule)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const enabled = !!schedule?.enabled
  async function toggle() {
    setSaving(true); setError('')
    try {
      setSchedule(await api<FundScheduleState>(`/api/funds/${fund.id}/schedule`, json('PUT', { enabled: !enabled })))
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not change schedule.') }
    finally { setSaving(false) }
  }
  return <section className="fund-schedule" aria-label="Hourly agent wakeups">
    <div><strong>Hourly wakeups <span className="muted">{enabled ? 'On' : 'Off'}</span></strong>
      <p>{enabled && schedule?.next_run_at ? `Next check ${new Date(schedule.next_run_at).toLocaleString()}. Active agent work is left running.` : 'Resume the saved Dexter every hour while this fund is active.'}</p>
      {schedule?.last_result && <p>{schedule.last_result}</p>}
      <p>Pausing the fund or stopping Dexter turns this off. Enabling it does not authorize trades.</p>
      {error && <p role="alert">{error}</p>}
    </div>
    <button className="secondary" disabled={saving || (!enabled && fund.status !== 'active')} onClick={toggle}>{saving ? 'Saving…' : enabled ? 'Disable wakeups' : 'Enable hourly wakeups'}</button>
  </section>
}
