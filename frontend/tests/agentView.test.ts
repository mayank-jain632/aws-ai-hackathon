import { describe, expect, test } from 'bun:test'
import type { Agent } from '../src/types'
import { agentStatus, currentTask, treeRows } from '../src/board/agentView'
const agent = (id: string, parentId: string | null = null, extra: Partial<Agent> = {}) => ({ id, parentId, status: 'idle', messages: [], ...extra }) as Agent

describe('whole-fund canvas presentation', () => {
  test('every grandchild and sibling appears once with ancestry depth', () => {
    expect(treeRows([agent('root'), agent('one', 'root'), agent('deep', 'one'), agent('two', 'root')]).map(({agent, depth}) => [agent.id, depth])).toEqual([['root',0],['one',1],['deep',2],['two',1]])
  })
  test('orphan and malformed cycle cannot hide or duplicate the roster', () => {
    const rows = treeRows([agent('orphan','missing'),agent('a','b'),agent('b','a')])
    expect(new Set(rows.map(row => row.agent.id)).size).toBe(3)
    expect(rows.length).toBe(3)
  })
  test('monitoring and waits precede queue flag, never report idle as complete', () => {
    expect(agentStatus(agent('x',null,{status:'running',monitoring:true,queued:true}))).toBe('Monitoring')
    expect(agentStatus(agent('x',null,{status:'running',waitingUntil:'2026-10-23T16:00:00Z',queued:true}))).toBe('Waiting')
    expect(agentStatus(agent('x',null,{status:'running',waitingForAgents:true}))).toBe('Waiting')
    expect(agentStatus(agent('x',null,{status:'running',queued:true}))).toBe('Queued')
    expect(agentStatus(agent('x',null,{status:'idle'}))).toBe('Idle')
  })
  test('server lifecycle exposes reported blockers and completion without prose parsing', () => {
    expect(agentStatus(agent('x', null, {lifecycle:'blocked',workflow:{status:'blocked',blocker:'Provider unavailable'}}))).toBe('Blocked')
    expect(agentStatus(agent('x', null, {lifecycle:'completed'}))).toBe('Completed')
  })
  test('task is the latest visible assignment, without reading assistant prose as state', () => {
    const item = agent('x',null,{messages:[{id:'a',role:'user',text:'first task'}, {id:'b',role:'assistant',text:'blocked or complete'}, {id:'c',role:'user',text:'follow-up task'}]})
    expect(currentTask(item)).toBe('follow-up task')
    expect(agentStatus(item)).toBe('Idle')
  })
})
