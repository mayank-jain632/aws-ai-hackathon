import type { Agent } from '../types'

export const NODE_WIDTH = 300
export const NODE_HEIGHT = 170
const SIBLING_GAP = 64
const LEVEL_GAP = 100
export type Position = { x: number; y: number }

/** Center each parent over its children's measured subtrees. */
export function layoutTree<T extends Pick<Agent, 'id' | 'parentId'>>(agents: T[], collapsed: Set<string>) {
  const byId = new Map(agents.map(agent => [agent.id, agent]))
  const children = new Map<string, T[]>()
  for (const agent of agents) {
    if (!agent.parentId) continue
    const siblings = children.get(agent.parentId) || []
    siblings.push(agent)
    children.set(agent.parentId, siblings)
  }
  const widths = new Map<string, number>()
  function measure(id: string): number {
    if (widths.has(id)) return widths.get(id)!
    const descendants = collapsed.has(id) ? [] : children.get(id) || []
    const width = Math.max(NODE_WIDTH, descendants.reduce((sum, child) => sum + measure(child.id), 0) + Math.max(0, descendants.length - 1) * SIBLING_GAP)
    widths.set(id, width)
    return width
  }
  const positions: Record<string, Position> = {}
  const visible: T[] = []
  function place(agent: T, left: number, depth: number) {
    const width = measure(agent.id)
    positions[agent.id] = { x: left + (width - NODE_WIDTH) / 2, y: 80 + depth * (NODE_HEIGHT + LEVEL_GAP) }
    visible.push(agent)
    if (collapsed.has(agent.id)) return
    for (const child of children.get(agent.id) || []) {
      place(child, left, depth + 1)
      left += measure(child.id) + SIBLING_GAP
    }
  }
  let left = 0
  for (const root of agents.filter(agent => !agent.parentId || !byId.has(agent.parentId))) {
    place(root, left, 0)
    left += measure(root.id) + SIBLING_GAP
  }
  return { positions, visible, children }
}
