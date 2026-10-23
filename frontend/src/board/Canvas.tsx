// Adapted from takehome-kushagra-bharti's SVG camera, pointer-captured gestures,
// selection, and screen-space toolbar. Agent execution is separate from layout.
import { useEffect, useRef, useState, type PointerEvent } from 'react'
import type { Agent, BoardPositions } from '../types'
import { layoutTree } from './tree'
import { agentStatus, currentTask, treeRows } from './agentView'

type Camera = { x: number; y: number; zoom: number }
type Position = { x: number; y: number }
type Gesture = { id: string | null; x: number; y: number; camera: Camera; position: Position }

export function Canvas({ agents, connected, selectedId, onSelect, onDeselect, positions, onPosition, onReset }: {
  positions: BoardPositions; onPosition: (id: string, position: Position, final: boolean) => void; onReset: () => void
  agents: Agent[]; connected: boolean; selectedId: string | null; onSelect: (id: string) => void; onDeselect: () => void
}) {
  const [view, setCamera] = useState<Camera | null>(null)
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const [viewport, setViewport] = useState({ width: window.innerWidth, height: window.innerHeight - 74 })
  const board = useRef<HTMLElement>(null)
  const navigator = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      setViewport({ width, height })
    })
    if (board.current) observer.observe(board.current)
    return () => observer.disconnect()
  }, [])
  const tree = layoutTree(agents, collapsed)
  const [dragging, setDragging] = useState<{ id: string; position: Position } | null>(null)
  const [tool, setTool] = useState<'select' | 'hand'>('select')
  const gesture = useRef<Gesture | null>(null)
  const positionRef = useRef<Position>({ x: 0, y: 0 })
  const positionFor = (id: string) => (dragging?.id === id ? dragging.position : positions[id]) || tree.positions[id] || { x: 0, y: 0 }
  const locations = tree.visible.map(agent => positionFor(agent.id))
  const minX = Math.min(...locations.map(p => p.x), 0)
  const maxX = Math.max(...locations.map(p => p.x + 300), 300)
  const minY = Math.min(...locations.map(p => p.y), 0)
  const maxY = Math.max(...locations.map(p => p.y + 170), 250)
  const zoom = Math.max(0.05, Math.min(1, (viewport.width - 60) / (maxX - minX), (viewport.height - 100) / (maxY - minY)))
  const autoView: Camera = { zoom, x: minX - (viewport.width / zoom - (maxX - minX)) / 2, y: minY - (viewport.height / zoom - (maxY - minY)) / 2 }
  const camera = view || autoView

  function toggleBranch(id: string) {
    setCollapsed(previous => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    onSelect(id)
    setCamera(null)
  }

  function pointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0 && event.button !== 1) return
    const node = (event.target as Element).closest('[data-agent]')
    const id = node?.getAttribute('data-agent') || null
    const moving = Boolean(id) && tool === 'select' && event.button === 0
    if (moving && id) { onSelect(id); positionRef.current = positionFor(id) }
    else if (tool === 'select' && event.button === 0) onDeselect()
    gesture.current = { id: moving ? id : null, x: event.clientX, y: event.clientY, camera, position: id ? positionFor(id) : { x: 0, y: 0 } }
    setCamera(camera)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function pointerMove(event: PointerEvent<SVGSVGElement>) {
    const start = gesture.current
    if (!start) return
    const dx = (event.clientX - start.x) / start.camera.zoom
    const dy = (event.clientY - start.y) / start.camera.zoom
    if (start.id) {
      const position = { x: start.position.x + dx, y: start.position.y + dy }
      positionRef.current = position
      setDragging({ id: start.id, position })
      onPosition(start.id, position, false)
    } else setCamera({ ...start.camera, x: start.camera.x - dx, y: start.camera.y - dy })
  }

  function pointerUp() {
    if (gesture.current?.id) {
      onPosition(gesture.current.id, positionRef.current, true)
    }
    gesture.current = null
    setDragging(null)
  }

  function zoomBy(factor: number) {
    setCamera({ ...camera, zoom: Math.max(0.05, Math.min(2, camera.zoom * factor)) })
  }

  function focusAgent(id: string) {
    const next = new Set(collapsed)
    const seen = new Set<string>()
    let parent = agents.find(agent => agent.id === id)?.parentId
    while (parent && !seen.has(parent)) {
      seen.add(parent); next.delete(parent)
      parent = agents.find(agent => agent.id === parent)?.parentId
    }
    const target = positions[id] || layoutTree(agents, next).positions[id]
    setCollapsed(next)
    if (target) {
      const zoom = Math.max(0.6, camera.zoom)
      setCamera({ zoom, x: target.x + 150 - viewport.width / zoom / 2, y: target.y + 85 - viewport.height / zoom / 2 })
    }
    onSelect(id)
    if (navigator.current) navigator.current.open = false
  }

  function fit(reset = false) {
    if (reset) onReset()
    setCollapsed(new Set())
    setCamera(null)
  }

  return (
    <section ref={board} className="board" aria-label="Agent tree canvas">
      <details className="tree-navigator" ref={navigator}>
        <summary>Agents <span>{agents.length}</span></summary>
        <nav aria-label="Full fund agent tree">{treeRows(agents).map(({agent, depth}) => <button key={agent.id} aria-current={selectedId === agent.id ? 'true' : undefined} style={{paddingLeft: 12 + Math.min(depth, 8) * 12}} onClick={() => focusAgent(agent.id)} title={currentTask(agent) || 'No task assigned'}>
          <strong>{depth ? '↳ ' : ''}{agent.name}</strong><span>{agent.role} · {agentStatus(agent)}</span>
        </button>)}</nav>
      </details>
      <div className="tools" role="toolbar" aria-label="Canvas tools">
        <button className={tool === 'select' ? 'active' : ''} aria-label="Select and move agents" aria-pressed={tool === 'select'} onClick={() => setTool('select')}><svg viewBox="0 0 24 24"><path d="M5 3l14 10-7 1-3 7z" /></svg></button>
        <button className={tool === 'hand' ? 'active' : ''} aria-label="Pan canvas" aria-pressed={tool === 'hand'} onClick={() => setTool('hand')}><svg viewBox="0 0 24 24"><path d="M8 12V6a2 2 0 014 0v6-8a2 2 0 014 0v8-5a2 2 0 014 0v9c0 4-2 6-6 6h-1c-2 0-4-1-5-3l-4-6a2 2 0 013-2l3 3" /></svg></button>
      </div>
      <svg className={`canvas ${tool === 'hand' ? 'hand' : ''}`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerUp} onWheel={event => {
        const rect = event.currentTarget.getBoundingClientRect()
        const px = event.clientX - rect.left, py = event.clientY - rect.top
        setCamera(previous => {
          const old = previous || camera
          const zoom = Math.max(0.05, Math.min(2, old.zoom * Math.exp(-event.deltaY * 0.002)))
          return { zoom, x: old.x + px / old.zoom - px / zoom, y: old.y + py / old.zoom - py / zoom }
        })
      }}>
        <defs>
          <pattern id="dots" width={24 * camera.zoom} height={24 * camera.zoom} patternUnits="userSpaceOnUse" x={-camera.x * camera.zoom} y={-camera.y * camera.zoom}><circle cx="1" cy="1" r="1" fill="#cfd5df" /></pattern>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10" fill="none" stroke="#a8b2c3" strokeWidth="1.5" /></marker>
        </defs>
        <rect width="100%" height="100%" fill="url(#dots)" />
        <g transform={`scale(${camera.zoom}) translate(${-camera.x}, ${-camera.y})`}>
          {tree.visible.filter(a => a.parentId && tree.visible.some(parent => parent.id === a.parentId)).map(child => {
            const from = positionFor(child.parentId!), to = positionFor(child.id)
            const x1 = from.x + 150, y1 = from.y + 170, x2 = to.x + 150, y2 = to.y - 9
            return <path key={child.id} d={`M${x1},${y1} C${x1},${y1 + 50} ${x2},${y2 - 50} ${x2},${y2}`} fill="none" stroke="#a8b2c3" strokeWidth="1.5" strokeDasharray="5 4" markerEnd="url(#arrow)" pointerEvents="none" />
          })}
          {tree.visible.map(agent => {
            const position = positionFor(agent.id), selected = selectedId === agent.id
            return <g key={agent.id} data-agent={agent.id} transform={`translate(${position.x}, ${position.y})`} role="button" tabIndex={0} aria-label={`Open ${agent.name} agent`} onKeyDown={event => {
              if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(agent.id) }
            }}>
              <title>{agent.name} · {agent.role} · {agentStatus(agent)}{currentTask(agent) ? `\n${currentTask(agent)}` : ''}</title>
              {selected ? <rect className="selection" x="-6" y="-6" width="312" height="182" rx="14" /> : null}
              <rect className="agent-body" width="300" height="170" rx="10" />
              <rect x="18" y="20" width="34" height="34" rx="9" fill="#e9edfc" />
              <text className="agent-icon" x="35" y="43" textAnchor="middle">{agent.name[0]}</text>
              <text className="agent-name" x="64" y="43">{agent.name.length > 22 ? agent.name.slice(0, 21) + '…' : agent.name}</text>
              <circle className={`status-dot ${agent.status}`} cx="24" cy="84" r="4" />
              <text className="agent-status" x="36" y="89">{connected ? agentStatus(agent) : 'Connecting…'}</text>
              <text className="agent-description" x="19" y="117">{agent.role === 'backtester' ? 'Backtester · historical test only' : `${agent.role || 'Agent'} · shared workspace`}</text>
              <line x1="0" x2="300" y1="137" y2="137" stroke="#e2e6ed" />
              <text className="agent-footer" x="19" y="158">{agent.files.length} {agent.files.length === 1 ? 'file' : 'files'}</text>
              {tree.children.get(agent.id)?.length ? <g role="button" tabIndex={0} aria-label={`${collapsed.has(agent.id) ? 'Expand' : 'Collapse'} ${agent.name} branch`} onPointerDown={event => event.stopPropagation()} onClick={() => toggleBranch(agent.id)} onKeyDown={event => {
                if (event.key === 'Enter' || event.key === ' ') { event.stopPropagation(); event.preventDefault(); toggleBranch(agent.id) }
              }}><rect x="156" y="140" width="138" height="27" fill="transparent" /><text className="agent-footer branch-toggle" x="281" y="158" textAnchor="end">{tree.children.get(agent.id)!.length} {tree.children.get(agent.id)!.length === 1 ? 'subagent' : 'subagents'} {collapsed.has(agent.id) ? '▸' : '▾'}</text></g> : <text className="agent-footer" x="281" y="158" textAnchor="end">Open agent</text>}
            </g>
          })}
        </g>
      </svg>
      <div className="zoom-controls" aria-label="Zoom controls"><button aria-label="Zoom out" onClick={() => zoomBy(0.8)}>−</button><span>{Math.round(camera.zoom * 100)}%</span><button aria-label="Zoom in" onClick={() => zoomBy(1.25)}>+</button><span className="divider" /><button aria-label="Fit all agents" title="Expand all branches and fit view" onClick={() => fit()}>⊡</button><button aria-label="Arrange tree" title="Reset saved positions and arrange tree" onClick={() => fit(true)}>↺</button></div>
      <div className="board-hint">{agents.length} {agents.length === 1 ? 'agent' : 'agents'} · Drag to move · Scroll to zoom</div>
    </section>
  )
}
