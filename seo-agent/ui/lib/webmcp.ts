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
import {
  getRuns,
  getRun,
  addRunFeedback,
  restoreDefaultRuns,
  getRunClusters,
  getRunStage,
  promoteRunCluster,
  discardRunCluster,
  proposeRunCluster,
  getRunKeywords,
  rerunClusterResearch,
  getFlows,
} from './api';

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

// Resolve a run by explicit id, else fall back to the most recent run.
async function resolveRun(runId?: string) {
  if (runId) {
    try {
      return await getRun(runId);
    } catch {
      return null;
    }
  }
  return currentRun();
}

const RUN_ID_PROP = {
  run_id: {
    type: 'string',
    description: 'Optional run id. Defaults to the most recent pipeline run.',
  },
};

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
      title: 'SEO keyword clusters (selected)',
      description:
        'List the SELECTED keyword clusters for the current run with their measured metrics and member keywords. For the discarded ones and the reasoning behind every decision, use seo_list_clusters_all instead.',
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
    {
      name: 'seo_get_stage_artifact',
      title: 'SEO stage artifact',
      description:
        'Inspect the artifact of one pipeline stage (intake, seeds, keywords, clusters, pillars, mix, audit, competitors, onpage, ai_citability). Returns the raw artifact so the calling agent can analyze any step.',
      inputSchema: {
        type: 'object',
        properties: {
          ...RUN_ID_PROP,
          stage_id: {
            type: 'string',
            description:
              'Stage to inspect: intake|seeds|keywords|clusters|pillars|mix|audit|competitors|onpage|ai_citability',
          },
        },
        required: ['stage_id'],
      },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string; stage_id: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        try {
          return await getRunStage(run.id, input.stage_id, options?.signal);
        } catch {
          return `Stage '${input.stage_id}' not found in run ${run.id}.`;
        }
      },
    },
    {
      name: 'seo_list_clusters_all',
      title: 'SEO clusters with the reasoning behind each decision',
      description:
        'List BOTH the selected keyword clusters and the discarded ones. Every cluster carries a `reasoning` block: decision_reason (why this cluster was kept, or why it was dropped), why_these_keywords_group, and a `metrics` block MEASURED from the DataForSEO rows (total_volume, max_volume, median_volume, avg/max difficulty, avg/max CPC, commercial_share, top_keywords) — no model estimated these, so you can rank by whichever metric matters rather than trusting a composite. Use this to audit the strategy: check whether a discard reason actually holds, whether a selected cluster earns its place, and what was traded away. Discarded clusters are parked, not deleted — promote any back with seo_promote_cluster.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return getRunClusters(run.id, options?.signal);
      },
    },
    {
      name: 'seo_promote_cluster',
      title: 'Promote discarded cluster',
      description:
        'Promote a previously discarded keyword cluster back into the active selection. Read its reasoning.decision_reason first (via seo_list_clusters_all) to see why it was dropped. Reversible.',
      inputSchema: {
        type: 'object',
        properties: {
          ...RUN_ID_PROP,
          cluster_name: { type: 'string', description: 'Name of the discarded cluster to promote.' },
        },
        required: ['cluster_name'],
      },
      annotations: READ_WRITE,
      execute: async (input: { run_id?: string; cluster_name: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return promoteRunCluster(run.id, input.cluster_name, options?.signal);
      },
    },
    {
      name: 'seo_discard_cluster',
      title: 'Discard selected cluster',
      description:
        'Discard a currently selected keyword cluster (moves it to the discarded set, stats preserved, reversible).',
      inputSchema: {
        type: 'object',
        properties: {
          ...RUN_ID_PROP,
          cluster_name: { type: 'string', description: 'Name of the selected cluster to discard.' },
          reason: { type: 'string', description: 'Why it is being discarded.' },
        },
        required: ['cluster_name'],
      },
      annotations: READ_WRITE,
      execute: async (
        input: { run_id?: string; cluster_name: string; reason?: string },
        options?: any
      ) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return discardRunCluster(run.id, input.cluster_name, input.reason, options?.signal);
      },
    },
    {
      name: 'seo_propose_cluster',
      title: 'Propose new cluster',
      description:
        'Propose a NEW keyword cluster the pipeline missed: a scoped keyword re-seed on one topic (1 DataForSEO call), assembled with real volume/difficulty/intent stats and merged into the run.',
      inputSchema: {
        type: 'object',
        properties: {
          ...RUN_ID_PROP,
          topic: { type: 'string', description: 'The topic/head term to re-seed.' },
        },
        required: ['topic'],
      },
      annotations: READ_WRITE,
      execute: async (input: { run_id?: string; topic: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return proposeRunCluster(run.id, input.topic, options?.signal);
      },
    },
    {
      name: 'seo_get_ai_citability',
      title: 'AI citability brief',
      description:
        'Get the AI-citability stage: how AI engines (ChatGPT/Google AI) answer questions around the selected head terms — AI demand, answer share, currently cited sources, top questions and People-also-ask.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        try {
          return await getRunStage(run.id, 'ai_citability', options?.signal);
        } catch {
          return 'No AI-citability stage yet — run ai_citability_brief in the pipeline first.';
        }
      },
    },
    {
      name: 'seo_list_flows',
      title: 'SEO flows available',
      description:
        'List the flows this agent can run end to end, each with the inputs it requires before it will start (country and language are always required and are never inferred). Use this to see what can be asked for, and what a flow will need from the user first.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      execute: async (_input: any, options?: any) => {
        const catalog = await getFlows(options?.signal);
        return {
          flows: catalog.flows.map((f) => ({
            id: f.id,
            label: f.label,
            does: f.description,
            steps: f.nodes,
            requires: f.required_inputs.map((i) => i.label),
          })),
          not_yet_available: catalog.planned,
          markets: catalog.markets.map((m) => `${m.market} (${m.country})`),
        };
      },
    },
    {
      name: 'seo_get_keywords',
      title: 'SEO keywords with metrics',
      description:
        'Get the keywords for this run as a flat table: search volume, keyword difficulty, CPC, search intent, and which cluster each landed in. Use this to run your own analysis — filter by difficulty, rank by CPC, find intent mismatches, or check whether a cluster is carried by one term.',
      inputSchema: {
        type: 'object',
        properties: {
          ...RUN_ID_PROP,
          cluster: {
            type: 'string',
            description: 'Optional cluster name to restrict the table to.',
          },
        },
      },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string; cluster?: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return getRunKeywords(run.id, input?.cluster, options?.signal);
      },
    },
    {
      name: 'seo_rerun_cluster_research',
      title: 'Re-run research for one cluster',
      description:
        'Fetch fresh keyword data for ONE cluster and merge it in, without re-running the pipeline or re-billing the other clusters. Use when a cluster looks thin, stale or off-target. Costs one DataForSEO call, charged to this run.',
      inputSchema: {
        type: 'object',
        properties: {
          ...RUN_ID_PROP,
          cluster_name: {
            type: 'string',
            description: 'The cluster to refresh (selected or discarded).',
          },
        },
        required: ['cluster_name'],
      },
      annotations: READ_WRITE,
      execute: async (input: { run_id?: string; cluster_name: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return rerunClusterResearch(run.id, input.cluster_name, options?.signal);
      },
    },
    {
      name: 'seo_analyze_run',
      title: 'Analyze pipeline run',
      description:
        'Deterministic health/gap analysis of a pipeline run (no LLM): which stages exist, which expected stages are missing, run status issues, and whether cluster validation/selection happened. Returns findings + suggested next steps so the orchestrator (or an external agent) knows what to fix.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return analyzeRun(run);
      },
    },
  ];
}

