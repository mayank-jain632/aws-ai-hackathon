// Uses the pinned upstream Dexter loop, Bedrock, shared file tools, and recursive agent delegation.
import { plugin } from 'bun';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve(import.meta.dir, '../..');
const dexter = process.env.DEXTER_SOURCE_DIR || resolve(root, '.local/dexter');

plugin({
  name: 'local-dexter',
  setup(build) {
    build.onLoad({ filter: /dexter\/src\/model\/llm\.ts$/ }, async ({ path }) => {
      const source = await readFile(path, 'utf8');
      const needle = 'const opts: ModelOpts = { streaming };';
      if (!source.includes(needle)) throw new Error('Pinned Dexter model adapter no longer matches');
      return {
        loader: 'ts',
        contents: "import { ChatBedrockConverse } from '@langchain/aws';\n" + source.replace(needle, `
          if (modelName.startsWith('bedrock:')) {
            return new ChatBedrockConverse({
              model: modelName.slice('bedrock:'.length),
              region: process.env.AWS_REGION || 'us-east-1',
              streaming, maxTokens: 2048,
            });
          }
          ${needle}`).replace('return getProviderById(modelProvider)?.fastModel ?? fallbackModel;', "return fallbackModel.startsWith('bedrock:') ? fallbackModel : (getProviderById(modelProvider)?.fastModel ?? fallbackModel);").replace('yield chunk as AIMessageChunk;', `
          if (model.startsWith('bedrock:') && Array.isArray(chunk.content) && chunk.content.every(b => b.type === 'text')) {
            chunk.content = chunk.content.map(b => b.text).join('');
          }
          yield chunk as AIMessageChunk;`),
      };
    });
    build.onLoad({ filter: /dexter\/src\/utils\/ai-message\.ts$/ }, async ({ path }) => ({
      loader: 'ts', contents: (await readFile(path, 'utf8')).replace(".join('\\n')", ".join('')"),
    }));
    build.onLoad({ filter: /dexter\/src\/utils\/paths\.ts$/ }, async ({ path }) => ({
      loader: 'ts', contents: (await readFile(path, 'utf8')).replace("const DEXTER_DIR = '.dexter';", "const DEXTER_DIR = process.env.DEXTER_STATE_DIR || '.dexter';"),
    }));
    build.onLoad({ filter: /dexter\/src\/tools\/registry\.ts$/ }, () => ({
      loader: 'ts',
      contents: `
        import { readFileTool } from './filesystem/read-file';
        import { writeFileTool } from './filesystem/write-file';
        import { editFileTool } from './filesystem/edit-file';
        import { DynamicStructuredTool } from '@langchain/core/tools';
        import { z } from 'zod';
        const control = async (action, input, signal) => {
          const response = await fetch('http://127.0.0.1:8000/api/internal/agents' + (action ? '/' + action : ''), {
            method: action ? 'POST' : 'GET',
            headers: { 'Content-Type': 'application/json', 'X-Agent-Token': process.env.AGENT_CONTROL_TOKEN || '', 'X-Agent-ID': process.env.LOCAL_AGENT_ID || 'dexter' },
            body: action ? JSON.stringify(input) : undefined,
            signal,
          });
          const result = await response.json();
          if (!response.ok) throw new Error(result.detail || 'Agent control request failed');
          return JSON.stringify(result);
        };
        const createAgent = new DynamicStructuredTool({
          name: 'create_agent',
          description: 'Create a named specialist agent with its own conversation in the shared workspace, give it a self-contained task, and return its result. It appears immediately on the canvas. Provide all context it needs; it can read and edit the same workspace files.',
          schema: z.object({ name: z.string().min(1).max(60), task: z.string().min(1).max(12000) }),
          func: async (input, _manager, config) => control('create', input, config?.signal),
        });
        const listAgents = new DynamicStructuredTool({
          name: 'list_agents', description: 'List yourself and your descendant agents, IDs, parent relationships, and current status.',
          schema: z.object({}), func: async (_input, _manager, config) => control('', null, config?.signal),
        });
        const messageAgent = new DynamicStructuredTool({
          name: 'message_agent', description: 'Send a follow-up task to an existing idle agent by its ID and return its result. Use list_agents to find the ID. You can message only your own descendants.',
          schema: z.object({ agent_id: z.string(), task: z.string().min(1).max(12000) }),
          func: async (input, _manager, config) => control('message', input, config?.signal),
        });
        const tools = [readFileTool, writeFileTool, editFileTool, createAgent, listAgents, messageAgent];
        export const getTools = () => tools;
        export const getToolConcurrencyMap = () => new Map(tools.map(t => [t.name, !['write_file', 'edit_file'].includes(t.name)]));
        export const buildCompactToolDescriptions = () => tools.map(t => t.name + ': ' + t.description).join('\\n');
      `,
    }));
  },
});

const emit = (event: Record<string, unknown>) => process.stdout.write(JSON.stringify(event) + '\n');
try {
  const input = JSON.parse(await Bun.stdin.text());
  const { Agent } = await import(pathToFileURL(resolve(dexter, 'src/agent/agent.ts')).href);
  const { InMemoryChatHistory } = await import(pathToFileURL(resolve(dexter, 'src/utils/in-memory-chat-history.ts')).href);
  const model = `bedrock:${process.env.BEDROCK_MODEL_ID || 'us.openai.gpt-5.6-luna'}`;
  const history = new InMemoryChatHistory(model);
  // Restore the upstream history's completed turns without additional summarization calls.
  history.messages = input.history.map((m: { query: string; answer: string }, id: number) => ({ ...m, id, summary: m.answer }));
  const controller = new AbortController();
  process.on('SIGTERM', () => controller.abort());
  const files = input.files.length ? input.files.join(', ') : 'The workspace is empty.';
  const agent = await Agent.create({
    model, maxIterations: 8, memoryEnabled: false,
    signal: controller.signal,
    toolAllowlist: ['read_file', 'write_file', 'edit_file', 'create_agent', 'list_agents', 'message_agent'],
    requestToolApproval: async () => 'allow-once',
    systemPromptOverride: `You are ${process.env.LOCAL_AGENT_NAME || "Dexter"}, a helpful research assistant in a local agent canvas.
You can read, write, and edit files inside this workspace. Use the tools when the user requests files.
You can create specialist agents with create_agent, inspect the roster with list_agents, and give an existing agent a follow-up with message_agent.
When asked to create or delegate to an agent, actually use create_agent. Give it a clear name and self-contained task. The tool waits for its result.
All agents share the same workspace and files. Each agent has its own conversation and owns its descendant agents. Pass task context explicitly, and coordinate file edits with other agents. Stopping a parent cancels its descendants. Do not create unrequested agents.
Workspace files: ${files}
Be concise. Do not claim to have accessed live financial data, the web, or shell commands: these tools are not enabled.
Files are relative to your current workspace. Do not access paths outside it.
Keep your internal reasoning private. Report actions, observations, and final results instead.`,
  });
  for await (const event of agent.run(input.prompt, history)) {
    if (event.type !== 'thinking') emit(event);
  }
} catch (error) {
  emit({ type: 'error', message: error instanceof Error ? error.message : String(error) });
  process.exitCode = 1;
}
