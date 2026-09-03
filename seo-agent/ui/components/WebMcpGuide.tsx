'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  CircleDollarSign,
  Eye,
  Pencil,
  Search,
  CircleCheck,
  CircleAlert,
} from 'lucide-react';
import { buildTools, registerWebMcpTools } from '@/lib/webmcp';

/**
 * What this page is for
 * ---------------------
 * SEOstrich registers its tools on the page itself, so whatever assistant the
 * visitor already uses can drive the app. That is invisible: nothing on screen
 * tells you the tools are there, what they are called, or what to say to reach
 * them. This page is the missing half — the contract, written down.
 *
 * The tool list is rendered from the SAME registry the browser registers, so
 * it cannot drift into describing tools that no longer exist. Only the worked
 * examples below are written by hand, because a schema cannot say what a tool
 * is GOOD for.
 */

/** Read-only, but each call is billed by DataForSEO. Worth flagging separately:
 *  "read-only" usually implies "free", and here it does not. */
const BILLED = new Set([
  'seo_check_ai_citations',
  'seo_rerun_cluster_research',
  'seo_propose_cluster',
]);


/** Ordered by how much they show off what the tools make possible, not by how
 *  simple they are. The first four are the ones worth trying first. */
const RECIPES: Array<{ goal: string; say: string; does: string; tools: string[] }> = [
  {
    goal: 'Trust it before you build on it',
    say: 'Audit this strategy. Do the discard reasons hold up, and is any pillar standing on one keyword?',
    does:
      'The assistant reads every cluster with its measured metrics and the reasons on both sides of the cut, checks the run for gaps, and tells you where a pillar is thin (one keyword carrying the volume) or a parked cluster deserved better — with the numbers, not opinions.',
    tools: ['seo_analyze_run', 'seo_list_clusters_all', 'seo_get_keywords', 'seo_check_if_edited'],
  },
  {
    goal: 'Make the strategy fit the business',
    say: 'We do not sell courses and we will never lead with a product name. Drop the courses theme, bring back the one on evaluation, and rebuild the brief.',
    does:
      'Selection is the person’s call. The assistant parks the cluster with your reason, promotes the parked one, and rebuilds the brief so the six pieces follow the new selection. Every change is logged with who and why; the report shows an "edited" badge and can be reset to as-produced.',
    tools: ['seo_discard_cluster', 'seo_promote_cluster', 'seo_regenerate_brief', 'seo_get_governance_history'],
  },
  {
    goal: 'Chase a keyword that could become a head term',
    say: '"evaluation harness" has volume and almost no difficulty. Could it carry a theme of its own? Research it and tell me what it pulls in.',
    does:
      'One scoped DataForSEO lookup on that topic: the phrases people search around it, with real volume, difficulty and CPC. The assistant reads the result against the existing clusters and says whether it stands on its own or belongs inside one. Nothing else in the run changes; the proposal is logged and reversible.',
    tools: ['seo_propose_cluster', 'seo_get_keywords', 'seo_list_clusters_all'],
  },
  {
    goal: 'Decide with little information',
    say: 'The eval theme has only three keywords. Before we commit a writer, is there more demand around it, and who owns it today?',
    does:
      'The assistant refreshes that one cluster (one paid call, in place), re-reads its keywords, and checks the competitor map for who ranks where. You get a yes or no with the evidence: enough demand for a hub, or one good article and move on.',
    tools: ['seo_rerun_cluster_research', 'seo_get_keywords', 'seo_get_stage_artifact'],
  },
  {
    goal: 'See who you are really up against',
    say: 'Add mindtheproduct.com to the competitor map. What does it rank for that we have nothing on?',
    does:
      'A competitor the run did not check joins the map with the keywords it ranks for in your market. The assistant reads it against the universe and names the gaps: what they own that none of the selected themes cover.',
    tools: ['seo_research_competitor', 'seo_get_stage_artifact', 'seo_get_keyword_clusters'],
  },
  {
    goal: 'Know what to write first, and for whom',
    say: 'Which piece should we write first, what question does it answer, and who answers that question on Google today?',
    does:
      'The brief already holds the order: the pillar to build first with its reasons, six pieces each answering a question Google shows under People also ask, and the page that answers it today. The assistant reads it and turns it into a writer’s starting point.',
    tools: ['seo_get_brief', 'seo_get_content_calendar', 'seo_get_content_pillars'],
  },
  {
    goal: 'Be the answer AI engines lift',
    say: 'On our topics, what do people actually ask, who gets cited by AI answers, and is any of it winnable for a site nobody cites yet?',
    does:
      'From the AI-visibility report: the questions AI engines already answer, the sites they cite with their authority, what share of the answer space is open, and where your own site stands today. The assistant ranks the openings and says which are realistic.',
    tools: ['seo_get_ai_citability', 'seo_check_ai_citations'],
  },
  {
    goal: 'Hand it to someone else without losing the plot',
    say: 'Has anyone changed this since it was produced? Put it back to as-produced and tell me what it looked like.',
    does:
      'Reports are shared. The change history says who did what and why; a reset restores the pipeline’s own selection and keeps the history. Nothing is ever deleted.',
    tools: ['seo_check_if_edited', 'seo_get_governance_history', 'seo_reset_run'],
  },
];

