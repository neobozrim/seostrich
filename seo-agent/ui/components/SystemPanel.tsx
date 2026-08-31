'use client';

import React, { useEffect, useState } from 'react';
import {
  X,
  ChevronDown,
  ChevronRight,
  ListTodo,
  FileText,
  Lightbulb,
  Target,
  Package,
  TrendingUp,
  BookOpen,
  RotateCcw,
  Loader2,
} from 'lucide-react';
import { MemoryState } from '@/types';
import {
  getMemoryFile,
  getImprovements,
  getArtifacts,
  restoreDefaultRuns,
  AuthError,
} from '@/lib/api';

interface SystemPanelProps {
  memory: MemoryState;
  onClose: () => void;
}

function Section({
  title,
  icon: Icon,
  count,
  defaultOpen = false,
  children,
}: {
  title: string;
  icon: any;
  count?: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-white border border-surface-300 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-50 transition-colors text-left"
      >
        <span className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-primary-500" />
          <span className="text-sm font-semibold text-gray-800">{title}</span>
          {count !== undefined && (
            <span className="text-xs text-gray-500 bg-surface-200 px-2 py-0.5 rounded">
              {count}
            </span>
          )}
        </span>
        {open ? (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400" />
        )}
      </button>
      {open && <div className="px-4 pb-4 border-t border-surface-200 pt-3">{children}</div>}
    </div>
  );
}

function EntryList({ items, borderColor }: { items: string[]; borderColor: string }) {
  if (!items.length) {
    return <p className="text-sm text-gray-400 italic">No entries yet</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className={`text-xs p-2 bg-surface-50 rounded border-l-2 ${borderColor}`}>
          {item}
        </li>
      ))}
    </ul>
  );
}

function FileBlock({ filename }: { filename: string }) {
  const [content, setContent] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    getMemoryFile(filename)
      .then((c) => !cancelled && setContent(c))
      .catch(() => !cancelled && setContent(''));
    return () => {
      cancelled = true;
    };
  }, [filename]);
  if (content === null) return <p className="text-xs text-gray-400">Loading…</p>;
  if (!content.trim()) return <p className="text-xs text-gray-400 italic">Empty</p>;
  return (
    <pre className="whitespace-pre-wrap font-mono text-xs text-gray-700 bg-surface-50 p-3 rounded max-h-64 overflow-auto">
      {content}
    </pre>
  );
}

export function SystemPanel({ memory, onClose }: SystemPanelProps) {
  const [improvements, setImprovements] = useState<any[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [restoring, setRestoring] = useState(false);
  const [restoreMsg, setRestoreMsg] = useState<string | null>(null);

  useEffect(() => {
    getImprovements().then(setImprovements).catch(() => setImprovements([]));
    getArtifacts().then(setArtifacts).catch(() => setArtifacts([]));
  }, []);

  const handleRestore = async () => {
    if (!confirm('Reset the example pipeline data back to defaults?')) return;
    setRestoring(true);
    setRestoreMsg(null);
    try {
      const res = await restoreDefaultRuns();
      setRestoreMsg(`Restored ${res.restored?.length || 0} run(s).`);
    } catch (e: any) {
      setRestoreMsg(
        e instanceof AuthError ? 'Not authenticated.' : `Restore failed: ${e?.message || e}`
      );
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* scrim */}
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />

      {/* drawer */}
      <div className="relative w-full max-w-md h-full bg-surface-50 border-l border-surface-300 flex flex-col shadow-xl">
        <div className="sticky top-0 bg-surface-100 border-b border-surface-300 px-4 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-primary-700">System</h2>
            <p className="text-xs text-gray-500">Memory, artifacts &amp; controls</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-surface-200 rounded transition-colors"
            title="Close system panel"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {/* Tasks on top */}
          <Section title="Tasks" icon={ListTodo} count={memory.tasks.length} defaultOpen>
            <EntryList items={memory.tasks} borderColor="border-surface-400" />
          </Section>

          <Section title="Facts" icon={FileText} count={memory.facts.length} defaultOpen>
            <EntryList items={memory.facts} borderColor="border-secondary-300" />
          </Section>

          <Section title="Learnings" icon={Lightbulb} count={memory.learnings.length}>
            <EntryList items={memory.learnings} borderColor="border-accent-400" />
          </Section>

          <Section title="Decisions" icon={Target} count={memory.decisions.length}>
            <EntryList items={memory.decisions} borderColor="border-primary-400" />
          </Section>

          <Section title="Artifacts" icon={Package} count={artifacts.length}>
            {artifacts.length === 0 ? (
              <p className="text-xs text-gray-400 italic">No artifacts yet</p>
            ) : (
              <ul className="space-y-1">
                {artifacts.map((a: any) => (
                  <li
                    key={a.name}
                    className="text-xs flex items-center justify-between bg-surface-50 rounded px-2 py-1.5"
                  >
                    <span className="text-gray-700 truncate">{a.name}</span>
                    <span className="text-gray-400 flex-shrink-0 ml-2">
                      {(a.size / 1024).toFixed(1)} KB
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Run summaries" icon={BookOpen}>
            <FileBlock filename="runs-summaries.md" />
          </Section>

          <Section title="Improvement proposals" icon={TrendingUp} count={improvements.length}>
            {improvements.length === 0 ? (
              <p className="text-xs text-gray-400 italic">No proposals yet</p>
            ) : (
              <div className="space-y-2">
                {improvements.map((imp: any, i: number) => (
                  <div key={i} className="border border-surface-300 rounded-lg p-2">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-gray-800 truncate">
                        {imp.topic}
                      </span>
                      <span
                        className={`px-1.5 py-0.5 text-[10px] rounded flex-shrink-0 ml-2 ${
                          imp.status === 'approved'
                            ? 'bg-green-100 text-green-700'
                            : imp.status === 'rejected'
                              ? 'bg-red-100 text-red-700'
                              : 'bg-accent-100 text-accent-700'
                        }`}
                      >
                        {imp.status || 'pending'}
                      </span>
                    </div>
                    {imp.rationale && (
                      <p className="text-[11px] text-gray-600">{imp.rationale}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Actions */}
          <div className="bg-white border border-surface-300 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-800 mb-1">Example data</h3>
            <p className="text-xs text-gray-500 mb-3">
              Reset the example pipeline back to the shipped default.
            </p>
            <button
              onClick={handleRestore}
              disabled={restoring}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-surface-200 hover:bg-surface-300 rounded-lg text-gray-700 transition-colors disabled:opacity-50"
            >
              {restoring ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RotateCcw className="w-4 h-4" />
              )}
              Restore defaults
            </button>
            {restoreMsg && <p className="text-xs text-gray-600 mt-2">{restoreMsg}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