// Deterministic run health/gap analysis — no LLM, no DataForSEO.
function analyzeRun(run: any) {
  const stageIds = new Set((run.stages || []).map((s: any) => s.id));
  const findings: string[] = [];
  const nextSteps: string[] = [];

  if (run.status === 'error') {
    findings.push('Run ended in an error state.');
    nextSteps.push('Inspect the failing stage artifact and re-run the failed step.');
  } else if (run.status === 'stopped') {
    findings.push('Run was stopped before completion.');
    nextSteps.push('Resume or re-run the pipeline to complete the remaining stages.');
  } else if (run.status === 'running') {
    findings.push('Run is still in progress.');
  }

  // Core pipeline order expectations
  const core: Array<[string, string, string]> = [
    ['seeds', 'No seed keywords extracted.', 'Run extract_seeds.'],
    ['keywords', 'No keyword discovery stage.', 'Run keyword research (pull_universe / keyword_suggestions).'],
    ['clusters', 'No clustering stage.', 'Cluster the discovered keywords.'],
    ['pillars', 'No content pillars yet.', 'Recommend pillars from the selected clusters.'],
  ];
  for (const [id, problem, fix] of core) {
    if (!stageIds.has(id)) {
      findings.push(problem);
      nextSteps.push(fix);
    }
  }

  // Cluster governance quality checks
  if (stageIds.has('clusters')) {
    const clusterStage = run.stages.find((s: any) => s.id === 'clusters');
    const art = clusterStage?.artifact || {};
    if (!art.selected) {
      findings.push('Clusters were never selected/curated (no selected vs discarded split).');
      nextSteps.push('Run select_clusters to pick the top 3-4 and park the rest with reasons.');
    } else {
      const sel = (art.clusters || []).length;
      const disc = (art.discarded || []).length;
      findings.push(`Cluster selection made: ${sel} selected, ${disc} discarded.`);
      if (sel > 5) {
        findings.push('More than 5 clusters are still selected — the strategy may be unfocused.');
        nextSteps.push('Consider discarding weaker clusters to focus on 3-4 pillars.');
      }
    }
  }

  // Optional/enrichment stages — informational only
  const enrichment: Array<[string, string]> = [
    ['ai_citability', 'AI-citability brief not generated (run ai_citability_brief on the selected head terms).'],
    ['mix', 'No content calendar yet (offer plan_calendar if the user wants a schedule).'],
    ['audit', 'No technical audit run (on-demand only).'],
  ];
  const missingEnrichment: string[] = [];
  for (const [id, note] of enrichment) {
    if (!stageIds.has(id)) missingEnrichment.push(note);
  }

  return {
    run_id: run.id,
    status: run.status,
    stages_present: Array.from(stageIds),
    findings,
    missing_enrichment: missingEnrichment,
    next_steps: nextSteps,
  };
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
