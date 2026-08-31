import { ActivityEvent } from '../types';

const TOOL_LABELS: Record<string, string> = {
  extract_seeds: 'extracting seeds',
  pull_universe: 'researching keyword universe (DataForSEO)',
  keyword_suggestions: 'fetching keyword stats',
  related_keywords: 'expanding related keywords',
  cluster_keywords: 'creating clusters',
  validate_clusters: 'reviewing cluster coherence',
  score_clusters: 'scoring clusters',
  select_clusters: 'selecting top clusters',
  ai_citability_brief: 'building AI-citability brief',
  recommend_pillars: 'recommending pillars',
  plan_calendar: 'planning calendar',
  submit_deliverable: 'recording deliverable',
  list_clusters_all: 'listing clusters',
  promote_cluster: 'promoting cluster',
  discard_cluster: 'discarding cluster',
  propose_cluster: 'proposing new cluster',
  web_search: 'searching the web',
  seo_agent: 'SEO agent',
};

export function activityLabel(ev: ActivityEvent): string {
  if (ev.kind === 'llm_round') return 'Thinking';
  if (ev.kind === 'answer') return 'Writing answer';
  if (ev.kind === 'step') return ev.detail || 'working';
  const name = TOOL_LABELS[ev.tool || ''] || ev.tool || 'working';
  if (ev.kind === 'tool_start') return `${name}…`;
  if (ev.kind === 'tool_end') return `${ev.success ? '✓' : '✗'} ${name}`;
  return name;
}

export function activityLine(ev: ActivityEvent): string {
  return activityLabel(ev);
}
