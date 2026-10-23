import { useId } from 'react'
import { layoutTree, NODE_HEIGHT, NODE_WIDTH } from '../board/tree'
import type { Fund } from './types'

/** Uses the same tree layout and current roster as the full agent canvas. */
export function FundPreview({ fund }: { fund: Fund }) {
  const gridId = useId()
  const tree = layoutTree(fund.agents, new Set<string>())
  const positions = Object.values(tree.positions)
  const minX = Math.min(0, ...positions.map(p => p.x))
  const minY = Math.min(80, ...positions.map(p => p.y))
  const maxX = Math.max(NODE_WIDTH, ...positions.map(p => p.x + NODE_WIDTH))
  const maxY = Math.max(250, ...positions.map(p => p.y + NODE_HEIGHT))
  const width = Math.max(600, maxX - minX + 100)
  const height = Math.max(350, maxY - minY + 100)
  const left = (minX + maxX - width) / 2
  const top = (minY + maxY - height) / 2
  return <svg className="fund-preview" viewBox={`${left} ${top} ${width} ${height}`} role="img" aria-label={`${fund.name} agent canvas, ${fund.agents.length} agents, ${fund.metrics.working} working`}>
    <defs><pattern id={gridId} width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.2" fill="#d8d2c9"/></pattern></defs>
    <rect x={left} y={top} width={width} height={height} fill={`url(#${gridId})`}/>
    {tree.visible.map(agent => {
      const p = tree.positions[agent.id]
      const parent = agent.parentId ? tree.positions[agent.parentId] : null
      return <g key={agent.id}>
        {parent && <path d={`M${parent.x + NODE_WIDTH / 2} ${parent.y + NODE_HEIGHT}V${p.y - 50}H${p.x + NODE_WIDTH / 2}V${p.y}`} fill="none" stroke="#b9ada1" strokeWidth="2"/>}
        <rect x={p.x} y={p.y} width={NODE_WIDTH} height={NODE_HEIGHT} rx="8" fill="#faf9f6" stroke={agent.status === 'running' ? '#874e4c' : '#c8bcb0'} strokeWidth="2"/>
        <circle cx={p.x + 24} cy={p.y + 34} r="5" fill={agent.status === 'running' ? '#874e4c' : agent.status === 'error' ? '#b44737' : '#69816b'}/>
        <text x={p.x + 41} y={p.y + 41} fontSize="23" fill="#292622" fontFamily="Georgia,serif">{agent.name.length > 19 ? `${agent.name.slice(0,18)}…` : agent.name}</text>
        <text x={p.x + 22} y={p.y + 90} fontSize="17" fill="#756c62">{agent.status === 'running' ? 'Working' : agent.status === 'error' ? 'Needs attention' : agent.status === 'stopped' ? 'Stopped' : 'Ready'}</text>
        <path d={`M${p.x} ${p.y + 120}h${NODE_WIDTH}`} stroke="#e5dfd7"/>
        <text x={p.x + 22} y={p.y + 151} fontSize="15" fill="#756c62">{tree.children.get(agent.id)?.length || 0} subagents</text>
      </g>
    })}
  </svg>
}
