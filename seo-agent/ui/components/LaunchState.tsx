'use client';

import { useState } from 'react';
import { Square } from 'lucide-react';

/**
 * The moment between "Go" and the artefact existing.
 *
 * This IS the report's layout with nothing in it yet: the same chrome, the
 * same "Your request" row, the same pinned composer. The request rises into
 * place while the ostrich crosses the screen; when the first stage lands,
 * RunView takes over in the same position and the eye sees nothing move.
 */
export function LaunchState({
  prompt,
  status,
  answering,
  onSteer,
  onStop,
}: {
  prompt: string;
  status?: string;
  answering?: boolean;
  onSteer?: (text: string) => void;
  onStop?: () => void;
}) {
  const [draft, setDraft] = useState('');
  const firstLine = prompt.split('\n')[0].slice(0, 140);
  const submit = () => {
    if (!draft.trim() || !onSteer) return;
    onSteer(draft.trim());
    setDraft('');
  };
  return (
    <div className="fixed inset-x-0 bottom-0 top-16 z-40 bg-surface-50 flex flex-col overflow-hidden">
      {/* The runner and its trail. Decorative; nothing sits under it for long. */}
      <div className="pointer-events-none select-none" aria-hidden>
        <div className="launch-streak" />
        {[0.12, 0.22, 0.38].map((o, i) => (
          <img
            key={i}
            src="/brand/ostrich-run.png"
            alt=""
            className="launch-ghost"
            style={{ opacity: o, animationDelay: `${(3 - i) * 110}ms`, filter: `blur(${(3 - i) * 1.5}px)` }}
          />
        ))}
        <img src="/brand/ostrich-run.png" alt="" className="launch-runner" />
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="launch-prompt max-w-3xl lg:max-w-6xl mx-auto px-6 pt-8">
          <div className="lg:max-w-[48rem]">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-semibold px-2 py-0.5 rounded bg-accent-50 text-accent-600 border border-accent-100">
                Starting
              </span>
              <span className="text-xs text-gray-400">
                {new Date().toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })}
              </span>
            </div>
            <div className="launch-heading h-8 w-3/5 max-w-md rounded-md bg-surface-300" title={firstLine} />

            <details className="mt-4 group bg-surface-100 border border-surface-300 rounded-xl px-4 py-2.5">
              <summary className="cursor-pointer list-none flex items-baseline gap-3 text-sm">
                <span className="text-sm font-semibold text-primary-600 shrink-0">Your request</span>
                <span className="text-gray-600 truncate group-open:hidden flex-1 min-w-0">{firstLine}</span>
                <span className="hidden group-open:block flex-1" />
                <span className="text-sm text-gray-500 shrink-0 ml-auto group-open:hidden">expand ▾</span>
                <span className="text-sm text-gray-500 shrink-0 ml-auto hidden group-open:inline">collapse ▴</span>
              </summary>
              <div className="mt-2 text-sm text-gray-700 whitespace-pre-wrap leading-relaxed max-h-80 overflow-y-auto">{prompt}</div>
            </details>

            <p className="mt-6 text-sm text-gray-800 flex items-center gap-3 pl-1">
              <span className="inline-block w-2 h-2 rounded-full bg-action-500 animate-pulse shrink-0" />
              {(status || (answering ? 'Answering' : 'Reading your request')).replace(/[.…\s]+$/, '')}…
            </p>
          </div>
        </div>
      </div>

      {/* Same composer as the report: pinned, steers while it runs. */}
      <div className="border-t border-surface-300 bg-surface-50/95 backdrop-blur">
        <div className="max-w-3xl lg:max-w-6xl mx-auto px-6 py-3">
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              rows={1}
              placeholder="Steer it — this stops the current step and sends your correction"
              className="flex-1 resize-none rounded-xl border border-surface-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-action-400"
            />
            {onStop && (
              <button onClick={onStop} title="Stop" className="p-2.5 rounded-xl border border-surface-300 bg-white text-gray-600 hover:bg-surface-100">
                <Square className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={submit}
              disabled={!draft.trim()}
              title="Steer"
              className="px-4 py-2.5 rounded-xl bg-action-300 text-primary-700 hover:bg-action-400 hover:text-white text-sm font-semibold disabled:opacity-60 disabled:hover:bg-action-300 disabled:hover:text-primary-700 flex items-center gap-1.5 transition"
            >
              Steer
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
