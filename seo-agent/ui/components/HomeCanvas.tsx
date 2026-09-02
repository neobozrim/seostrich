'use client';

import React, { useEffect, useState } from 'react';
import { Pin, PinOff, Send, MoreHorizontal, Archive, ArchiveRestore, FolderArchive, ArrowLeft } from 'lucide-react';
import { getRuns, pinRun, archiveRun } from '@/lib/api';
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
  // The report type is its own chip on the card; keep the line to the
  // domain and the market.
  const p = (run.project || '').replace(/\s*\u00b7\s*(SEO content strategy|Content strategy|AI visibility)/i, '').replace(/^(SEO content strategy|Content strategy|AI visibility)\s*\u00b7\s*/i, '').trim();
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

function whenCreated(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export function HomeCanvas({ onOpenRun, onStartChat }: Props) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  // The archive is the same canvas with a different ground and heading.
  const [showArchive, setShowArchive] = useState(false);
  const [menuFor, setMenuFor] = useState<string | null>(null);

  const toggleArchive = async (run: RunSummary) => {
    const next = !run.archived;
    setMenuFor(null);
    setRuns((prev) => ordered((prev || []).map((r) => (r.id === run.id ? { ...r, archived: next, pinned: next ? false : r.pinned } : r))));
    try {
      await archiveRun(run.id, next);
    } catch {
      setRuns((prev) => ordered((prev || []).map((r) => (r.id === run.id ? { ...r, archived: !next } : r))));
    }
  };
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

  const active = (runs || []).filter((r) => !r.archived);
  const archived = (runs || []).filter((r) => r.archived);
  const shown = showArchive ? archived : active;
  const empty = runs !== null && active.length === 0 && !showArchive;

  return (
    <div className={`relative min-h-[calc(100vh-4rem)] ${showArchive ? 'bg-surface-200' : ''}`}>
      {/* The ostrich, peeking in from the bottom-left. Decorative: content
          flows over it, and it never intercepts a click. */}
      {peekOk && !empty && !showArchive && (
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
                className="w-full resize-none rounded-xl border-2 border-surface-300 bg-white px-4 py-3 pr-12 text-base focus:outline-none focus:border-action-300"
              />
              <button
                onClick={() => onStartChat(draft)}
                aria-label="Start"
                className="absolute bottom-3 right-3 p-2 rounded-lg bg-action-300 text-primary-700 hover:bg-action-400 hover:text-white transition"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {showArchive && (
          <div className="mb-5 flex items-center gap-3">
            <button onClick={() => setShowArchive(false)} className="p-1.5 rounded-lg hover:bg-white/60" title="Back">
              <ArrowLeft className="w-4 h-4 text-gray-600" />
            </button>
            <h1 className="font-display text-2xl text-primary-700">Archive</h1>
            <span className="text-sm text-gray-500">{archived.length} artefact{archived.length === 1 ? '' : 's'}</span>
          </div>
        )}

        {runs && (shown.length > 0 || (!showArchive && archived.length > 0)) && (
          <div className={`grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 ${showArchive ? '' : 'sm:pl-24 lg:pl-56'}`}>
            {showArchive && shown.length === 0 && (
              <div className="text-sm text-gray-500">Nothing archived.</div>
            )}
            {shown.map((run) => {
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
                      {run.pinned && <Pin className="w-3.5 h-3.5 text-primary-400" />}
                      {live && (
                        <span className="flex items-center gap-1 text-[11px] text-action-500">
                          <span className="w-1.5 h-1.5 rounded-full bg-action-400 animate-pulse" />
                          live
                        </span>
                      )}
                      <span className="relative">
                        <span
                          role="button"
                          tabIndex={0}
                          aria-label="More"
                          onClick={(e) => { e.stopPropagation(); setMenuFor(menuFor === run.id ? null : run.id); }}
                          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); setMenuFor(menuFor === run.id ? null : run.id); } }}
                          className="p-1 rounded hover:bg-surface-100 text-gray-300 hover:text-gray-700"
                        >
                          <MoreHorizontal className="w-4 h-4" />
                        </span>
                        {menuFor === run.id && (
                          <span
                            className="absolute right-0 top-6 z-20 w-40 bg-white border border-surface-300 rounded-lg shadow-lg py-1 text-sm"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {!run.archived && (
                              <span role="button" onClick={() => { setMenuFor(null); togglePin(run); }} className="flex items-center gap-2 px-3 py-1.5 hover:bg-surface-100 cursor-pointer">
                                {run.pinned ? <PinOff className="w-3.5 h-3.5" /> : <Pin className="w-3.5 h-3.5" />}
                                {run.pinned ? 'Unpin' : 'Pin to top'}
                              </span>
                            )}
                            <span role="button" onClick={() => toggleArchive(run)} className="flex items-center gap-2 px-3 py-1.5 hover:bg-surface-100 cursor-pointer">
                              {run.archived ? <ArchiveRestore className="w-3.5 h-3.5" /> : <Archive className="w-3.5 h-3.5" />}
                              {run.archived ? 'Restore' : 'Archive'}
                            </span>
                          </span>
                        )}
                      </span>
                    </span>
                  </div>
                  {subtitleOf(run) && (
                    <div className="text-sm text-gray-500 mt-1 line-clamp-2">{subtitleOf(run)}</div>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-400">
                    {run.flow && (
                      <span className="px-2 py-0.5 rounded bg-accent-50 text-accent-600 border border-accent-100 font-semibold">{run.flow}</span>
                    )}
                    {run.created && <span>{whenCreated(run.created)}</span>}
                    <span>{run.stages} stage{run.stages === 1 ? '' : 's'}</span>
                  </div>
                </button>
              );
            })}
            {!showArchive && archived.length > 0 && (
              <button
                onClick={() => setShowArchive(true)}
                className="text-left rounded-xl border border-dashed border-surface-400 bg-surface-100/80 p-4 hover:border-gray-500 hover:bg-surface-100 transition flex items-center gap-3"
              >
                <FolderArchive className="w-6 h-6 text-gray-500 shrink-0" />
                <div>
                  <div className="font-display text-base text-gray-700">Archive</div>
                  <div className="text-xs text-gray-400">{archived.length} artefact{archived.length === 1 ? '' : 's'}</div>
                </div>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
