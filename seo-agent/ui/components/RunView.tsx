'use client';

import React, { useEffect, useState } from 'react';
import {
  X,
  ChevronDown,
  ChevronRight,
  Send,
  CheckCircle2,
  Circle,
  Sparkles,
  MessageSquare,
  Loader2,
} from 'lucide-react';
import { Run, RunStage, RunFeedback } from '@/types';
import { getRuns, getRun, addRunFeedback, getUsername, AuthError } from '@/lib/api';

interface RunViewProps {
  tasks: string[];
  onClose: () => void;
}

const STAGE_ICONS: Record<string, string> = {
  intake: '📝',
  seeds: '🌱',
  keywords: '🔎',
  clusters: '🧩',
  pillars: '🏛️',
  mix: '🗓️',
};

function ScoreBadge({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return null;
  const tone =
    value >= 80
      ? 'bg-green-100 text-green-700'
      : value >= 60
        ? 'bg-accent-100 text-accent-700'
        : 'bg-surface-200 text-gray-600';
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${tone}`}>
      {value}
    </span>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block px-2 py-0.5 m-0.5 text-xs bg-surface-100 border border-surface-300 rounded-full text-gray-700">
      {children}
    </span>
  );
}

function StageCard({
  stage,
  index,
  isLast,
  children,
}: {
  stage: RunStage;
  index: number;
  isLast: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex gap-4">
      {/* connector rail */}
      <div className="flex flex-col items-center">
        <div
          className={`w-9 h-9 rounded-full flex items-center justify-center text-base flex-shrink-0 ${
            stage.status === 'done'
              ? 'bg-primary-100 border border-primary-300'
              : 'bg-surface-200 border border-surface-300'
          }`}
          title={stage.label}
        >
          {STAGE_ICONS[stage.id] || index + 1}
        </div>
        {!isLast && <div className="w-px flex-1 bg-surface-300 my-1" />}
      </div>

      <div className="flex-1 pb-8 min-w-0">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-medium text-gray-400">
            Step {index + 1}
          </span>
          <h3 className="text-base font-semibold text-gray-900">{stage.label}</h3>
          {stage.status === 'done' ? (
            <CheckCircle2 className="w-4 h-4 text-green-600" />
          ) : (
            <Circle className="w-4 h-4 text-gray-300" />
          )}
        </div>
        <div className="bg-white border border-surface-300 rounded-xl p-4 shadow-sm">
          {children}
        </div>
      </div>
    </div>
  );
}

// --- per-stage artifact renderers ------------------------------------------

function IntakeArtifact({ artifact }: { artifact: Record<string, any> }) {
  const rows: Array<[string, string]> = [
    ['Domain', artifact.domain],
    ['Goal', artifact.goal],
    ['Optimization mix', artifact.optimization_mix],
    ['Locale', artifact.locale ? `#${artifact.locale.location_code} / ${artifact.locale.language_code}` : ''],
  ];
  return (
    <div className="space-y-3">
      {artifact.description && (
        <p className="text-sm text-gray-600">{artifact.description}</p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {rows
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className="text-sm">
              <div className="text-xs text-gray-400">{k}</div>
              <div className="text-gray-800">{v}</div>
            </div>
          ))}
      </div>
      {Array.isArray(artifact.competitors) && artifact.competitors.length > 0 && (
        <div>
          <div className="text-xs text-gray-400 mb-1">Competitors</div>
          <div>{artifact.competitors.map((c: string) => <Chip key={c}>{c}</Chip>)}</div>
        </div>
      )}
    </div>
  );
}

