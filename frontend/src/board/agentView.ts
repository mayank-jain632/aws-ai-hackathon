import type { Agent } from '../types'

export function agentStatus(agent: Agent): string {
  if (agent.lifecycle) return { idle: 'Idle', working: 'Working', queued: 'Queued', waiting: 'Waiting', monitoring: 'Monitoring', blocked: 'Blocked', completed: 'Completed', stopped: 'Stopped', error: 'Needs attention' }[agent.lifecycle]
  if (agent.status === 'running') {
    if (agent.monitoring) return 'Monitoring'
    if (agent.waitingUntil || agent.waitingForAgents) return 'Waiting'
    if (agent.queued) return 'Queued'
    return 'Working'
  }
  return { idle: 'Idle', stopped: 'Stopped', error: 'Needs attention' }[agent.status]
}

export function currentTask(agent: Agent): string {
  return [...agent.messages].reverse().find(message => message.role === 'user')?.text || agent.objective || ''
}

/** Full fund roster, independent of which canvas branches are collapsed. */
export function treeRows(agents: Agent[]) {
  const ids = new Set(agents.map(agent => agent.id))
  const rows: { agent: Agent; depth: number }[] = []
  const seen = new Set<string>()
  const children = new Map<string, Agent[]>()
  for (const agent of agents) {
    if (!agent.parentId) continue
    children.set(agent.parentId, [...(children.get(agent.parentId) || []), agent])
  }
  function visit(agent: Agent, depth: number) {
    if (seen.has(agent.id)) return
    seen.add(agent.id); rows.push({ agent, depth })
    for (const child of children.get(agent.id) || []) visit(child, depth + 1)
  }
  for (const root of agents.filter(agent => !agent.parentId || !ids.has(agent.parentId))) visit(root, 0)
  for (const agent of agents) visit(agent, 0)
  return rows
}
