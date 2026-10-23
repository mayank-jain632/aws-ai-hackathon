import { agentControl } from './swarm-tools';

// Preserve the pinned Dexter loop/context, replacing its default turn ceiling with cancellation.
export function extendAgentLoop(source: string): string {
  const loop = 'while (ctx.iteration < this.maxIterations) {';
  const exhausted = 'answer: `Reached maximum iterations (${this.maxIterations}). I was unable to complete the research in the allotted steps.`,';
  if (!source.includes(loop) || !source.includes(exhausted)) {
    throw new Error('Pinned Dexter continuation adapter no longer matches');
  }
  return source.replace(loop, 'while (!this.signal?.aborted) {').replace(exhausted, "answer: 'Error: Run cancelled; work remains incomplete.',");
}


export async function runSupervised(
  agent: {run: (query: string, history: any) => AsyncIterable<any>}, prompt: string,
  history: {messages: any[]}, signal: AbortSignal, emit: (event: any) => void,
  isRoot: boolean, agentId: string, control = agentControl,
) {
  let query = prompt;
  let supervise = true;
  while (supervise && !signal.aborted) {
    supervise = false;
    for await (const event of agent.run(query, history)) {
      if (event.type === 'done' && isRoot && !event.answer.startsWith('Error:') && !event.answer.startsWith('Reached maximum iterations')) {
        const roster = JSON.parse(await control('', undefined, signal, 'GET'));
        const active = roster.agents.filter((a: {id: string; status: string}) => a.id !== agentId && a.status === 'running');
        if (active.length) {
          emit({ type: 'monitoring', iterations: event.iterations, message: 'Task remains active while specialists work; waiting before the next supervision pass.' });
          const result = await control('/wait', {seconds: 60, agent_ids: active.map((a: {id: string}) => a.id)}, signal);
          history.messages.push({id: history.messages.length, query, answer: event.answer.slice(-6000), summary: event.answer.slice(-3000)});
          history.messages = history.messages.slice(-8);
          query = 'Continue the original authorized task: ' + prompt + '\nThe previous response was a progress checkpoint, not completion. Specialist wait result: ' + result + '\nRead relevant threads and memos, follow up or reassign incomplete work, then advance the pipeline. Preserve all human gates. Stop only when work is complete, genuinely blocked, or a person stops it.';
          supervise = true;
          break;
        }
      }
      if (event.type !== 'thinking') emit(event);
    }
  }
  if (signal.aborted) throw new Error('Run stopped; work may remain incomplete');
}
