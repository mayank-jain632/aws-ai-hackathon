import { useEffect, useState } from 'react'

export function ShareFundButton({ fundId, name, view = 'overview' }: { fundId: string; name: string; view?: string }) {
  const [copied, setCopied] = useState(false)
  const [fallback, setFallback] = useState('')
  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 2200)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function copy() {
    const url = new URL(window.location.href)
    url.search = ''
    url.hash = `/funds/${encodeURIComponent(fundId)}/${view === 'agents' ? 'agents' : 'overview'}`
    try {
      await navigator.clipboard.writeText(url.href)
      setFallback('')
      setCopied(true)
    } catch {
      setFallback(url.href)
    }
  }

  return <div className="fund-share">
    <button type="button" className="secondary share-button" aria-label={`Share ${name}`} title="Copy fund link" onClick={() => void copy()}>
      <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><path d="m10 13 4-4m-5 8-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m0 8a4 4 0 0 0 6 0l4-4a4 4 0 0 0-6-6l-1 1" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
      {copied ? 'Copied' : 'Share'}
    </button>
    <span className="screen-reader-only" role="status">{copied ? `Link to ${name} copied. Teammates can sign in to collaborate.` : ''}</span>
    {fallback && <div className="share-fallback"><label>Copy fund link<input readOnly autoFocus value={fallback} onFocus={event => event.currentTarget.select()}/></label><button className="text-button" onClick={() => setFallback('')}>Close</button></div>}
  </div>
}
