import {expect, test} from 'bun:test';
import {plugin} from 'bun';
import {readFile, mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {AIMessage} from '@langchain/core/messages';
import {extendRootLoop} from './swarm-runtime';

// This runs the actual pinned loop and executor. Only model responses and the probe tool are fixtures.
test('pinned Dexter continues beyond turn 24 with its tool history intact', async () => {
  const dexter = resolve(import.meta.dir, '../../.local/dexter');
  const temporary = await mkdtemp(resolve(tmpdir(), 'dexter-loop-test-'));
  plugin({name: 'swarm-loop-test', setup(build) {
    build.onLoad({filter: /dexter\/src\/agent\/agent\.ts$/}, async ({path}) => ({loader: 'ts', contents: extendRootLoop(await readFile(path, 'utf8'), true)}));
    build.onLoad({filter: /dexter\/src\/utils\/paths\.ts$/}, () => ({loader: 'ts', contents: `import {join} from 'node:path'; export const getDexterDir = () => ${JSON.stringify(temporary)}; export const dexterPath = (...parts) => join(getDexterDir(), ...parts);`}));
    build.onLoad({filter: /dexter\/src\/tools\/registry\.ts$/}, () => ({loader: 'ts', contents: `import {DynamicStructuredTool} from '@langchain/core/tools'; import {z} from 'zod'; const tool = new DynamicStructuredTool({name:'probe',description:'Fixture probe',schema:z.object({n:z.number()}),func:async ({n})=>'result-'+n}); export const buildCompactToolDescriptions=()=>"probe: Fixture probe"; export const getTools=()=>[tool]; export const getToolConcurrencyMap=()=>new Map([['probe',true]]);`}));
  }});
  try {
    const {Agent} = await import(pathToFileURL(resolve(dexter, 'src/agent/agent.ts')).href);
    const agent = await Agent.create({model: 'gpt-5.6-sol', maxIterations: 24, memoryEnabled: false, systemPromptOverride: 'Test fixture only.', requestToolApproval: async () => 'allow-once'});
    let turns = 0;
    agent.callModelWithStreaming = async function* (messages: any[]) {
      if (turns > 0) expect(messages.findLast((m: any) => m._getType() === 'tool').content).toContain('result-' + (turns - 1));
      const n = turns++;
      return {response: n < 26 ? new AIMessage({content: '', tool_calls: [{id: 'probe-' + n, name: 'probe', args: {n}}]}) : new AIMessage('actual final result')};
    };
    const events: any[] = [];
    for await (const event of agent.run('Continue useful fixture work')) events.push(event);
    expect(events.at(-1).answer).toBe('actual final result');
    expect(events.filter(e => e.type === 'continuation').map(e => e.iterations)).toEqual([24]);
    expect(events.filter(e => e.type === 'tool_end')).toHaveLength(26);
    expect(events.filter(e => e.type === 'done')).toHaveLength(1);
    expect(events.at(-1).answer).toBe('actual final result');
    expect(events.at(-1).iterations).toBe(27);
  } finally { await rm(temporary, {recursive: true, force: true}); }
});
