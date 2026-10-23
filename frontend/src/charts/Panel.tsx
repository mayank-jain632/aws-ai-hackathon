import type { ReactNode } from 'react'

export interface PanelProps { title: string; subtitle: string; tag?: string; wide?: boolean; note?: string; children: ReactNode }

export function Panel({ title, subtitle, tag, wide, note, children }: PanelProps) {
  return <section className={`fund-panel chart-panel${wide ? ' wide' : ''}`}>
    <header><div><h3>{title}</h3><p>{subtitle}</p></div>{tag && <span className="subtle-tag">{tag}</span>}</header>
    {children}
    {note && <p className="chart-note">{note}</p>}
  </section>
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="chart-empty">{children}</div>
}
