import { useState } from 'react'
import { createPortal } from 'react-dom'
import { ShareFundDialog } from './ShareFundDialog'

export function ShareFundButton({ fundId, name, view = 'overview' }: { fundId: string; name: string; view?: string }) {
  const [open, setOpen] = useState(false)
  return <div className="fund-share">
    <button type="button" className="secondary share-button" aria-label={`Share ${name}`} aria-haspopup="dialog" onClick={() => setOpen(true)}>
      <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><path d="m10 13 4-4m-5 8-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m0 8a4 4 0 0 0 6 0l4-4a4 4 0 0 0-6-6l-1 1" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
      Share
    </button>
    {open && createPortal(<ShareFundDialog fundId={fundId} name={name} view={view} onClose={() => setOpen(false)}/>, document.body)}
  </div>
}
