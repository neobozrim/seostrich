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

type Recipe = {
  say: string;
  does: string;
  tools: string[];
};

/** Ordered by how much they show off what the tools make possible, not by how
 *  simple they are. The first four are the ones worth trying first. */
const RECIPES: Recipe[] = [
  {
    say: 'Audit this SEO strategy for me. Do the discard reasons actually hold up?',
    does:
      'Your assistant pulls every cluster — kept AND dropped — with the measured metrics behind each decision, and argues with the reasoning instead of taking it on trust. This is the thing a static report cannot do.',
    tools: ['seo_list_clusters_all', 'seo_analyze_run'],
  },
  {
    say: 'Drop the cluster about courses — we do not sell courses — and bring back the one on building AI products.',
    does:
      'Changes the strategy in place, both ways, with your reason recorded. The dropped cluster is parked, not deleted, so nothing here is a one-way door.',
    tools: ['seo_discard_cluster', 'seo_promote_cluster'],
  },
  {
    say: 'We are not going after prompt engineering. Re-shape the strategy around evaluation and knowledge graphs instead.',
    does:
      'A goal stated in one sentence, applied across the whole selection: your assistant drops what conflicts with it and researches the topics that are missing, pulling real volume and difficulty for the new ones.',
    tools: ['seo_discard_cluster', 'seo_propose_cluster'],
  },
  {
    say: 'Which of these keywords could we realistically rank for this year?',
    does:
      'Gets the flat keyword table — volume, difficulty, CPC, intent, cluster — and lets your assistant apply its own threshold rather than ours. Filter, rank, cross-tabulate: it is your analysis, on our data.',
    tools: ['seo_get_keywords'],
  },
  {
    say: 'Is any cluster carried by a single keyword?',
    does:
      'A concentration check no report thought to include. One 8,000-volume term next to nine dead ones is not a cluster, and the numbers to prove it are already there.',
    tools: ['seo_get_keywords', 'seo_list_clusters_all'],
  },
  {
    say: 'What do people actually ask about these topics, and is AI already answering them?',
    does:
      'Returns AI search demand per topic, which sources ChatGPT and Google AI currently cite, how much of the answer space is still unclaimed, and the real People-also-ask questions — so you write against questions users ask, not ones we guessed.',
    tools: ['seo_get_ai_citability'],
  },
  {
    say: 'Check whether competitor.com gets cited by AI answers, and what for.',
    does:
      'Far more concrete than a keyword list: the actual answers that quote them, and who is quoted alongside. Run it on your own domain too — a new site returns zero, which is the honest baseline.',
    tools: ['seo_check_ai_citations'],
  },
  {
    say: 'What did someone already decide here before I change anything?',
    does:
      'The full record of promotions, discards and proposals, in order, each with its reason and whether it came from the agent, an outside assistant, or a person. Stops one assistant quietly undoing another judgement call.',
    tools: ['seo_get_governance_history'],
  },
  {
    say: 'Is this run trustworthy, or is something missing?',
    does:
      'A deterministic health check — no model, no API calls: which stages are absent, whether it errored or was stopped, whether the selection was ever curated. Run it before you trust a report you did not watch being made.',
    tools: ['seo_analyze_run'],
  },
  {
    say: 'This cluster looks stale. Refresh just that one.',
    does:
      'Re-researches a single cluster and merges the new data in, without re-running — or re-billing — the other five.',
    tools: ['seo_rerun_cluster_research'],
  },
  {
    say: 'Turn the selected pillars into a brief for the writer.',
    does:
      'Pulls the pillars, the calendar and the questions people ask, and your assistant writes the brief in its own format — because the useful last step is always specific to you.',
    tools: ['seo_get_content_pillars', 'seo_get_content_calendar', 'seo_get_ai_citability'],
  },
  {
    say: 'I disagree with how this weighted commercial intent — note that for the team.',
    does:
      'Records a judgement on the run without changing it. For things an assistant should raise rather than decide.',
    tools: ['seo_submit_feedback'],
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
          Open an artefact first, then say any of these to your assistant. It picks
          the tools itself — you never name them.
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
                  <p className="text-gray-800 font-medium leading-snug">
                    &ldquo;{r.say}&rdquo;
                  </p>
                  <p className="mt-2 text-sm text-gray-600 leading-relaxed">{r.does}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {r.tools.map((t) => (
                      <code
                        key={t}
                        className="text-[11px] bg-surface-200 text-gray-600 px-2 py-0.5 rounded font-mono"
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
