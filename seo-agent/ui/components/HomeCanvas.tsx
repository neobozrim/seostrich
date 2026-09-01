'use client';

import React, { useEffect, useState } from 'react';
import { ArrowRight, Send, Workflow, Target, Sparkles, Lock, Pin, PinOff } from 'lucide-react';
import { getRuns, getFlows, pinRun, FlowCard, FlowCatalog } from '@/lib/api';
import { RunSummary } from '@/types';

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  target: Target,
  sparkles: Sparkles,
  workflow: Workflow,
};

const STARTERS: Record<string, string> = {
  keyword_strategy: 'I want a content strategy. My business is: ',
  geo_demand:
    'I want to know how AI engines answer questions in my space. The topics are: ',
};

// Featured only: the homepage is a canvas of work worth returning to, not an
// audit log. Completed runs first, and only a handful.
const FEATURED_LIMIT = 6;

function featured(runs: RunSummary[]): RunSummary[] {
  // The API returns pinned-first, then newest. A pinned run is a deliberate
  // choice about what someone should see, so it always survives the cut —
  // only the unpinned tail competes for the remaining slots.
  const pinned = runs.filter((r) => r.pinned);
  const rest = runs.filter((r) => !r.pinned);
  const rank = (r: RunSummary) =>
    r.status === 'complete' || r.status === 'done' ? 0 : r.status === 'running' ? 1 : 2;
  rest.sort((a, b) => rank(a) - rank(b) || (b.modified || 0) - (a.modified || 0));
  return [...pinned, ...rest].slice(0, Math.max(FEATURED_LIMIT, pinned.length));
}

interface Props {
  onOpenRun: (runId: string) => void;
  onStartChat: (prompt?: string) => void;
}

export function HomeCanvas({ onOpenRun, onStartChat }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [catalog, setCatalog] = useState<FlowCatalog | null>(null);
  const [draft, setDraft] = useState('');

  // Optimistic: the canvas re-sorts immediately, and reverts if the call fails.
  const togglePin = async (run: RunSummary) => {
    const next = !run.pinned;
    setRuns((prev) =>
      featured(prev.map((r) => (r.id === run.id ? { ...r, pinned: next } : r)))
    );
    try {
      await pinRun(run.id, next);
    } catch {
      setRuns((prev) =>
        featured(prev.map((r) => (r.id === run.id ? { ...r, pinned: !next } : r)))
      );
    }
  };

  useEffect(() => {
    const ctrl = new AbortController();
    getRuns().then((r) => setRuns(featured(r || []))).catch(() => setRuns([]));
    getFlows(ctrl.signal).then(setCatalog).catch(() => setCatalog(null));
    return () => ctrl.abort();
  }, []);

  return (
    <div className="w-full max-w-5xl mx-auto px-6 py-10">
      <div className="grid gap-8 lg:grid-cols-[1fr_20rem] items-start">
        {/* Projects — the canvas itself */}
        <div>
          <h2 className="text-sm font-medium text-gray-700 mb-3">Your work</h2>
          {runs.length === 0 ? (
            <p className="text-sm text-gray-400">
              Nothing here yet. Start a flow and it will show up as a page you can
              come back to.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {runs.map((run) => (
                <button
                  key={run.id}
                  onClick={() => onOpenRun(run.id)}
                  className="group text-left rounded-lg border border-surface-300 bg-white p-4
                             hover:border-gray-400 hover:shadow-sm transition"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium text-gray-900 truncate">
                      {run.project || run.id}
                    </span>
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label={run.pinned ? 'Unpin this run' : 'Pin this run'}
                      title={
                        run.pinned
                          ? 'Pinned — always shown first'
                          : 'Pin so this is always shown first'
                      }
                      onClick={(e) => {
                        e.stopPropagation();
                        togglePin(run);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          e.stopPropagation();
                          togglePin(run);
                        }
                      }}
                      className={`p-1 rounded flex-shrink-0 hover:bg-surface-100 ${
                        run.pinned ? 'text-primary-400' : 'text-gray-300 hover:text-gray-600'
                      }`}
                    >
                      {run.pinned ? <Pin className="w-3.5 h-3.5" /> : <PinOff className="w-3.5 h-3.5" />}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full border flex-shrink-0 ${
                        run.status === 'complete' || run.status === 'done'
                          ? 'bg-green-50 border-green-300 text-green-800'
                          : run.status === 'running'
                          ? 'bg-blue-50 border-blue-300 text-blue-800'
                          : 'bg-surface-100 border-surface-300 text-gray-600'
                      }`}
                    >
                      {run.status}
                    </span>
                  </div>
                  {run.title && (
                    <div className="text-sm text-gray-500 mt-1 line-clamp-2">
                      {run.title}
                    </div>
                  )}
                  <div className="text-xs text-gray-400 mt-2 flex items-center gap-1
                                  group-hover:text-gray-700">
                    {run.stages} stage{run.stages === 1 ? '' : 's'}
                    <ArrowRight className="w-3 h-3" />
                  </div>
                </button>
              ))}
            </div>
          )}

          {catalog?.flows?.length ? (
            <>
              <h2 className="text-sm font-medium text-gray-700 mt-8 mb-3">Start something</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {catalog.flows.map((flow: FlowCard) => {
                  const Icon = ICONS[flow.icon] || Workflow;
                  return (
                    <button
                      key={flow.id}
                      onClick={() =>
                        onStartChat(STARTERS[flow.id] ?? `Run the ${flow.label} flow. `)
                      }
                      className="group text-left rounded-lg border border-surface-300 bg-white p-4
                                 hover:border-gray-400 hover:shadow-sm transition"
                    >
                      <div className="flex items-start gap-3">
                        <Icon className="w-5 h-5 mt-0.5 text-gray-500 group-hover:text-gray-900 shrink-0" />
                        <div className="min-w-0">
                          <div className="font-medium text-gray-900">{flow.label}</div>
                          <div className="text-sm text-gray-500">{flow.tagline}</div>
                        </div>
                      </div>
                      {flow.required_inputs.length > 0 && (
                        <div className="mt-3 pt-2 border-t border-surface-200 text-xs text-gray-500">
                          Asks first: {flow.required_inputs.map((i) => i.label).join(' · ')}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
              {catalog.planned?.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="text-xs text-gray-400">Coming next:</span>
                  {catalog.planned.map((p) => (
                    <span
                      key={p.id}
                      className="inline-flex items-center gap-1 text-xs text-gray-400
                                 border border-surface-300 rounded px-2 py-0.5"
                    >
                      <Lock className="w-3 h-3" />
                      {p.label}
                    </span>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Chat lives to the side until it is needed, then it takes over. */}
        <aside className="lg:sticky lg:top-4">
          <div className="rounded-xl border-2 border-primary-400 bg-white p-4 shadow-sm">
            <div className="text-sm font-medium text-gray-900 mb-1">Ask for anything</div>
            <p className="text-xs text-gray-500 mb-3">
              Describe what you need and the agent picks the flow — it will ask for
              your market before spending anything.
            </p>
            <div className="relative">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    onStartChat(draft);
                  }
                }}
                onFocus={() => draft && undefined}
                rows={3}
                placeholder="Start here..."
                className="w-full resize-none rounded-lg border border-surface-300 px-3 py-2 pr-10
                           text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
              />
              <button
                onClick={() => onStartChat(draft)}
                aria-label="Open chat"
                className="absolute bottom-2 right-2 p-1.5 rounded-md bg-primary-400 text-white
                           hover:bg-primary-500 transition"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
