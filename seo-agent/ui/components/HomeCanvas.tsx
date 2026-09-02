'use client';

import React, { useEffect, useState } from 'react';
import { Pin, PinOff, Send } from 'lucide-react';
import { getRuns, pinRun } from '@/lib/api';
import { RunSummary } from '@/types';

/**
 * The home is the artefacts. Nothing else.
 *
 * There used to be a second column ("Ask for anything") and a row of service
 * cards ("Content strategy", "AI visibility"). Together they gave a visitor
 * three doors into the same product, and the service cards led to an
 * intermediate state that looked like a form. Now: your artefacts as cards,
 * one blue + to make another, and when there is nothing yet, the one thing a
 * new visitor needs — somewhere to type.
 */

function ordered(runs: RunSummary[]): RunSummary[] {
  const pinned = runs.filter((r) => r.pinned);
  const rest = runs.filter((r) => !r.pinned);
  const rank = (r: RunSummary) =>
    r.status === 'running' ? 0 : r.status === 'complete' || r.status === 'done' ? 1 : 2;
  rest.sort((a, b) => rank(a) - rank(b) || (b.modified || 0) - (a.modified || 0));
  return [...pinned, ...rest];
}

// A run whose title is a chat prompt gets its project as the name; the
// prompt becomes the subtitle. Test fixtures with one-letter names are hidden.
// A title that reads like a name ("Product Pirates Club") leads; a title that
// reads like the prompt that produced the run ("Global English audience,
// target the United States. Build the strategy.") becomes the subtitle and
// the project (usually the domain) leads instead.
function looksLikeName(t: string): boolean {
  return t.length > 0 && t.length <= 48 && !/[.!?]$/.test(t) && !/(build|run|want|target|audience)/i.test(t);
}
function nameOf(run: RunSummary): string {
  const t = (run.title || '').trim();
  const p = (run.project || '').trim();
  if (looksLikeName(t)) return t;
  if (p && p.toLowerCase() !== 'chat pipeline') return p;
  return t || run.id;
}
function subtitleOf(run: RunSummary): string {
  const t = (run.title || '').trim();
  const p = (run.project || '').trim();
  const name = nameOf(run);
  const internal = p.toLowerCase() === 'chat pipeline';
  if (name === t) return p && p !== t && !internal ? p : '';
  return t && t !== name ? t : '';
}
function isFixture(run: RunSummary): boolean {
  if (run.pinned) return false;
  if (/^(test|diag)-/.test(run.id)) return true;
  const p = (run.project || '').trim();
  return nameOf(run).length <= 2 || p.length <= 1;
}

interface Props {
  onOpenRun: (runId: string) => void;
  onStartChat: (prompt?: string) => void;
}

export function HomeCanvas({ onOpenRun, onStartChat }: Props) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [draft, setDraft] = useState('');
  const [peekOk, setPeekOk] = useState(true);
  const [runOk, setRunOk] = useState(true);

  const togglePin = async (run: RunSummary) => {
    const next = !run.pinned;
    setRuns((prev) => ordered((prev || []).map((r) => (r.id === run.id ? { ...r, pinned: next } : r))));
    try {
      await pinRun(run.id, next);
    } catch {
      setRuns((prev) => ordered((prev || []).map((r) => (r.id === run.id ? { ...r, pinned: !next } : r))));
    }
  };

  useEffect(() => {
    getRuns()
      .then((r) => setRuns(ordered((r || []).filter((x: RunSummary) => !isFixture(x)))))
      .catch(() => setRuns([]));
  }, []);

  const empty = runs !== null && runs.length === 0;

  return (
    <div className="relative min-h-full">
      {/* The ostrich, peeking in from the bottom-left. Decorative: content
          flows over it, and it never intercepts a click. */}
      {peekOk && !empty && (
        <img
          src="/brand/ostrich-peek.png"
          alt=""
          aria-hidden
          onError={() => setPeekOk(false)}
          className="pointer-events-none select-none fixed left-0 bottom-0 w-[18rem] sm:w-[24rem] lg:w-[30rem] opacity-90 -translate-x-[22%] translate-y-[14%]"
        />
      )}

      <div className="relative w-full max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
        {runs === null && <div className="text-sm text-gray-400">Loading…</div>}

        {empty && (
          <div className="flex flex-col items-center text-center pt-2 sm:pt-6">
            {runOk && (
              <img
                src="/brand/ostrich-run.png"
                alt=""
                aria-hidden
                onError={() => setRunOk(false)}
                className="w-40 sm:w-52 h-auto mb-4"
              />
            )}
            <h1 className="font-display text-4xl sm:text-5xl tracking-[0.18em] text-primary-700">
              GET FOUND
            </h1>
            <p className="mt-3 text-gray-500 max-w-md">
              Tell it what you do and where. It builds the strategy in front of you.
            </p>
            <div className="relative mt-8 w-full max-w-xl">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    onStartChat(draft);
                  }
                }}
                rows={3}
                placeholder="My business is…"
                className="w-full resize-none rounded-xl border-2 border-surface-300 bg-white px-4 py-3 pr-12 text-base focus:outline-none focus:border-action-400"
              />
              <button
                onClick={() => onStartChat(draft)}
                aria-label="Start"
                className="absolute bottom-3 right-3 p-2 rounded-lg bg-action-400 text-white hover:bg-action-500 transition"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {runs && runs.length > 0 && (
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 sm:pl-24 lg:pl-56">
            {runs.map((run) => {
              const live = run.status === 'running';
              return (
                <button
                  key={run.id}
                  onClick={() => onOpenRun(run.id)}
                  className="group text-left rounded-xl border border-surface-300 bg-white/95 backdrop-blur p-4
                             hover:border-gray-400 hover:shadow-sm transition"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-display text-base text-primary-700 truncate">{nameOf(run)}</span>
                    <span className="flex items-center gap-1 shrink-0">
                      {live && (
                        <span className="flex items-center gap-1 text-[11px] text-action-500">
                          <span className="w-1.5 h-1.5 rounded-full bg-action-400 animate-pulse" />
                          live
                        </span>
                      )}
                      <span
                        role="button"
                        tabIndex={0}
                        aria-label={run.pinned ? 'Unpin' : 'Pin'}
                        title={run.pinned ? 'Pinned — always first' : 'Pin so it is always first'}
                        onClick={(e) => { e.stopPropagation(); togglePin(run); }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); togglePin(run); }
                        }}
                        className={`p-1 rounded hover:bg-surface-100 ${run.pinned ? 'text-primary-400' : 'text-gray-300 hover:text-gray-600'}`}
                      >
                        {run.pinned ? <Pin className="w-3.5 h-3.5" /> : <PinOff className="w-3.5 h-3.5" />}
                      </span>
                    </span>
                  </div>
                  {subtitleOf(run) && (
                    <div className="text-sm text-gray-500 mt-1 line-clamp-2">{subtitleOf(run)}</div>
                  )}
                  <div className="text-xs text-gray-400 mt-2">
                    {run.stages} stage{run.stages === 1 ? '' : 's'}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
