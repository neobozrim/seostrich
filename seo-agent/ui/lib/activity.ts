import { ActivityEvent } from '../types';

/**
 * What the agent is doing, in words a person would use.
 *
 * The stream carries node names and tool names ("node: extract seeds",
 * "pull_universe"). Those are the pipeline's vocabulary, not the reader's.
 * A status line should read like a colleague saying what they are on now.
 */

const TOOL_PHRASES: Record<string, string> = {
  seo_agent: 'Working on your strategy',
  extract_seeds: 'Building seed phrases from your brief and your pages',
  read_page: 'Reading your page',
  pull_universe: 'Pulling keyword data from DataForSEO',
  keyword_suggestions: 'Fetching keyword stats',
  related_keywords: 'Expanding related keywords',
  cluster_keywords: 'Grouping keywords into themes',
  validate_clusters: 'Reviewing the themes',
  score_clusters: 'Measuring each theme',
  select_clusters: 'Choosing the themes worth pursuing',
  recommend_pillars: 'Writing the content pillars',
  plan_calendar: 'Planning the calendar',
  ai_citability_brief: 'Checking who AI answers cite',
  ai_citation_check: 'Checking AI citations',
  run_keyword_strategy: 'Running the content strategy',
  run_geo_demand: 'Running the AI-visibility research',
  confirm_market: 'Confirming the market',
  list_markets: 'Looking up markets',
  submit_deliverable: 'Saving the report',
  list_clusters_all: 'Reading the clusters',
  promote_cluster: 'Promoting a cluster',
  discard_cluster: 'Discarding a cluster',
  propose_cluster: 'Researching a proposed cluster',
  rerun_cluster_research: 'Refreshing a cluster',
  read_run_section: 'Reading the report',
  web_search: 'Searching the web',
};

// Step details emitted by the graphs, matched by prefix. Order matters:
// first match wins, so the specific ones come before the generic ones.
const STEP_PHRASES: Array<[RegExp, string | ((m: RegExpMatchArray) => string)]> = [
  [/^market: (.+)/, (m) => `Market confirmed: ${m[1]}`],
  [/^reading your page: (.+)/, (m) => `Reading your page: ${m[1]}`],
  [/^links: (.+)/, (m) => `Links found — ${m[1]}`],
  [/^node: extract seeds/, 'Building seed phrases from your brief'],
  [/^node: keyword universe/, 'Pulling keyword data from DataForSEO'],
  [/^competitors: (\d+) queried.*?(\d+) keywords.*?(\d+) ranked by two or more/,
    (m) => `Checked ${m[1]} competitors: ${m[2]} keywords, ${m[3]} shared by two or more`],
  [/^note: thin market/, 'Thin market: little search data, leaning on seeds and competitors'],
  [/^node: cluster (\d+) keywords/, (m) => `Grouping ${m[1]} keywords into themes`],
  [/^node: verify clusters against live SERPs/, 'Verifying themes against live Google results'],
  [/^node: validate clusters/, 'Reviewing the themes'],
  [/^gate: needs_revision/, 'Re-grouping after review'],
  [/^cluster node: LLM failed/, 'Retrying the grouping step'],
  [/^node: compute cluster metrics/, 'Measuring each theme'],
  [/^node: select top/, 'Choosing the themes worth pursuing'],
  [/^node: pillars/, 'Writing the content pillars'],
  [/^node: search demand for (\d+) topics/, (m) => `Measuring search demand for ${m[1]} topics`],
  [/^node: grade the sites AI engines cite/, 'Checking who AI answers cite, and whether they can be displaced'],
  [/^node: rank topics/, 'Ranking topics on measured demand'],
  [/^budget exhausted/, 'Stopping early: the call budget is used up'],
  [/^graph complete/, 'Done'],
  [/^node: (.+)/, (m) => m[1].charAt(0).toUpperCase() + m[1].slice(1)],
];

export function activityLabel(ev: ActivityEvent): string {
  if (ev.kind === 'llm_round') return 'Writing the summary';
  if (ev.kind === 'answer') return 'Writing the summary';
  if (ev.kind === 'step') {
    const d = ev.detail || '';
    for (const [re, phrase] of STEP_PHRASES) {
      const m = d.match(re);
      if (m) return typeof phrase === 'function' ? phrase(m) : phrase;
    }
    return d || 'Working';
  }
  const name = TOOL_PHRASES[ev.tool || ''] || (ev.tool ? ev.tool.replace(/_/g, ' ') : 'Working');
  if (ev.kind === 'tool_start') return name;
  if (ev.kind === 'tool_end') return ev.success ? name : `${name} — failed`;
  return name;
}

export function activityLine(ev: ActivityEvent): string {
  return activityLabel(ev);
}

/** The phrase for a tool the orchestrator just started. */
export function toolPhrase(tool: string): string {
  return TOOL_PHRASES[tool] || tool.replace(/_/g, ' ');
}

/** The phrase for what is happening NOW: a tool that has started and not
 *  finished wins over anything the model is doing in between; otherwise the
 *  most recent step. Never a bare "thinking" while research is running. */
export function currentActivity(events: ActivityEvent[]): string {
  const open: ActivityEvent[] = [];
  let lastStep: ActivityEvent | null = null;
  for (const ev of events) {
    if (ev.kind === 'tool_start') open.push(ev);
    else if (ev.kind === 'tool_end') {
      const i = open.map((o) => o.tool).lastIndexOf(ev.tool);
      if (i >= 0) open.splice(i, 1);
    } else if (ev.kind === 'step') lastStep = ev;
  }
  if (open.length) return activityLabel(open[open.length - 1]);
  if (lastStep) return activityLabel(lastStep);
  const last = events[events.length - 1];
  return last ? activityLabel(last) : 'Starting';
}
