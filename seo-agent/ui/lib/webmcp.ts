'use client';

/**
 * WebMCP integration — exposes the SEO pipeline as browser-side tools.
 *
 * Implements the current WebMCP spec (https://webmachinelearning.github.io/webmcp/):
 *   document.modelContext.registerTool({ name, title, description, inputSchema,
 *     annotations, execute }, { signal })
 *
 * - `registerTool` returns a Promise; we await it and swallow per-tool failures.
 * - Read-only tools set `annotations.readOnlyHint = true`.
 * - `execute(input, options)` receives an AbortSignal via options; we surface it
 *   to the underlying fetches so an aborted agent call cancels cleanly.
 * - Re-registration / unregistration follows the spec's AbortController pattern.
 *
 * Registration is defensive: on browsers without `modelContext` we no-op.
 */
import { getRuns, getRun, addRunFeedback, restoreDefaultRuns } from './api';

interface ModelContextLike {
  registerTool?: (tool: any, options?: any) => Promise<unknown>;
}

function getModelContext(): ModelContextLike | null {
  if (typeof window === 'undefined') return null;
  const doc = (window as any).document as any;
  const nav = (window as any).navigator as any;
  // Spec puts modelContext on Document; navigator was an early Chrome location.
  return doc?.modelContext || nav?.modelContext || null;
}

async function currentRun() {
  const summaries = await getRuns();
  if (!summaries.length) return null;
  return getRun(summaries[0].id);
}

const READ_ONLY = { readOnlyHint: true };
const READ_WRITE = { readOnlyHint: false };

function buildTools() {
  return [
    {
      name: 'seo_get_pipeline_overview',
      title: 'SEO pipeline overview',
      description:
        'Get an overview of the current SEO pipeline run: project, status and the list of stages with their labels.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      execute: async (_input: any, _options?: any) => {
        const run = await currentRun();
        if (!run) return 'No pipeline run found.';
        return {
          id: run.id,
          project: run.project,
          status: run.status,
          stages: run.stages.map((s: any) => ({ id: s.id, label: s.label, status: s.status })),
        };
      },
    },
    {
      name: 'seo_get_keyword_clusters',
      title: 'SEO keyword clusters',
      description:
        'List the keyword clusters for the current run with their SEO/GEO/combined scores and member keywords.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      execute: async () => {
        const run = await currentRun();
        const stage = run?.stages?.find((s: any) => s.id === 'clusters');
        if (!stage) return 'No clusters stage found.';
        return stage.artifact?.clusters || [];
      },
    },
    {
      name: 'seo_get_content_pillars',
      title: 'SEO content pillars',
      description:
        'List the prioritized content pillars (title, type, priority, rationale) for the current run.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      execute: async () => {
        const run = await currentRun();
        const stage = run?.stages?.find((s: any) => s.id === 'pillars');
        if (!stage) return 'No pillars stage found.';
        return stage.artifact?.pillars || [];
      },
    },
    {
      name: 'seo_get_content_calendar',
      title: 'SEO content calendar',
      description:
        'Get the planned content calendar (week-by-week article plan) for the current run.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      execute: async () => {
        const run = await currentRun();
        const stage = run?.stages?.find((s: any) => s.id === 'mix');
        if (!stage) return 'No calendar stage found.';
        return stage.artifact?.calendar || [];
      },
    },
    {
      name: 'seo_submit_feedback',
      title: 'Submit pipeline feedback',
      description:
        'Attach a feedback note to the current pipeline run so the agent can revise the plan.',
      inputSchema: {
        type: 'object',
        properties: {
          text: { type: 'string', description: 'The feedback to record.' },
        },
        required: ['text'],
      },
      annotations: READ_WRITE,
      execute: async (input: { text: string }) => {
        const run = await currentRun();
        if (!run) return 'No pipeline run found.';
        const res = await addRunFeedback(run.id, input?.text || '', 'webmcp');
        return { ok: true, feedbackCount: res?.feedback?.length || 0 };
      },
    },
    {
      name: 'seo_restore_defaults',
      title: 'Restore example pipeline',
      description: 'Reset the example pipeline run back to the shipped default data.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_WRITE,
      execute: async () => {
        const res = await restoreDefaultRuns();
        return res;
      },
    },
  ];
}

let registerPromise: Promise<boolean> | null = null;
let abortController: AbortController | null = null;

/**
 * Register the pipeline tools with the browser's ModelContext.
 * Idempotent: repeated calls return the same in-flight/last result.
 */
export function registerWebMcpTools(): Promise<boolean> {
  if (registerPromise) return registerPromise;
  registerPromise = (async () => {
    const ctx = getModelContext();
    if (!ctx || typeof ctx.registerTool !== 'function') return false;

    // Abort any previous registration set before (re)registering, per spec.
    if (abortController) abortController.abort();
    abortController = new AbortController();

    let any = false;
    for (const tool of buildTools()) {
      try {
        await ctx.registerTool(tool, { signal: abortController.signal });
        any = true;
      } catch (e) {
        console.error(`WebMCP registerTool failed for ${tool.name}:`, e);
      }
    }
    return any;
  })();
  return registerPromise;
}
