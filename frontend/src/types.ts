export type AgentStatus = 'idle' | 'running' | 'stopped' | 'error'
export interface AgentMessage { id: string; role: 'user' | 'assistant'; text: string; source?: string }
export interface Activity { id: string; time: string; label: string; detail: string; kind: string }
export interface Agent {
  id: string; parentId: string | null; name: string; status: AgentStatus; model: string
  messages: AgentMessage[]; activity: Activity[]; files: string[]; workspace: string
}

export type Position = { x: number; y: number }
export type BoardPositions = Record<string, Position>
