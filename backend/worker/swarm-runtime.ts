import { agentControl } from './swarm-tools';

// Extend only the pinned orchestrator's loop. Its messages, tool IDs and compaction stay intact.
export const ROOT_MAX_TURNS = 2400;
export const ROOT_MAX_MS = 4 * 60 * 60 * 1000;

export function extendRootLoop(source: string, isRoot: boolean): string {
  if (!isRoot) return source;
  const loop = 'while (ctx.iteration < this.maxIterations) {\n      ctx.iteration++;';
  const exhausted = 'answer: `Reached maximum iterations (${this.maxIterations}). I was unable to complete the research in the allotted steps.`,';
  if (!source.includes(loop) || !source.includes(exhausted)) {
    throw new Error('Pinned Dexter continuation adapter no longer matches');
  }
  return source.replace(loop, `while (ctx.iteration < ${ROOT_MAX_TURNS} && Date.now() - startTime < ${ROOT_MAX_MS}) {
      if (ctx.iteration > 0 && ctx.iteration % this.maxIterations === 0) {
        yield { type: 'continuation', iterations: ctx.iteration, message: 'Iteration window exhausted; continuing the unfinished task with the same live context.' } as any;
      }
      ctx.iteration++;`).replace(exhausted, `answer: \`Reached maximum iterations or run duration (\${ctx.iteration} turns; four-hour limit). Work remains incomplete. Saved files and visible tool checkpoints can be used on the next explicit or scheduled wakeup.\`,`);
}


export async function runSupervised(
  agent: {run: (query: string, history: any) => AsyncIterable<any>}, prompt: string,
  history: {messages: any[]}, signal: AbortSignal, emit: (event: any) => void,
  isRoot: boolean, agentId: string, control = agentControl, clock = Date.now,
) {
  const started = clock();
  let query = prompt;
  let supervise = true;
  let totalTurns = 0;
  while (supervise && !signal.aborted) {
    supervise = false;
    for await (const event of agent.run(query, history)) {
      if (event.type === 'done') totalTurns += event.iterations || 0;
      if (isRoot && totalTurns > ROOT_MAX_TURNS) throw new Error('Supervision turn limit reached; work remains incomplete');
      if (event.type === 'done' && isRoot && !event.answer.startsWith('Error:') && !event.answer.startsWith('Reached maximum iterations')) {
        const roster = JSON.parse(await control('', undefined, signal, 'GET'));
        const active = roster.agents.filter((a: {id: string; status: string}) => a.id !== agentId && a.status === 'running');
        if (active.length) {
          if (clock() - started >= ROOT_MAX_MS) throw new Error('Four-hour supervision limit reached; work remains incomplete');
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
  if (signal.aborted) throw new Error('Run stopped or four-hour limit reached; work may remain incomplete');
}
