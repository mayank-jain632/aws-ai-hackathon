import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Canvas } from './board/Canvas'
import type { Agent, BoardPositions, Position } from './types'
import './App.css'

type Tab = 'chat' | 'activity' | 'files'

async function request(path: string, options?: RequestInit) {
  const response = await fetch(path, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not reach the backend.')
  }
  return response.json()
}

export default function AgentWorkspace({ fundId, fundName }: { fundId: string; fundName: string }) {
  const base = `/api/funds/${fundId}`
  const [positions, setPositions] = useState<BoardPositions>({})
  const [viewers, setViewers] = useState(0)
  const [identity, setIdentity] = useState({ email: 'local', hosted: false })
  const lastLayoutWrite = useRef(0)
  const writes = useRef<Promise<unknown>>(Promise.resolve())
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedId, setSelectedId] = useState('dexter')
  const agent = agents.find(item => item.id === selectedId) || null
  const [connected, setConnected] = useState(false)
  const [selected, setSelected] = useState(true)
  const [tab, setTab] = useState<Tab>('chat')
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [file, setFile] = useState<{ path: string; content: string } | null>(null)
  const fileRequest = useRef(0)
  const bottom = useRef<HTMLDivElement>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)
  const running = agent?.status === 'running'

  useEffect(() => {
    void request('/api/me').then(setIdentity).catch(() => {})
    const stream = new EventSource(`${base}/events`)
    stream.onmessage = event => { const board = JSON.parse(event.data); setAgents(board.agents); setPositions(board.positions || {}); setViewers(board.viewers || 1); setConnected(true) }
    stream.onerror = () => { setConnected(false); void fetch('/api/me').then(response => { if (response.status === 401) window.location.assign('/login') }).catch(() => {}) }
    return () => stream.close()
  }, [base])

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'instant', block: 'end' }) }, [agent?.messages.length, tab])

  async function send(event: FormEvent) {
    event.preventDefault()
    if (!draft.trim() || running || sending) return
    setSending(true); setError('')
    try {
      await request(`${base}/agents/${selectedId}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: draft }) })
      setDraft('')
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not send your message.') }
    finally { setSending(false) }
  }

  async function changeModel(model: string) {
    setSending(true); setError('')
    try {
      const updated: Agent = await request(`${base}/agents/${selectedId}/model`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model }) })
      setAgents(previous => previous.map(item => item.id === updated.id ? updated : item))
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not change the model.') }
    finally { setSending(false) }
  }

  async function stop() {
    setError('')
    try { setAgents((await request(`${base}/agents/${selectedId}/stop`, { method: 'POST' })).agents) }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not stop the agent.') }
  }

  async function openFile(path: string) {
    const current = ++fileRequest.current
    setError('')
    try {
      const next = await request(`${base}/agents/${selectedId}/file?path=${encodeURIComponent(path)}`)
      if (current === fileRequest.current) setFile(next)
    } catch (e) { if (current === fileRequest.current) setError(e instanceof Error ? e.message : 'Could not open the file.') }
  }

  function writeLayout(body: object) {
    writes.current = writes.current.catch(() => {}).then(() => request(`${base}/board/layout`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).catch(() => setError('Could not sync the canvas. Check your connection.'))
  }

  function moveAgent(id: string, position: Position, final: boolean) {
    setPositions(previous => ({ ...previous, [id]: position }))
    if (!final && Date.now() - lastLayoutWrite.current < 100) return
    lastLayoutWrite.current = Date.now()
    writeLayout({ agent_id: id, position })
  }

  const lastError = agent?.status === 'error' ? [...agent.activity].reverse().find(item => item.kind === 'error') : null

  return (
    <main className="app">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">⌘</span><div><strong>Agent canvas</strong><span>{fundName}</span></div></div>
        <div className="connection"><i className={connected ? 'online' : ''} />{connected ? `Shared board · ${viewers} online` : 'Reconnecting…'}{identity.hosted ? <><span style={{ marginLeft: 12 }}>{identity.email.split('@')[0]}</span><a href="/logout" style={{ marginLeft: 12, color: 'inherit' }}>Sign out</a></> : null}</div>
      </header>
      <div className="workspace">
        <Canvas positions={positions} onPosition={moveAgent} onReset={() => { setPositions({}); writeLayout({ reset: true }) }} agents={agents} connected={connected} selectedId={selected ? selectedId : null} onSelect={id => {
          setSelectedId(id); setSelected(true); setFile(null); fileRequest.current++; setError(''); setTab('chat')
        }} onDeselect={() => setSelected(false)} />
        {selected ? (
          <aside className="agent-panel" aria-label={`${agent?.name || 'Agent'} details`}>
            <div className="panel-heading"><div className="avatar">{agent?.name[0] || 'D'}</div><div className="panel-title"><h1>{agent?.name || 'Dexter'}</h1><p>{running ? 'Working on your request' : agent?.parentId ? `Subagent of ${agents.find(item => item.id === agent.parentId)?.name || 'Dexter'}` : 'Main agent'}</p></div><button className="icon-button close" aria-label="Close agent details" onClick={() => setSelected(false)}>×</button></div>
            <div className="model-row"><span className={`state ${agent?.status || 'idle'}`}>{running ? 'Working' : agent?.status === 'error' ? 'Needs attention' : agent?.status === 'stopped' ? 'Stopped' : 'Ready'}</span><select aria-label="Agent model" value={agent?.model || ''} disabled={!agent || running || sending || agent.role === 'backtester'} onChange={event => void changeModel(event.target.value)}>{agent?.modelChoices?.map(model => <option key={model.id} value={model.id}>{model.name}{agent.role === 'backtester' ? ' · fixed' : ''}</option>)}</select></div>
            <div className="tabs" role="tablist" aria-label="Agent details">
              {(['chat', 'activity', 'files'] as const).map(name => <button key={name} id={`tab-${name}`} role="tab" aria-selected={tab === name} aria-controls="agent-content" onClick={() => setTab(name)}>{name[0].toUpperCase() + name.slice(1)}{name === 'files' && agent?.files.length ? <span className="count">{agent.files.length}</span> : null}</button>)}
            </div>
            <div id="agent-content" className="panel-content" role="tabpanel" aria-labelledby={`tab-${tab}`}>
              {tab === 'chat' ? <>
                {!agent?.messages.length ? <div className="empty-chat"><div className="empty-icon">✳</div><h2>What are we working on?</h2><p>Give this agent a task. It can work with shared files or create its own subagents.</p><button className="suggestion" onClick={() => { setDraft('Create a researcher agent named Scout. Ask it to write a short introduction in hello.txt, read it back, and report the result.'); textarea.current?.focus() }}>Create a researcher agent <span>↗</span></button></div> : agent.messages.map(message => <div key={message.id} className={`message ${message.role}`}><span className="message-author">{message.role === 'user' ? message.source || 'You' : agent?.name}</span><div>{message.text}</div></div>)}
                {running ? <div className="working" role="status"><span className="pulse" />{agent?.name} is working… <button onClick={() => setTab('activity')}>View activity</button></div> : null}
                {lastError ? <div className="error-box" role="alert"><strong>The run couldn’t finish</strong><p>{lastError.detail}</p><small>If the workshop token expired, refresh your dedicated AWS credentials and send the message again.</small></div> : null}
                <div ref={bottom} />
              </> : null}
              {tab === 'activity' ? <div className="activity-list">{!agent?.activity.length ? <p className="empty-text">Tool calls and run activity will appear here.</p> : agent.activity.map(item => <details key={item.id} className={`activity-item ${item.kind}`}><summary><i /><span>{item.label}</span><time>{new Date(item.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></summary>{item.detail ? <pre>{item.detail}</pre> : <p>No additional details.</p>}</details>)}</div> : null}
              {tab === 'files' ? <div className="files"><p className="workspace-path">{agent?.workspace || '.local/workspace'}</p>{file ? <><button className="back-link" onClick={() => { fileRequest.current++; setFile(null) }}>‹ All files</button><h2 className="file-title">{file.path}</h2><pre className="file-preview">{file.content}</pre></> : !agent?.files.length ? <p className="empty-text">No files yet. Ask Dexter to create one.</p> : agent.files.map(path => <button className="file-row" key={path} onClick={() => void openFile(path)}><span>▤</span>{path}<span>↗</span></button>)}</div> : null}
            </div>
            {error ? <p className="request-error" role="alert">{error}</p> : null}
            <form className="composer" onSubmit={send}>
              <textarea ref={textarea} aria-label={`Message ${agent?.name || 'agent'}`} placeholder={`Give ${agent?.name || 'the agent'} a task…`} value={draft} maxLength={12000} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(event) } }} />
              <div className="composer-footer"><span>Shared workspace for all agents</span>{running ? <button type="button" className="stop-button" onClick={() => void stop()}>■ Stop</button> : <button className="send-button" aria-label="Send message" disabled={!draft.trim() || !connected || sending}>↑</button>}</div>
            </form>
          </aside>
        ) : null}
      </div>
    </main>
  )
}
