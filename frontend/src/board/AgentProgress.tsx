import type { Agent } from '../types'
import { agentStatus, currentTask } from './agentView'

export function AgentProgress({ agent, agents, onOpenFile }: { agent: Agent; agents: Agent[]; onOpenFile: (path: string) => void }) {
  const task = currentTask(agent)
  const workflow = agent.workflow
  const response = [...agent.messages].reverse().find(message => message.role === 'assistant')
  const activity = agent.activity.at(-1)
  const parent = agents.find(item => item.id === agent.parentId)
  const children = agents.filter(item => item.parentId === agent.id)
  return <details className="agent-context">
    <summary>Task &amp; progress</summary>
    <dl>
      <dt>Role</dt><dd>{agent.role}</dd>
      <dt>Parent</dt><dd>{parent ? `${parent.name} (${parent.id})` : 'Fund root'}</dd>
      <dt>State</dt><dd>{agentStatus(agent)}{agent.waitingUntil && agent.status === 'running' ? ` · until ${new Date(agent.waitingUntil).toLocaleTimeString()}` : ''}</dd>
      {workflow?.phase && <><dt>Reported phase</dt><dd>{workflow.phase}</dd></>}
      {workflow?.blocker && <><dt>Reported blocker</dt><dd className="context-text">{workflow.blocker}</dd></>}
      {!!workflow?.artifacts?.length && <><dt>Reported artifacts</dt><dd>{workflow.artifacts.map(path => <button className="context-file" key={path} onClick={() => onOpenFile(path)}>{path}</button>)}</dd></>}
      <dt>Current task</dt><dd className="context-text">{task || 'No task assigned yet.'}</dd>
      {activity && <><dt>Latest activity</dt><dd>{activity.label} · {new Date(activity.time).toLocaleTimeString()}{activity.detail && <p className="context-text">{activity.detail.slice(0, 1200)}{activity.detail.length > 1200 ? '… See Activity for the full entry.' : ''}</p>}</dd></>}
      {response && <><dt>Latest response</dt><dd className="context-text">{response.text.slice(0, 1200)}{response.text.length > 1200 ? '… Full response in Chat.' : ''}</dd></>}
      <dt>Direct subagents</dt><dd>{children.length ? children.map(child => `${child.name}: ${agentStatus(child)}`).join('; ') : 'None'}</dd>
      <dt>Shared workspace</dt><dd>{agent.files.length} files available in the Files tab. Files are shared by this fund’s agents.</dd>
    </dl>
    {workflow && <p className="progress-note">Phase and completion reports come from the agent. Backend evaluations and trading approvals remain separate.</p>}
  </details>
}
