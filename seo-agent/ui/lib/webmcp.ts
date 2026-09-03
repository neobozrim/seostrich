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
  checkAiCitations,
  getRunGovernance,
  getRunChanges,
  resetRun,
  regenerateBrief,
  fetchCompetitorKeywords,
  researchKeyword,
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

// "The most recent run" must be one worth reading: the pinned one first,
// else the newest that has stages. A chat that produced no report (an
// abandoned prompt, a question) is never the default an assistant lands on.
async function currentRun() {
  // The report on screen is what the person and their assistant are both
  // looking at; that is "the run" unless one is named.
  const onScreen = typeof window !== 'undefined' ? (window as any).__seostrichOpenRun : null;
  if (onScreen) {
    try {
      return await getRun(onScreen);
    } catch {
      /* fall through to the summaries */
    }
  }
  const summaries = await getRuns();
  if (!summaries.length) return null;
  const pick =
    summaries.find((s: any) => s.pinned && !s.archived) ||
    summaries.find((s: any) => (s.stages || 0) > 0 && !s.archived && !/^(test|diag)-/.test(s.id)) ||
    summaries[0];
  return getRun(pick.id);
}

// Resolve a run by explicit id, else the run on screen / pinned / newest.
// An id that does not exist falls back too: tool inspectors send schema
// placeholders ("example_string"), and an agent may retry with a stale id;
// answering "no run found" to either helped nobody. Every result carries
// the run_id actually used.
async function resolveRun(runId?: string) {
  if (runId) {
    try {
      return await getRun(runId);
    } catch {
      /* unknown id: use the default run */
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
const READ_ONLY_UNTRUSTED = { readOnlyHint: true, untrustedContentHint: true };

export function buildTools() {
  return [
    {
      name: 'seo_get_pipeline_overview',
      title: 'SEO pipeline overview',
      description:
        'Where to start: the report on screen (or the one named by run_id) with its stages, plus every other report in this workspace with its run_id, type (SEO content strategy or AI visibility) and date, so you can read a second report - the AI-visibility one next to a strategy, say - by passing its run_id to the other tools. Use it first. Read-only, no cost.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }, _options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        const all = await getRuns().catch(() => []);
        return {
          id: run.id,
          title: run.title,
          project: run.project,
          type: (all.find((r: any) => r.id === run.id) || {}).flow || '',
          created: run.created,
          status: run.status,
          stages: run.stages.map((s: any) => ({ id: s.id, label: s.label, status: s.status })),
          other_reports: all
            .filter((r: any) => r.id !== run.id && !r.archived && !/^(test|diag)-/.test(r.id))
            .map((r: any) => ({ run_id: r.id, title: r.title, type: r.flow || '', created: r.created, pinned: !!r.pinned, stages: r.stages })),
        };
      },
    },
    {
      name: 'seo_get_keyword_clusters',
      title: 'SEO keyword clusters (selected)',
      description:
        'List the SELECTED keyword clusters for the current run with their measured metrics and member keywords. For the discarded ones and the reasoning behind every decision, use seo_list_clusters_all instead. Read-only, no cost.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }) => {
        const run = await resolveRun(input?.run_id);
        const stage = run?.stages?.find((s: any) => s.id === 'clusters');
        if (!stage) return 'No clusters stage found.';
        return stage.artifact?.clusters || [];
      },
    },
    {
      name: 'seo_get_content_pillars',
      title: 'SEO content pillars',
      description:
        'The finished output of a strategy run: the content pillars to actually write, each with a title, type (hub/guide/comparison), priority order, and the rationale naming the metric that justified it. Use this when you want the recommendation rather than the working. Empty until a run reaches the pillars stage. Read-only, no cost.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }) => {
        const run = await resolveRun(input?.run_id);
        const stage = run?.stages?.find((s: any) => s.id === 'pillars');
        if (!stage) return 'No pillars stage found.';
        return stage.artifact?.pillars || [];
      },
    },
    {
      name: 'seo_get_content_calendar',
      title: 'Publishing order from the SEO strategy brief',
      description:
        'What to write, in order: the six pieces the brief commits to, each with a title, the exact question it answers, the cluster it serves and the keywords it targets, plus which pillar to build first and why. Use this to check sequencing. Absent until the brief has been written (seo_regenerate_brief writes it). Read-only, no cost.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        const stage = run.stages?.find((s: any) => s.id === 'brief');
        const brief = stage?.artifact;
        if (!brief?.pieces) return 'No brief yet for this run — seo_regenerate_brief writes one from the selected clusters.';
        return {
          run_id: run.id,
          build_first: brief.the_call,
          order: (brief.pieces || []).map((p: any, i: number) => ({ position: i + 1, ...p })),
          stale: !!brief.stale,
          note: brief.stale
            ? 'The selection changed after this brief was written; seo_regenerate_brief rebuilds it.'
            : 'Written from the selected clusters as they stand.',
        };
      },
    },
    {
      name: 'seo_submit_feedback',
      title: 'Submit pipeline feedback',
      description:
        'Record a note on the run for the human to act on — a concern, a correction, or context the pipeline did not have. Use this for judgements you cannot make yourself; it does NOT change the strategy on its own. To actually change the selection, use seo_promote_cluster or seo_discard_cluster instead. Writes to the run, no API cost.',
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
      description:
        'Reset the bundled example run back to its shipped state. Use only to undo experimentation on the demo data — it discards edits made to the example run and does not touch real runs. Destructive to the example run, no API cost.',
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
        'Fetch the raw artifact of ONE stage, unshaped, for when the purpose-built tools do not expose what you need. Stages: intake (the confirmed market), seeds (the phrases the research started from), keywords, clusters, pillars, mix (calendar), ai_citability, audit, competitors, onpage. Use seo_get_keywords or seo_list_clusters_all first — they return cleaner shapes; drop to this only to inspect something they omit. Read-only, no cost.',
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
        'List BOTH the selected keyword clusters and the discarded ones. Every cluster carries a `reasoning` block: decision_reason (why this cluster was kept, or why it was dropped), why_these_keywords_group, and a `metrics` block MEASURED from the DataForSEO rows (total_volume, max_volume, median_volume, avg/max difficulty, avg/max CPC, commercial_share, top_keywords) — no model estimated these, so you can rank by whichever metric matters rather than trusting a composite. Use this to audit the strategy: check whether a discard reason actually holds, whether a selected cluster earns its place, and what was traded away. Discarded clusters are parked, not deleted — promote any back with seo_promote_cluster. Read-only, no cost.',
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
        'Bring a discarded cluster back into the strategy. Use this when you judge that a cluster was dropped wrongly — read its reasoning.decision_reason first via seo_list_clusters_all, so you are arguing against a stated reason rather than overriding it blindly. Fully reversible with seo_discard_cluster. Writes to the run, no API cost.',
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
        'Drop a cluster from the strategy, with your reason. It is parked rather than deleted — keywords, metrics and history are preserved, and seo_promote_cluster brings it back. Use this when a cluster is off-topic for the business, overlaps one already selected, or targets the wrong intent. Give a real reason: it is shown to the user as part of the decision record. Writes to the run, no API cost.',
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
        'Add a topic the pipeline never explored. Runs fresh keyword research on the topic you name and builds a new cluster from the results, with real volume, difficulty, intent and CPC — nothing invented. Use this when the strategy has a genuine gap; use seo_rerun_cluster_research instead if the topic is already a cluster that just looks thin. Costs one DataForSEO call charged to this run, so name a real head term rather than exploring. Writes to the run.',
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
        'What AI engines already do with these topics: how much AI search demand each head term has, which sources ChatGPT and Google AI currently cite, how much of the answer space is unclaimed, and the real questions people ask (People-also-ask). Use this to judge whether content could realistically be cited by an AI answer, and to write against questions users actually ask rather than guessed ones. Read-only, no cost — the data was already fetched during the run.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY_UNTRUSTED,
      execute: async (input: { run_id?: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        try {
          return await getRunStage(run.id, 'ai_citability', options?.signal);
        } catch {
          return 'This run is a content strategy; AI visibility is a separate report. Start one with "Analyse AI visibility" (or ask for the GEO report) and read it with this tool.';
        }
      },
    },
    {
      name: 'seo_list_flows',
      title: 'SEO flows available',
      description:
        'List the flows this agent can run end to end, each with the inputs it requires before it will start (country and language are always required and are never inferred). Use this to see what can be asked for, and what a flow will need from the user first. Read-only, no cost.',
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
        'Get the keywords for this run as a flat table: search volume, keyword difficulty, CPC, search intent, and which cluster each landed in. Use this to run your own analysis — filter by difficulty, rank by CPC, find intent mismatches, or check whether a cluster is carried by one term. Read-only, no cost — these numbers were already fetched during the run.',
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
        'Fetch fresh keyword data for ONE cluster and merge it in, without re-running the pipeline or re-billing the other clusters. Use when a cluster looks thin, stale or off-target. Costs one DataForSEO call charged to this run, and writes to the run.',
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
      name: 'seo_check_ai_citations',
      title: 'Is this site cited by AI answers?',
      description:
        'Ask which AI answers already cite a given DOMAIN, how many, what they were cited for, and which sites are quoted alongside them. Use it two ways: on your own site to see whether content has started getting cited at all (a new site returns 0, which is the honest baseline, not an error), or on a competitor to see what a comparable site actually gets quoted for — far more concrete than a keyword list. Read-only: it costs one DataForSEO call but changes nothing.',
      inputSchema: {
        type: 'object',
        properties: {
          domain: {
            type: 'string',
            description: "Domain to check, e.g. 'example.com'.",
          },
        },
        required: ['domain'],
      },
      annotations: READ_ONLY_UNTRUSTED,
      execute: async (input: { domain: string }, options?: any) => {
        if (!input?.domain) return 'A domain is required.';
        return checkAiCitations(input.domain, options?.signal);
      },
    },
    {
      name: 'seo_get_governance_history',
      title: 'How this strategy was shaped',
      description:
        'List every change made to the cluster selection since the pipeline produced it — promotions, discards and proposals, in order, each with its reason and who made it (the agent, an external assistant over WebMCP, or the user). Use it to see what a human already decided before you suggest changing it again, or to show how a strategy reached its current shape. Empty means nothing has been adjusted. Read-only, no cost.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return getRunGovernance(run.id, options?.signal);
      },
    },
    {
      name: 'seo_get_brief',
      title: 'SEO strategy brief: what to build, in what order, and why',
      description:
        'The one page a content team acts on, built from the measured stages: which pillar to build first and why (with the numbers), who owns the keywords in that space, six pieces each with a working title and the exact question it answers, and what was parked and why. Use this when you want the plan rather than the working. When the selection changes it is marked `stale` (with the reason) but NOT rebuilt — call seo_regenerate_brief to rebuild it once you are done editing, so ten edits cost one model call rather than ten. Read-only, no cost.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        try {
          return await getRunStage(run.id, 'brief', options?.signal);
        } catch {
          return 'No brief yet — the strategy graph writes it after the pillars.';
        }
      },
    },
    {
      name: 'seo_regenerate_brief',
      title: 'Rebuild the SEO strategy brief from the current selection',
      description:
        'Rewrite the brief from the clusters as they stand now. Use this once after a batch of changes to the selection — it is the only thing that rebuilds the brief. Writes to the run; costs a model call but no DataForSEO calls.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_WRITE,
      execute: async (input: { run_id?: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return regenerateBrief(run.id);
      },
    },
    {
      name: 'seo_check_if_edited',
      title: 'Has this report been changed?',
      description:
        'Say whether the cluster selection still matches what the pipeline produced, or whether someone has edited it since — how many changes are standing, and who made the most recent one. Use this when you are about to judge a strategy or suggest changes of your own: on a shared deployment the report you are reading may already carry decisions someone else made, and reading those as the verdict of the pipeline is the easiest mistake to make here. Read-only, no cost.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return getRunChanges(run.id, options?.signal);
      },
    },
    {
      name: 'seo_reset_run',
      title: 'Undo every change to this report',
      description:
        'Put the cluster selection back to exactly what the pipeline produced, undoing every promotion, discard and proposal made since. Use it to hand a report back in its original state after experimenting, or when the edits on it were made by somebody else and you want to judge the pipeline rather than their edits. The history of what was changed is KEPT, including this reset — nothing is erased, only the selection moves back. Writes to the run, no API cost.',
      inputSchema: { type: 'object', properties: { ...RUN_ID_PROP } },
      annotations: READ_WRITE,
      execute: async (input: { run_id?: string }, options?: any) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        return resetRun(run.id, options?.signal);
      },
    },
    {
      name: 'seo_research_competitor',
      title: 'Add or refresh a competitor',
      description:
        'Put a competitor domain on the competitor map of a run and pull the keywords it ranks for (one DataForSEO call, brand terms removed). Use it when the user names a competitor the run did not check, or wants the full ranked list for a domain. A domain already on the map is refreshed in place; a new public domain is added and the change is logged with who asked. Writes to the run and costs one paid lookup; nothing else in the run changes.',
      inputSchema: {
        type: 'object',
        properties: {
          ...RUN_ID_PROP,
          domain: { type: 'string', description: 'The competitor domain, e.g. lennysnewsletter.com' },
        },
        required: ['domain'],
      },
      annotations: READ_WRITE,
      execute: async (input: { run_id?: string; domain: string }) => {
        const run = await resolveRun(input?.run_id);
        if (!run) return 'No pipeline run found.';
        if (!input?.domain) return 'A domain is required.';
        return fetchCompetitorKeywords(run.id, input.domain, 'webmcp');
      },
    },
    {
      name: 'seo_research_keyword',
      title: 'Research one keyword',
      description:
        'The phrases people search around one topic, with real monthly volume, difficulty, CPC and intent, measured by DataForSEO in the run\u2019s market. Use it to check whether a keyword could carry a theme of its own, or to pick two or three secondary terms for a post around a head term. Read-only: nothing on the run changes, unlike seo_propose_cluster. Costs one DataForSEO call (two when the phrase is narrow and related terms are fetched as well).',
      inputSchema: {
        type: 'object',
        properties: {
          ...RUN_ID_PROP,
          topic: { type: 'string', description: 'The keyword or topic to research, e.g. "llm evaluation harness".' },
          limit: { type: 'integer', description: 'How many phrases to return (5-50, default 30).' },
        },
        required: ['topic'],
      },
      annotations: READ_ONLY,
      execute: async (input: { run_id?: string; topic: string; limit?: number }) => {
        if (!input?.topic) return 'A topic is required.';
        const run = await resolveRun(input?.run_id);
        return researchKeyword(input.topic, run?.id, input.limit || 30);
      },
    },
    {
      name: 'seo_analyze_run',
      title: 'Analyze pipeline run',
      description:
        'Check a run for problems before trusting it: which stages are missing, whether it ended in an error or was stopped, whether clusters were ever curated, and whether too many clusters are still selected to be a focused strategy. Returns findings plus concrete next steps. Use this first when a run looks wrong or incomplete, before digging through individual stages. Read-only and fully deterministic — no model, no API calls, no cost.',
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

  // The graph writes these in order; a missing one means the run stopped
  // there. There is no tool to run a single node — the retry is the run.
  const core: Array<[string, string]> = [
    ['seeds', 'No seeds — the run stopped before reading the brief.'],
    ['keywords', 'No keyword universe — the run stopped before DataForSEO.'],
    ['clusters', 'No themes — the run stopped before clustering.'],
    ['pillars', 'No content pillars — the run stopped before the selection was written up.'],
  ];
  for (const [id, problem] of core) {
    if (!stageIds.has(id)) {
      findings.push(problem);
      nextSteps.push('Retry the run from the artefact; nothing invented so far is lost.');
    }
  }

  // Cluster governance quality checks
  if (stageIds.has('clusters')) {
    const clusterStage = run.stages.find((s: any) => s.id === 'clusters');
    const art = clusterStage?.artifact || {};
    if (!art.selected) {
      findings.push('Clusters were never selected (no selected vs discarded split).');
      nextSteps.push('Retry the run; selection is a graph node, not a tool.');
    } else {
      const sel = (art.clusters || []).length;
      const disc = (art.discarded || []).length;
      findings.push(`Cluster selection made: ${sel} selected, ${disc} discarded.`);
      if (sel > 5) {
        findings.push('More than 5 clusters are still selected — the strategy may be unfocused.');
        nextSteps.push('Discard the weaker ones (seo_discard_cluster) to focus on 3-4 pillars.');
      }
    }
  }
  const changes = (run.governance?.log || run.governance?.changes || []).length;
  if (changes) findings.push(`${changes} change(s) to the selection since the graph produced it — seo_get_governance_history says who and why; seo_reset_run puts it back.`);

  // Stages a run can legitimately lack — informational only
  const briefStage = run.stages?.find((s: any) => s.id === 'brief');
  const missingEnrichment: string[] = [];
  if (!stageIds.has('competitors')) missingEnrichment.push('No competitor map — this run predates it, or no competitor URLs were given.');
  if (!briefStage) missingEnrichment.push('No brief yet — seo_regenerate_brief writes one from the selected clusters.');
  else if (briefStage.artifact?.stale) missingEnrichment.push('The brief is stale: the selection changed after it was written. seo_regenerate_brief rebuilds it.');
  const separate: string[] = [];
  if (!stageIds.has('ai_citability') && !stageIds.has('geo_rank')) separate.push('AI visibility (GEO) is a separate report, not a layer of this one: it measures which questions AI answers already cover and who they cite. Mention it only if the user asks about AI search; it is not something this strategy lacks.');

  return {
    run_id: run.id,
    status: run.status,
    stages_present: Array.from(stageIds),
    findings,
    missing_enrichment: missingEnrichment,
    separate_reports: separate,
    next_steps: nextSteps,
  };
}

let registerPromise: Promise<boolean> | null = null;
let abortController: AbortController | null = null;

/**
 * Register the pipeline tools with the browser's ModelContext.
 * Idempotent: repeated calls return the same in-flight/last result.
 */
// Testing without a WebMCP-enabled browser: `__webmcpTools()` in the console
// returns the same tool objects the browser would register, so each
// `execute` can be called by hand. Read-only; no different from an agent.
if (typeof window !== 'undefined') (window as any).__webmcpTools = () => buildTools();

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