export function WebMcpGuide({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<'tools' | 'uses'>('tools');
  // 'unknown' until checked; then whether this browser exposes WebMCP at all,
  // and whether our registration went through.
  const [status, setStatus] = useState<'unknown' | 'registered' | 'unavailable' | 'failed'>('unknown');

  useEffect(() => {
    const w = window as any;
    const available = !!(w.document?.modelContext || w.navigator?.modelContext);
    if (!available) {
      setStatus('unavailable');
      return;
    }
    registerWebMcpTools()
      .then((ok) => setStatus(ok ? 'registered' : 'failed'))
      .catch(() => setStatus('failed'));
  }, []);

  // Rendered from the live registry: if a tool is removed from the app, it
  // disappears from this page too.
  const tools = useMemo(() => {
    try {
      return buildTools();
    } catch {
      return [];
    }
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return tools;
    return tools.filter(
      (t: any) =>
        t.name.toLowerCase().includes(q) ||
        (t.title || '').toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q),
    );
  }, [tools, query]);

  const readCount = tools.filter((t: any) => t.annotations?.readOnlyHint).length;

  return (
    <div className="fixed inset-x-0 bottom-0 top-16 bg-surface-50 z-40 overflow-y-auto">

      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
        <h1 className="text-2xl sm:text-3xl font-display text-primary-700">
          SEOstrich has full WebMCP support
        </h1>
        <p className="mt-4 text-gray-700 leading-relaxed">
          Every decision this app makes is on the page as a tool. That lets the assistant you
          already use — in your browser, in your editor — read the working behind a strategy,
          argue with it, change it, and rebuild the plan, while you watch. No API key, no
          export, no copy-paste: {tools.length} tools, registered on this page, working on the
          artefact you are looking at.
        </p>
        <p className="mt-3 text-gray-700 leading-relaxed">
          Two ways in, two graphs: <strong>Create SEO strategy</strong> and <strong>Analyse AI
          visibility</strong>, each behind a short questionnaire that composes the brief. The
          orchestrator only routes; the graphs do the work; the tools below read, audit, edit and
          reset what they produced.
        </p>

        {/* ---- is it live here? ---- */}
        {status === 'registered' && (
          <div className="mt-6 flex items-start gap-3 bg-green-50 border border-green-200 rounded-xl px-4 py-3">
            <CircleCheck className="w-5 h-5 text-green-700 shrink-0 mt-0.5" />
            <div className="text-sm text-green-900">
              <strong>Live in this browser.</strong> All {tools.length} tools are
              registered on this page right now — your assistant can call them.
            </div>
          </div>
        )}
        {status === 'unavailable' && (
          <div className="mt-6 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
            <div className="flex items-start gap-3">
              <CircleAlert className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
              <div className="text-sm text-amber-900">
                <strong>This browser does not expose WebMCP</strong>, so nothing on
                this page is registered yet. The app itself works as usual. To
                try the tools:
              </div>
            </div>
            <ol className="mt-3 ml-8 space-y-1.5 text-sm text-amber-900 list-decimal">
              <li>
                <strong>Google Chrome:</strong> open{' '}
                <code className="font-mono bg-white/70 px-1.5 py-0.5 rounded border border-amber-200">chrome://flags/#enable-webmcp-testing</code>
                , set it to <em>Enabled</em>, relaunch, then reopen this page.
              </li>
              <li>
                <strong>ChatGPT&apos;s in-app browser:</strong> open this URL there —
                WebMCP works natively, no flag needed.
              </li>
              <li>Then ask your assistant any of the prompts below.</li>
            </ol>
          </div>
        )}
        {status === 'failed' && (
          <div className="mt-6 flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
            <CircleAlert className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
            <div className="text-sm text-amber-900">
              <strong>WebMCP is available here, but registration did not complete.</strong>{' '}
              Reload the page; if it persists, the browser console will say which tool was refused.
            </div>
          </div>
        )}

        {/* ---- two tabs ---- */}
        <div className="mt-10 border-b border-surface-300 flex gap-6">
          {([
            ['tools', 'WebMCP tools', 'what your assistant can do'],
            ['uses', 'Example use cases', 'how to make the most of WebMCP and SEOstrich'],
          ] as const).map(([id, label, sub]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`pb-3 -mb-px text-left border-b-2 transition-colors ${
                tab === id ? 'border-primary-500 text-primary-700' : 'border-transparent text-gray-500 hover:text-gray-800'
              }`}
            >
              <div className="text-sm font-semibold">{label}</div>
              <div className="text-xs text-gray-400">{sub}</div>
            </button>
          ))}
        </div>

        {tab === 'uses' && (<>
        <p className="mt-6 text-sm text-gray-500 mb-5">
          Each of these is a business question, not a tool. Open a report, say it to your
          assistant, and it picks the tools itself — often several, in sequence — to get you
          an answer with the numbers behind it.
        </p>

        <ol className="space-y-4">
          {RECIPES.map((r, i) => (
            <li
              key={i}
              className="bg-white border border-surface-300 rounded-xl p-4 sm:p-5 shadow-sm"
            >
              <div className="flex gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-secondary-100 text-primary-600 text-xs font-semibold flex items-center justify-center">
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-primary-700 mb-1">{r.goal}</div>
                  <p className="text-gray-800 font-medium leading-snug">
                    &ldquo;{r.say}&rdquo;
                  </p>
                  <p className="mt-2 text-sm text-gray-600 leading-relaxed">{r.does}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {r.tools.map((t) => (
                      <code
                        key={t}
                        className="text-xs bg-surface-200 text-gray-600 px-2 py-0.5 rounded font-mono"
                      >
                        {t}
                      </code>
                    ))}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ol>
        </>)}

        {tab === 'tools' && (<>
        <p className="mt-6 text-sm text-gray-500 mb-4">
          Rendered from the same registry the page registers, so this list
          cannot drift from the code.
          {status === 'registered' && ' Every tool below is live in this browser.'}
          {status === 'unavailable' && ' None are active in this browser yet — see above.'}
        </p>

        <div className="relative mb-5">
          <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter tools…"
            className="w-full pl-9 pr-3 py-2 bg-white border border-surface-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-200"
          />
        </div>

        {filtered.length === 0 && (
          <p className="text-sm text-gray-500 py-6 text-center">
            {tools.length === 0
              ? 'The tool registry could not be read in this browser.'
              : 'Nothing matches that filter.'}
          </p>
        )}

        <div className="space-y-3">
          {filtered.map((t: any) => {
            const readOnly = !!t.annotations?.readOnlyHint;
            const billed = BILLED.has(t.name);
            return (
              <div
                key={t.name}
                className="bg-white border border-surface-300 rounded-xl p-4 sm:p-5 shadow-sm"
              >
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <code className="text-sm font-mono text-primary-700">{t.name}</code>
                  <span
                    className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full ${
                      readOnly
                        ? 'bg-surface-200 text-gray-600'
                        : 'bg-secondary-100 text-primary-700'
                    }`}
                  >
                    {readOnly ? <Eye className="w-3 h-3" /> : <Pencil className="w-3 h-3" />}
                    {readOnly ? 'reads' : 'changes the run'}
                  </span>
                  {billed && (
                    <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                      <CircleDollarSign className="w-3 h-3" />
                      costs a lookup
                    </span>
                  )}
                </div>
                <p className="text-sm font-medium text-gray-800">{t.title}</p>
                <p className="mt-1.5 text-sm text-gray-600 leading-relaxed">{t.description}</p>
              </div>
            );
          })}
        </div>

        </>)}

        <p className="mt-10 text-xs text-gray-500 leading-relaxed">
          Tools are registered on <code className="font-mono">document.modelContext</code>{' '}
          (falling back to <code className="font-mono">navigator.modelContext</code>) once
          you are signed in. Registration code:{' '}
          <code className="font-mono">ui/lib/webmcp.ts</code>.
        </p>
      </div>
    </div>
  );
}
