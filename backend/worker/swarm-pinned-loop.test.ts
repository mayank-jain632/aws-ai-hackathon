import {expect, test} from 'bun:test';
import {plugin} from 'bun';
import {readFile, mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {AIMessage} from '@langchain/core/messages';
import {extendAgentLoop} from './swarm-runtime';

// This runs the actual pinned loop and executor. Only model responses and the probe tool are fixtures.
test('pinned agents retain history beyond all old turn ceilings and researcher cancellation is prompt', async () => {
  const dexter = resolve(import.meta.dir, '../../.local/dexter');
  const temporary = await mkdtemp(resolve(tmpdir(), 'dexter-loop-test-'));
  plugin({name: 'swarm-loop-test', setup(build) {
    build.onLoad({filter: /dexter\/src\/agent\/agent\.ts$/}, async ({path}) => ({loader: 'ts', contents: extendAgentLoop(await readFile(path, 'utf8'))}));
    build.onLoad({filter: /dexter\/src\/utils\/paths\.ts$/}, () => ({loader: 'ts', contents: `import {join} from 'node:path'; export const getDexterDir = () => ${JSON.stringify(temporary)}; export const dexterPath = (...parts) => join(getDexterDir(), ...parts);`}));
    build.onLoad({filter: /dexter\/src\/tools\/registry\.ts$/}, () => ({loader: 'ts', contents: `import {DynamicStructuredTool} from '@langchain/core/tools'; import {z} from 'zod'; const tool = new DynamicStructuredTool({name:'probe',description:'Fixture probe',schema:z.object({n:z.number()}),func:async ({n})=>'result-'+n}); export const buildCompactToolDescriptions=()=>"probe: Fixture probe"; export const getTools=()=>[tool]; export const getToolConcurrencyMap=()=>new Map([['probe',true]]);`}));
  }});
  try {
    const {Agent} = await import(pathToFileURL(resolve(dexter, 'src/agent/agent.ts')).href);
    for (const role of ['orchestrator', 'research', 'backtester']) {
      const agent = await Agent.create({model: 'gpt-5.6-sol', memoryEnabled: false, systemPromptOverride: 'Test fixture only.', requestToolApproval: async () => 'allow-once'});
      let turns = 0;
      agent.callModelWithStreaming = async function* (messages: any[]) {
        if (turns > 0) expect(messages.findLast((m: any) => m._getType() === 'tool').content).toContain('result-' + (turns - 1));
        const n = turns++;
        return {response: n < 26 ? new AIMessage({content: '', tool_calls: [{id: 'probe-' + n, name: 'probe', args: {n}}]}) : new AIMessage('actual final result')};
      };
      const events: any[] = [];
      for await (const event of agent.run('Continue useful fixture work')) events.push(event);
      expect(events.filter(e => e.type === 'done')[0].iterations).toBeGreaterThan(role === 'orchestrator' ? 24 : role === 'research' ? 12 : 3);
      expect(events.filter(e => e.type === 'tool_end')).toHaveLength(26);
      expect(events.filter(e => e.type === 'done')).toHaveLength(1);
      expect(events.at(-1).answer).toBe('actual final result');
      expect(events.at(-1).iterations).toBe(27);
    }
    const controller = new AbortController();
    const researcher = await Agent.create({model: 'gpt-5.6-sol', signal: controller.signal, memoryEnabled: false, systemPromptOverride: 'Cancellation fixture only.', requestToolApproval: async () => 'allow-once'});
    let turns = 0;
    researcher.callModelWithStreaming = async function* () {
      const n = turns++;
      return {response: new AIMessage({content: '', tool_calls: [{id: 'cancel-' + n, name: 'probe', args: {n}}]})};
    };
    const events: any[] = [];
    let cancellation: unknown;
    try {
      for await (const event of researcher.run('Continue until cancelled')) {
        events.push(event);
        if (event.type === 'tool_end' && events.filter(e => e.type === 'tool_end').length === 13) controller.abort();
      }
    } catch (error) { cancellation = error; }
    expect(cancellation).toBeUndefined();
    expect(events.at(-1).answer).toContain('Error: Run cancelled');
    expect(turns).toBe(13);
    expect(events.filter(e => e.type === 'done')).toHaveLength(1);
    expect(events.some(e => e.type === 'done' && !e.answer.startsWith('Error:'))).toBe(false);

  } finally { await rm(temporary, {recursive: true, force: true}); }
});