function SeedsArtifact({ artifact }: { artifact: Record<string, any> }) {
  const groups = [
    ['Business seeds', artifact.business_seeds],
    ['Site seeds', artifact.site_seeds],
    ['Competitor seeds', artifact.competitor_seeds],
  ];
  return (
    <div className="space-y-3">
      {groups.map(([label, items]) => (
        <div key={label as string}>
          <div className="text-xs text-gray-400 mb-1">{label as string}</div>
          <div>
            {(items as string[] | undefined)?.length ? (
              (items as string[]).map((s) => <Chip key={s}>{s}</Chip>)
            ) : (
              <span className="text-xs text-gray-400 italic">None</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function KeywordsArtifact({ artifact }: { artifact: Record<string, any> }) {
  const [open, setOpen] = useState(false);
  const keywords: Array<string | Record<string, any>> = artifact.keywords || [];
  const shown = open ? keywords : keywords.slice(0, 24);
  const label = (k: string | Record<string, any>) =>
    typeof k === 'string' ? k : k.keyword || k.query || JSON.stringify(k);
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-700">
          <span className="font-semibold">{artifact.count ?? keywords.length}</span>{' '}
          keywords discovered
        </span>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700"
        >
          {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          {open ? 'Show less' : `Show all ${keywords.length}`}
        </button>
      </div>
      <div>
        {shown.map((k, i) => (
          <Chip key={i}>{label(k)}</Chip>
        ))}
        {!open && keywords.length > 24 && (
          <span className="text-xs text-gray-400"> +{keywords.length - 24} more…</span>
        )}
      </div>
    </div>
  );
}

function ClustersArtifact({ artifact }: { artifact: Record<string, any> }) {
  const [openId, setOpenId] = useState<number | null>(null);
  const clusters = artifact.clusters || [];
  return (
    <div className="space-y-2">
      {clusters.map((c: any, i: number) => (
        <div key={i} className="border border-surface-300 rounded-lg">
          <button
            onClick={() => setOpenId(openId === i ? null : i)}
            className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-50 rounded-lg transition-colors text-left"
          >
            <span className="flex items-center gap-2 min-w-0">
              {openId === i ? (
                <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
              )}
              <span className="text-sm font-medium text-gray-800 truncate">{c.name}</span>
            </span>
            <span className="flex items-center gap-1 flex-shrink-0">
              <ScoreBadge value={c.combined_score} />
            </span>
          </button>
          {openId === i && (
            <div className="px-3 pb-3">
              <div className="flex gap-4 text-xs text-gray-500 mb-2">
                <span>SEO <b>{c.seo_score}</b></span>
                <span>GEO <b>{c.geo_score}</b></span>
                <span>Combined <b>{c.combined_score}</b></span>
              </div>
              {c.rationale && <p className="text-xs text-gray-600 mb-2">{c.rationale}</p>}
              <div>
                {(c.keywords || []).map((k: string, ki: number) => (
                  <Chip key={ki}>{k}</Chip>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function PillarsArtifact({ artifact }: { artifact: Record<string, any> }) {
  const pillars = artifact.pillars || [];
  return (
    <div className="space-y-2">
      {pillars.map((p: any, i: number) => (
        <div key={i} className="border border-surface-300 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-primary-100 text-primary-700">
              P{p.priority}
            </span>
            <span className="px-2 py-0.5 rounded-full text-xs bg-secondary-100 text-secondary-700 capitalize">
              {p.pillar_type}
            </span>
          </div>
          <div className="text-sm font-semibold text-gray-900 mb-1">{p.pillar_title}</div>
          {p.cluster_name && (
            <div className="text-xs text-gray-400 mb-1">Cluster: {p.cluster_name}</div>
          )}
          {p.rationale && <p className="text-xs text-gray-600">{p.rationale}</p>}
        </div>
      ))}
    </div>
  );
}

function MixArtifact({
  artifact,
  feedback,
  onSubmitFeedback,
  submitting,
}: {
  artifact: Record<string, any>;
  feedback: RunFeedback[];
  onSubmitFeedback: (text: string) => void;
  submitting: boolean;
}) {
  const calendar = artifact.calendar || [];
  const [text, setText] = useState('');
  return (
    <div>
      <div className="text-sm text-gray-700 mb-3">
        <span className="font-semibold">{artifact.count ?? calendar.length}</span> planned
        pieces over {calendar.length} weeks
      </div>

      <div className="space-y-2 mb-4">
        {calendar.map((item: any, i: number) => (
          <div key={i} className="border border-surface-300 rounded-lg p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-gray-400">
                Week {item.week} · {item.publish_date} · <span className="capitalize">{item.content_type}</span>
              </span>
            </div>
            <div className="text-sm font-semibold text-gray-900">{item.article_title}</div>
            {item.primary_keyword && (
              <div className="text-xs text-gray-500 mt-1">
                <b>Primary:</b> {item.primary_keyword}
                {item.secondary_keywords?.length ? (
                  <> · <b>Secondary:</b> {item.secondary_keywords.join(', ')}</>
                ) : null}
              </div>
            )}
            {item.angle && <p className="text-xs text-gray-600 mt-1">{item.angle}</p>}
          </div>
        ))}
      </div>

      {/* Feedback composer */}
      <div className="border-t border-surface-300 pt-4">
        <div className="flex items-center gap-2 mb-2">
          <MessageSquare className="w-4 h-4 text-primary-500" />
          <h4 className="text-sm font-semibold text-gray-800">Give feedback on this plan</h4>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. Rebalance the calendar to lean more on the education pillar…"
          rows={3}
          className="w-full px-3 py-2 border border-surface-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400 resize-none bg-white"
        />
        <div className="flex justify-end mt-2">
          <button
            onClick={() => {
              if (!text.trim()) return;
              onSubmitFeedback(text.trim());
              setText('');
            }}
            disabled={submitting || !text.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-primary-400 text-white text-sm rounded-lg hover:bg-primary-500 disabled:opacity-50 transition-colors"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {submitting ? 'Sending…' : 'Send feedback'}
          </button>
        </div>

        {feedback.length > 0 && (
          <div className="mt-3 space-y-2">
            {feedback.map((f, i) => (
              <div key={i} className="bg-accent-50 border-l-2 border-accent-400 rounded p-2">
                <div className="text-xs text-gray-500 mb-0.5">
                  {f.author || 'judge'}
                  {f.at ? ` · ${new Date(f.at).toLocaleString()}` : ''}
                </div>
                <div className="text-sm text-gray-800">{f.text}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function renderStage(
  stage: RunStage,
  feedback: RunFeedback[],
  onSubmitFeedback: (text: string) => void,
  submitting: boolean
) {
  switch (stage.id) {
    case 'intake':
      return <IntakeArtifact artifact={stage.artifact} />;
    case 'seeds':
      return <SeedsArtifact artifact={stage.artifact} />;
    case 'keywords':
      return <KeywordsArtifact artifact={stage.artifact} />;
    case 'clusters':
      return <ClustersArtifact artifact={stage.artifact} />;
    case 'pillars':
      return <PillarsArtifact artifact={stage.artifact} />;
    case 'mix':
      return (
        <MixArtifact
          artifact={stage.artifact}
          feedback={feedback}
          onSubmitFeedback={onSubmitFeedback}
          submitting={submitting}
        />
      );
    default:
      return (
        <pre className="text-xs text-gray-600 whitespace-pre-wrap overflow-auto max-h-64">
          {JSON.stringify(stage.artifact, null, 2)}
        </pre>
      );
  }
}

export function RunView({ tasks, onClose }: RunViewProps) {
  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const summaries = await getRuns();
        if (!summaries.length) {
          if (!cancelled) setError('No runs yet — ask the agent to run a pipeline.');
          return;
        }
        const full = await getRun(summaries[0].id);
        if (!cancelled) setRun(full);
      } catch (e: any) {
        if (!cancelled) {
          setError(
            e instanceof AuthError
              ? 'Not authenticated.'
              : `Failed to load run: ${e?.message || e}`
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmitFeedback = async (text: string) => {
    if (!run) return;
    setSubmitting(true);
    try {
      const res = await addRunFeedback(run.id, text, getUsername() || 'judge');
      setRun({ ...run, feedback: res.feedback });
    } catch (e: any) {
      console.error('feedback failed', e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-surface-50 overflow-y-auto">
      {/* Top bar */}
      <div className="sticky top-0 z-10 bg-surface-100 border-b border-surface-300 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Sparkles className="w-5 h-5 text-primary-500" />
          <div>
            <h2 className="text-lg font-semibold text-primary-700">
              {run ? run.title || run.project || 'Pipeline run' : 'Pipeline run'}
            </h2>
            {run?.project && (
              <p className="text-xs text-gray-500">{run.project}</p>
            )}
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-2 hover:bg-surface-200 rounded-lg transition-colors"
          title="Close pipeline view"
        >
          <X className="w-5 h-5 text-gray-500" />
        </button>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-8">
        {loading && (
          <div className="flex items-center justify-center py-24 text-gray-400 gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> Loading pipeline…
          </div>
        )}
        {error && !loading && (
          <div className="text-center py-24 text-gray-500">{error}</div>
        )}

        {run && !loading && !error && (
          <>
            {/* Tasks on top */}
            {tasks.length > 0 && (
              <div className="mb-8 bg-white border border-surface-300 rounded-xl p-4 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="text-sm font-semibold text-gray-800">Active tasks</h3>
                  <span className="text-xs text-gray-500 bg-surface-200 px-2 py-0.5 rounded">
                    {tasks.length}
                  </span>
                </div>
                <ul className="space-y-1">
                  {tasks.slice(0, 5).map((t, i) => (
                    <li key={i} className="text-sm text-gray-600 flex gap-2">
                      <span className="text-primary-400">▸</span>
                      <span className="truncate">{t}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Vertical stage flow */}
            <div>
              {run.stages.map((stage, i) => (
                <StageCard
                  key={stage.id}
                  stage={stage}
                  index={i}
                  isLast={i === run.stages.length - 1}
                >
                  {renderStage(
                    stage,
                    run.feedback || [],
                    handleSubmitFeedback,
                    submitting
                  )}
                </StageCard>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
