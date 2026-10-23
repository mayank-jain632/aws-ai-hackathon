import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { api, json } from './types'

type Member = { email: string; role: 'owner' | 'editor'; status: 'active' | 'invited' }
type Access = { members: Member[]; you: string }

export function ShareFundDialog({ fundId, name, view, onClose }: { fundId: string; name: string; view: string; onClose: () => void }) {
  const titleId = useId()
  const [access, setAccess] = useState<Access | null>(null)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [invitation, setInvitation] = useState('')
  const [copied, setCopied] = useState('')
  const dialog = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const invitationInput = useRef<HTMLInputElement>(null)
  const fundInput = useRef<HTMLInputElement>(null)
  const loaded = access !== null
  const endpoint = `/api/funds/${fundId}/members`
  const fundLink = new URL(`${window.location.pathname}#/funds/${encodeURIComponent(fundId)}/${view === 'agents' ? 'agents' : 'overview'}`, window.location.origin).href
  const owner = access?.members.some(member => member.email === access.you && member.role === 'owner')

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    input.current?.focus()
    const controller = new AbortController()
    void api<Access>(endpoint, { signal: controller.signal }).then(setAccess).catch(problem => { if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : 'Could not load sharing.') })
    return () => { controller.abort(); previous?.focus() }
  }, [endpoint])

  useEffect(() => { if (loaded) input.current?.focus() }, [loaded])

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(''), 2200)
    return () => clearTimeout(timer)
  }, [copied])

  async function invite(event: FormEvent) {
    event.preventDefault()
    if (busy || !email.trim()) return
    setBusy(true); setError(''); setNotice(''); setInvitation('')
    const invited = email.trim().toLowerCase()
    try {
      const result = await api<{ members: Member[]; invitation_path: string | null }>(endpoint, json('POST', { email: invited }))
      setAccess(previous => ({ members: result.members, you: previous?.you || '' }))
      setEmail('')
      if (result.invitation_path) {
        setInvitation(new URL(result.invitation_path, window.location.origin).href)
        setNotice(`${invited} has been invited. Send them the invitation link to set up their account.`)
      } else setNotice(`${invited} now has access. This fund is on their dashboard.`)
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not share this fund.') }
    finally { setBusy(false) }
  }

  async function remove(email: string) {
    setBusy(true); setError(''); setNotice(''); setInvitation('')
    try {
      setAccess(await api<Access>(`${endpoint}/${encodeURIComponent(email)}`, { method: 'DELETE' }))
      setNotice(`Access removed for ${email}.`)
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not remove access.') }
    finally { setBusy(false) }
  }

  async function copy(value: string, label: string) {
    try { await navigator.clipboard.writeText(value); setCopied(label) }
    catch { const target = label === 'invitation' ? invitationInput : fundInput; target.current?.focus(); target.current?.select(); setNotice('Select and copy the link below.') }
  }

  return <div className="share-backdrop" onPointerDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <div className="share-dialog" ref={dialog} role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={event => {
      if (event.key === 'Escape' && !busy) { event.stopPropagation(); onClose() }
      if (event.key !== 'Tab') return
      const items = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), a[href]')
      if (!items?.length) return
      const first = items[0], last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }}>
      <header><div><h2 id={titleId}>Share {name}</h2><p>Invite a teammate to collaborate on this fund.</p></div><button type="button" className="share-close" disabled={busy} onClick={onClose} aria-label="Close sharing">×</button></header>
      <form className="share-invite" onSubmit={event => void invite(event)}><label htmlFor={`${titleId}-email`} className="screen-reader-only">Teammate email</label><input ref={input} id={`${titleId}-email`} type="email" required maxLength={254} placeholder="Email address" autoComplete="off" value={email} onChange={event => setEmail(event.target.value)} disabled={busy || !access}/><button type="submit" className="primary" disabled={busy || !email.trim() || !access}>{busy ? 'Sharing…' : 'Invite'}</button></form>
      {error && <p className="share-error" role="alert">{error}</p>}
      {notice && <p className="share-notice" role="status">{notice}</p>}
      {invitation && <div className="share-invitation"><label>Invitation link<input ref={invitationInput} readOnly value={invitation} onFocus={event => event.currentTarget.select()}/></label><button type="button" className="secondary" onClick={() => void copy(invitation, 'invitation')}>{copied === 'invitation' ? 'Copied' : 'Copy invitation link'}</button><small>Expires in 7 days. No email is sent automatically.</small></div>}
      <h3>People with access</h3>
      {!access && !error && <p className="share-loading">Loading people…</p>}
      <ul className="share-members">{access?.members.map(member => <li key={member.email}><div><strong>{member.email}{member.email === access.you ? ' (you)' : ''}</strong><span>{member.status === 'invited' ? 'Invited' : member.role === 'owner' ? 'Owner' : 'Can edit'}</span></div>{owner && member.role !== 'owner' && <button type="button" className="share-remove" aria-label={`Remove access for ${member.email}`} disabled={busy} onClick={() => void remove(member.email)}>Remove</button>}</li>)}</ul>
      <footer><p>Only people listed here can access this fund.</p><div><input ref={fundInput} aria-label="Fund link" readOnly value={fundLink} onFocus={event => event.currentTarget.select()}/><button type="button" className="secondary" onClick={() => void copy(fundLink, 'fund')}>{copied === 'fund' ? 'Copied' : 'Copy fund link'}</button></div></footer>
    </div>
  </div>
}
