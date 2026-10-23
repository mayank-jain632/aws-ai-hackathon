// Mirrors backend/app/scores/models.py. Read-only view of one fund's scorecard (D23).
export type Scope = 'fund' | 'firm'
export type FactorStatus = 'pass' | 'fail' | 'pending' | 'info'

export interface Citation { id: string; kind: string; title: string; date: string | null; url: string | null; excerpt: string }
export interface AgentRef { id: string | null; name: string; role: string; specialty: string; attribution: 'recorded' | 'role holder' | 'system' }
export interface Provenance { record: string; file: string | null; time: string | null; citations: Citation[] }
export interface Factor {
  key: string; label: string; value: string; number: number | null; weight: number | null; status: FactorStatus
  detail: string; agents: AgentRef[]; reasoning: string | null; reasoning_label: string; provenance: Provenance
}
export interface SourceRef { id: string; label: string; scope: Scope; location: string }
export interface Score {
  key: string; label: string; question: string; status: 'scored' | 'not_produced'; value: number | null
  raw: string; formula: string; source: SourceRef | null; owner: string; missing: string; scope: Scope
  contributors: AgentRef[]; factors: Factor[]
}
export interface SourceStatus { id: string; label: string; owner: string; location: string; status: 'present' | 'empty' | 'not_on_main'; detail: string }
export interface ToolCall { agent: AgentRef; tool: string; summary: string; time: string }
export interface Scorecard {
  fund_id: string; fund_name: string; generated_at: string
  strategy: { id: string; name: string; author: string; created_at: string; weights: Record<string, number>; cutoff: string; end: string } | null
  strategies: { id: string; name: string; created_at: string; verdict: string | null }[]
  scores: Score[]; team_title: string; team_note: string; team: Score[]
  sources: SourceStatus[]; agents: AgentRef[]; inputs: ToolCall[]; notes: string[]
}
