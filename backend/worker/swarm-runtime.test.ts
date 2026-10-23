import { expect, test } from 'bun:test';
import { extendAgentLoop, runSupervised } from './swarm-runtime';

function fakeAgent(answers: string[]) {
  const calls: string[] = [];
  return { calls, async *run(query: string) { calls.push(query); yield {type: 'done', answer: answers.shift() || 'finished', iterations: 1}; } };
}

test('root remains active until children settle, then resumes pipeline without a false completed event', async () => {
  const agent = fakeAgent(['Delegated work', 'Reviewed results and completed']);
  const events: any[] = [], controls: any[] = [], history = {messages: []};
  let active = true;
  const control = async (path: string, input?: any) => {
    controls.push({path, input});
    if (path === '/wait') { active = false; return JSON.stringify({reason: 'agent_finished'}); }
    return JSON.stringify({agents: [{id: 'dexter', status: 'running'}, {id: 'child', status: active ? 'running' : 'idle'}]});
  };
  await runSupervised(agent, 'Authorized work', history, new AbortController().signal, e => events.push(e), true, 'dexter', control);
  expect(events.map(e => e.type)).toEqual(['monitoring', 'done']);
  expect(events.at(-1).answer).toBe('Reviewed results and completed');
  expect(controls[1]).toEqual({path: '/wait', input: {seconds: 60, agent_ids: ['child']}});
  expect(agent.calls[1]).toContain('not completion');
  expect(history.messages).toHaveLength(1);
});

test('provider errors and exhausted work never turn into supervision success', async () => {
  for (const answer of ['Error: provider denied', 'Reached maximum iterations (12). Incomplete']) {
    const events: any[] = [];
    await runSupervised(fakeAgent([answer]), 'work', {messages: []}, new AbortController().signal, e => events.push(e), true, 'dexter', async () => {throw new Error('must not query roster');});
    expect(events).toHaveLength(1);
    expect(events[0].answer).toBe(answer);
  }
});

test('supervision stops on cancellation and accepts work beyond the old turn ceiling', async () => {
  const controller = new AbortController();
  controller.abort();
  await expect(runSupervised(fakeAgent([]), 'work', {messages: []}, controller.signal, () => {}, true, 'dexter')).rejects.toThrow('incomplete');
  const events: any[] = [];
  const agent = {async *run() {yield {type: 'done', answer: 'finished after useful work', iterations: 100000};}};
  await runSupervised(agent, 'work', {messages: []}, new AbortController().signal, e => events.push(e), true, 'dexter', async () => JSON.stringify({agents: []}));
  expect(events.at(-1).answer).toBe('finished after useful work');
});

test('specialists do not acquire supervisor behavior and incompatible pins fail clearly', async () => {
  const events: any[] = [];
  await runSupervised(fakeAgent(['specialist result']), 'work', {messages: []}, new AbortController().signal, e => events.push(e), false, 'specialist', async () => {throw new Error('not a supervisor');});
  expect(events[0].type).toBe('done');
  expect(() => extendAgentLoop('wrong pin')).toThrow('no longer matches');
});
