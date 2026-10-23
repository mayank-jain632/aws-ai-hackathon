export type AgentStatus = 'idle' | 'running' | 'stopped' | 'error'
export interface AgentMessage { id: string; role: 'user' | 'assistant'; text: string; source?: string }
export interface Activity { id: string; time: string; label: string; detail: string; kind: string }
export interface Agent {
  lifecycle?: 'idle' | 'working' | 'queued' | 'waiting' | 'monitoring' | 'blocked' | 'completed' | 'stopped' | 'error'
  objective?: string; recentResult?: string; artifacts?: string[]
  workflow?: { status?: 'working' | 'blocked' | 'complete'; phase?: string; blocker?: string | null; artifacts?: string[]; reported_at?: string }
  modelChoices: { id: string; name: string }[]
  waitingForAgents?: boolean; queued?: boolean; waitingUntil?: string | null; monitoring?: boolean
  role: 'orchestrator' | 'research' | 'adversarial' | 'strategy' | 'backtester' | 'executor' | 'moderator'; tools: string[]
  id: string; parentId: string | null; name: string; status: AgentStatus; model: string
  messages: AgentMessage[]; activity: Activity[]; files: string[]; workspace: string
}

export type Position = { x: number; y: number }
export type BoardPositions = Record<string, Position>
