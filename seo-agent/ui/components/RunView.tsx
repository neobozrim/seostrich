'use client';

import React, { useEffect, useRef, useState } from 'react';
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
  RefreshCw,
} from 'lucide-react';
import { Run, RunStage, RunFeedback, RunSummary, ActivityEvent } from '@/types';
import { getRuns, getRun, addRunFeedback, getUsername, getRunActivity, AuthError } from '@/lib/api';
import { activityLabel } from '@/lib/activity';
import { StageIcon } from '@/components/StageIcon';

function fmtVol(n: number): string {
  // Grouped digits, not "3.6k" — an abbreviation costs a mental step every
  // time and hides the difference between 1,100 and 1,900.
  return (n || 0).toLocaleString('en-US');
}

interface RunViewProps {
  tasks: string[];
  onClose: () => void;
  // Which run to open. Set when the user clicks a card on the home canvas;
  // without it the view falls back to the most recent run.
  initialRunId?: string | null;
}

// Icons live in StageIcon.tsx, drawn in the brand mark's language (filled
// disc, negative-space cut breaking the edge). Emoji rendered differently on
// every platform and shared nothing with the logo.

const STATUS_META: Record<string, { label: string; cls: string }> = {
  running: { label: 'Running', cls: 'bg-accent-100 text-accent-700' },
  done: { label: 'Done', cls: 'bg-green-100 text-green-700' },
  stopped: { label: 'Stopped', cls: 'bg-surface-200 text-gray-600' },
  error: { label: 'Error', cls: 'bg-red-100 text-red-700' },
};

function StatusBadge({ status }: { status?: string }) {
  const meta = STATUS_META[status || ''] || { label: status || 'unknown', cls: 'bg-surface-200 text-gray-600' };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${meta.cls}`}>
      {status === 'running' && <Loader2 className="w-3 h-3 inline mr-1 animate-spin" />}
      {meta.label}
    </span>
  );
}

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
            stage.status === 'done' ? '' : 'opacity-40 grayscale'
          }`}
          title={stage.label}
        >
          <StageIcon stage={stage.id} className="w-8 h-8" />
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
    ['Market', artifact.market],
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

function fmtCpc(n: number | undefined): string {
  if (n === undefined || n === null) return '';
  return `$${Number(n).toFixed(2)}`;
}

function DiffBadge({ value }: { value: number | undefined }) {
  if (value === undefined || value === null) return null;
  const tone =
    value < 30
      ? 'bg-green-100 text-green-700'
      : value < 60
        ? 'bg-amber-100 text-amber-700'
        : 'bg-red-100 text-red-700';
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${tone}`}>KD {value}</span>;
}

// Keywords are read by SCANNING a column — "which of these has volume?" — so
// they are laid out as a table with fixed columns and right-aligned numbers,
// not as inline chips where every row starts at a different x position.
function KeywordTable({ rows }: { rows: Array<string | Record<string, any>> }) {
  const objects = rows.filter((r) => typeof r === 'object') as Record<string, any>[];
  const plain = rows.filter((r) => typeof r === 'string') as string[];

  return (
    <div>
      {objects.length > 0 && (
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-xs border-separate border-spacing-y-1 px-1">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-gray-400">
                <th className="text-left font-medium pl-2 pb-1">Keyword</th>
                <th className="text-right font-medium pb-1 w-20">Volume</th>
                <th className="text-right font-medium pb-1 w-14">KD</th>
                <th className="text-right font-medium pb-1 w-16">CPC</th>
                <th className="text-left font-medium pb-1 pl-3 w-28">Intent</th>
              </tr>
            </thead>
            <tbody>
              {objects.map((k, i) => (
                <tr key={i} className="bg-surface-100">
                  <td className="pl-2 py-1.5 rounded-l-lg text-gray-800">
                    {k.keyword || k.query || ''}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-gray-700">
                    {k.volume != null ? fmtVol(k.volume) : '—'}
                  </td>
                  <td className="py-1.5 text-right">
                    <DiffBadge value={k.difficulty} />
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-gray-600">
                    {k.cpc != null && k.cpc > 0 ? fmtCpc(k.cpc) : '—'}
                  </td>
                  <td className="py-1.5 pl-3 pr-2 rounded-r-lg capitalize text-gray-600">
                    {k.intent || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {plain.length > 0 && (
        <div className="mt-1">
          {plain.map((k, i) => (
            <Chip key={i}>{k}</Chip>
          ))}
        </div>
      )}
    </div>
  );
}

function KeywordsArtifact({ artifact }: { artifact: Record<string, any> }) {
  const [open, setOpen] = useState(false);
  const keywords: Array<string | Record<string, any>> = artifact.keywords || [];
  const shown = open ? keywords : keywords.slice(0, 24);
  const totalVol = keywords.reduce(
    (acc, k) => acc + (typeof k === 'object' ? k.volume || 0 : 0),
    0
  );
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-700">
          <span className="font-semibold">{artifact.count ?? keywords.length}</span>{' '}
          keywords discovered
          {totalVol > 0 && <span className="text-gray-400"> · combined vol {fmtVol(totalVol)}</span>}
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
        <KeywordTable rows={shown} />
        {!open && keywords.length > 24 && (
          <span className="text-xs text-gray-400"> +{keywords.length - 24} more…</span>
        )}
      </div>
    </div>
  );
}

function ClusterMember({ name, stats }: { name: string; stats?: Record<string, any> }) {
  if (!stats || Object.keys(stats).length === 0) return <Chip>{name}</Chip>;
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-1 m-0.5 text-xs bg-surface-100 border border-surface-300 rounded-lg text-gray-700">
      <span className="font-medium">{name}</span>
      {stats.volume != null && <span className="text-gray-500">vol {fmtVol(stats.volume)}</span>}
      <DiffBadge value={stats.difficulty} />
      {stats.intent && <span className="px-1.5 py-0.5 rounded bg-surface-200 text-[10px] capitalize text-gray-600">{stats.intent}</span>}
      {stats.cpc != null && stats.cpc > 0 && <span className="text-gray-500">{fmtCpc(stats.cpc)}</span>}
    </span>
  );
}

function ClusterCard({ c }: { c: any }) {
  const [open, setOpen] = useState(false);
  const stats: Record<string, any> = c.keyword_stats || {};
  return (
    <div className="border border-surface-300 rounded-lg">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-50 rounded-lg transition-colors text-left"
      >
        <span className="flex items-center gap-2 min-w-0">
          {open ? (
            <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
          )}
          <span className="text-sm font-medium text-gray-800 truncate">{c.name}</span>
          {c.proposed && <span className="px-1.5 py-0.5 rounded bg-accent-100 text-accent-700 text-[10px] font-semibold">proposed</span>}
          {c.promoted && <span className="px-1.5 py-0.5 rounded bg-green-100 text-green-700 text-[10px] font-semibold">promoted</span>}
        </span>
        <span className="flex items-center gap-1 flex-shrink-0">
          {c.combined_score != null ? (
            <ScoreBadge value={c.combined_score} />
          ) : c.total_volume != null ? (
            <span className="text-xs text-gray-400">vol {fmtVol(c.total_volume)}</span>
          ) : null}
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3">
          {(c.market || c.intent || c.total_volume != null || c.avg_difficulty != null) && (
            <div className="mb-2">
              {c.market && <Chip>{c.market}</Chip>}
              {c.intent && <Chip>{c.intent} intent</Chip>}
              {c.total_volume != null && <Chip>vol {fmtVol(c.total_volume)}</Chip>}
              {c.avg_difficulty != null && <Chip>difficulty {c.avg_difficulty}</Chip>}
            </div>
          )}
          {(c.seo_score != null || c.geo_score != null || c.combined_score != null) && (
            <div className="flex gap-4 text-xs text-gray-500 mb-2">
              <span>SEO <b>{c.seo_score}</b></span>
              <span>GEO <b>{c.geo_score}</b></span>
              <span>Combined <b>{c.combined_score}</b></span>
            </div>
          )}
          {(c.rationale || c.seo_rationale || c.geo_rationale) && (
            <p className="text-xs text-gray-600 mb-2">
              {c.rationale || [c.seo_rationale, c.geo_rationale].filter(Boolean).join(' · ')}
            </p>
          )}
          <div>
            {(c.keywords || []).map((k: string, ki: number) => (
              <ClusterMember key={ki} name={k} stats={stats[k]} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ClustersArtifact({ artifact }: { artifact: Record<string, any> }) {
  const clusters = artifact.clusters || [];
  const discarded = artifact.discarded || [];
  const [showDiscarded, setShowDiscarded] = useState(false);
  return (
    <div className="space-y-2">
      {artifact.selected && (
        <div className="text-xs text-gray-500 mb-1">
          <span className="font-semibold text-gray-700">{clusters.length}</span> selected ·{' '}
          <span className="font-semibold text-gray-700">{discarded.length}</span> discarded
        </div>
      )}
      {clusters.map((c: any, i: number) => (
        <ClusterCard key={`sel-${i}`} c={c} />
      ))}

      {discarded.length > 0 && (
        <div className="pt-2">
          <button
            onClick={() => setShowDiscarded(!showDiscarded)}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
          >
            {showDiscarded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            Discarded clusters ({discarded.length})
          </button>
          {showDiscarded && (
            <div className="mt-2 space-y-2">
              {discarded.map((c: any, i: number) => (
                <div key={`disc-${i}`} className="border border-surface-200 rounded-lg bg-surface-50">
                  <ClusterCard c={c} />
                  {c.discard_reason && (
                    <div className="px-3 pb-2 -mt-1 text-xs text-gray-500">
                      <span className="font-medium text-gray-600">Why discarded:</span> {c.discard_reason}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
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

function AuditArtifact({ artifact }: { artifact: Record<string, any> }) {
  const checks = artifact.checks || {};
  const names = Object.keys(checks);
  return (
    <div className="space-y-2">
      <div className="text-sm text-gray-700">
        <span className="font-semibold">{artifact.checks_count ?? names.length}</span> audit checks run
        {artifact.title && <span className="text-gray-400"> · {artifact.title}</span>}
      </div>
      <div className="space-y-1">
        {names.map((n) => {
          const v = checks[n];
          const issues = Array.isArray(v?.issues) ? v.issues.length : v?.issues_count ?? v?.errors ?? null;
          return (
            <div key={n} className="flex items-center justify-between text-sm border border-surface-200 rounded-lg px-3 py-2">
              <span className="text-gray-700 font-medium">{n}</span>
              {issues != null ? (
                <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${issues > 0 ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'}`}>
                  {issues > 0 ? `${issues} issues` : 'clean'}
                </span>
              ) : (
                <span className="text-xs text-gray-400">done</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CompetitorsArtifact({ artifact }: { artifact: Record<string, any> }) {
  const sources = artifact.sources || {};
  const names = Object.keys(sources);
  return (
    <div className="space-y-2">
      <div className="text-sm text-gray-700">
        <span className="font-semibold">{names.length}</span> competitor data source{names.length === 1 ? '' : 's'}
      </div>
      {names.map((n) => {
        const v = sources[n];
        const count = Array.isArray(v) ? v.length : v?.count ?? null;
        return (
          <div key={n} className="flex items-center justify-between text-sm border border-surface-200 rounded-lg px-3 py-2">
            <span className="text-gray-700 font-medium">{n}</span>
            {count != null && <span className="text-xs text-gray-400">{count} result{count === 1 ? '' : 's'}</span>}
          </div>
        );
      })}
    </div>
  );
}

// The GEO graph's output. Distinct from AiCitabilityArtifact, which renders the
// older ai_citability_brief shape — both can land on the same stage id.
function GeoDemandArtifact({ artifact }: { artifact: Record<string, any> }) {
  const brief: any[] = artifact.brief || [];
  const [open, setOpen] = useState<string | null>(brief[0]?.topic ?? null);

  return (
    <div className="space-y-2">
      <div className="text-xs text-gray-500">
        {artifact.market ? `Market ${artifact.market}. ` : ''}
        Ranked on measured demand and on whether the sites AI engines cite can
        realistically be displaced.
      </div>

      {brief.map((t: any) => {
        const m = t.metrics || {};
        const verdict = String(t.can_you_displace_them || '');
        const winnable = verdict.startsWith('winnable');
        const verify = verdict.includes('verify') || verdict.startsWith('uncertain');
        const isOpen = open === t.topic;
        return (
          <div key={t.topic} className="border border-surface-300 rounded-lg">
            <button
              onClick={() => setOpen(isOpen ? null : t.topic)}
              className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-50 rounded-lg text-left"
            >
              <span className="flex items-center gap-2 min-w-0">
                {isOpen ? (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                )}
                <span className="text-sm font-medium text-gray-800 truncate">{t.topic}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded-full border flex-shrink-0 ${
                    winnable
                      ? 'bg-green-50 border-green-300 text-green-800'
                      : verify
                      ? 'bg-amber-50 border-amber-300 text-amber-800'
                      : 'bg-surface-100 border-surface-300 text-gray-600'
                  }`}
                >
                  {winnable ? 'winnable' : verify ? 'verify' : 'hard'}
                </span>
              </span>
              <span className="text-xs text-gray-400 flex-shrink-0">
                {fmtVol(m.search_volume || 0)}/mo · authority{' '}
                {m.weakest_cited_authority || '?'}–{m.strongest_cited_authority || '?'}
              </span>
            </button>

            {isOpen && (
              <div className="px-3 pb-3 space-y-3">
                <p className="text-sm text-gray-700">{verdict}</p>

                {/* The questions are the point of the whole flow, so they lead. */}
                {t.content_plan?.length > 0 && (
                  <div>
                    <div className="text-xs text-gray-400 mb-1">
                      Questions people ask — use as headings, answer in the first two
                      sentences
                    </div>
                    <ol className="space-y-1.5">
                      {t.content_plan.map((sec: any, i: number) => (
                        <li key={i} className="text-sm">
                          <div className="flex items-start gap-2">
                            <span className="text-gray-400 tabular-nums text-xs mt-0.5">
                              {i + 1}.
                            </span>
                            <div className="min-w-0">
                              <div className="text-gray-800">{sec.heading}</div>
                              <div className="text-xs text-gray-500">
                                {sec.source === 'people_also_ask'
                                  ? 'People also ask'
                                  : 'An AI engine already answers this'}
                                {sec.currently_cited?.length > 0 && (
                                  <> · cited today: {sec.currently_cited.join(', ')}</>
                                )}
                                {sec.currently_answered_by && (
                                  <> · answered today by {sec.currently_answered_by}</>
                                )}
                              </div>
                            </div>
                          </div>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                {t.niche_sites_already_cited?.length > 0 && (
                  <div>
                    <div className="text-xs text-gray-400 mb-1">
                      Small sites already cited here — your proof it is winnable
                    </div>
                    <div>
                      {t.niche_sites_already_cited.map((d: any) => (
                        <Chip key={d.domain}>
                          {d.domain} · authority {d.authority_rank}
                        </Chip>
                      ))}
                    </div>
                  </div>
                )}

                {t.currently_cited?.length > 0 && (
                  <div>
                    <div className="text-xs text-gray-400 mb-1">Who AI cites today</div>
                    <div>
                      {t.currently_cited.slice(0, 10).map((d: any) => (
                        <span
                          key={d.domain}
                          title={
                            d.confidence === 'needs_review'
                              ? 'Found by matching answer text, not the question itself — may be off-subject. Verify before treating it as a competitor.'
                              : 'Cited on a question that names this topic'
                          }
                          className={`inline-block px-2 py-0.5 m-0.5 text-xs rounded-full border ${
                            d.confidence === 'needs_review'
                              ? 'bg-amber-50 border-amber-300 text-amber-900'
                              : 'bg-surface-100 border-surface-300 text-gray-700'
                          }`}
                        >
                          {d.domain}
                          {d.authority_rank ? ` · ${d.authority_rank}` : ''}
                          {d.confidence === 'needs_review' ? ' · verify' : ''}
                        </span>
                      ))}
                    </div>
                    <div className="text-[11px] text-gray-400 mt-1">
                      Amber = found by matching the answer text rather than the
                      question, so it may be off-subject. Worth reading, not trusting.
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {artifact.cost_note && (
        <div className="text-[11px] text-gray-400 pt-1">{artifact.cost_note}</div>
      )}
    </div>
  );
}

function AiCitabilityArtifact({ artifact }: { artifact: Record<string, any> }) {
  const terms = artifact.head_terms || [];
  const [openTerm, setOpenTerm] = useState<string | null>(null);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3 text-sm text-gray-700">
        <span>
          <span className="font-semibold">{artifact.questions_captured ?? 0}</span> AI questions captured
        </span>
        {artifact.overall_answer_share != null && (
          <span className="text-gray-500">
            answer share <b>{Math.round(artifact.overall_answer_share * 100)}%</b>
          </span>
        )}
      </div>

      {artifact.top_cited_sources?.length > 0 && (
        <div>
          <div className="text-xs text-gray-400 mb-1">Most cited by AI engines</div>
          <div>
            {artifact.top_cited_sources.map((s: any) => (
              <Chip key={s.domain}>{s.domain} ×{s.mentions}</Chip>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2 pt-1">
        {terms.map((t: any) => (
          <div key={t.head_term} className="border border-surface-300 rounded-lg">
            <button
              onClick={() => setOpenTerm(openTerm === t.head_term ? null : t.head_term)}
              className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-50 rounded-lg text-left"
            >
              <span className="flex items-center gap-2 min-w-0">
                {openTerm === t.head_term ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                <span className="text-sm font-medium text-gray-800 truncate">{t.head_term}</span>
              </span>
              <span className="text-xs text-gray-400 flex-shrink-0">
                {t.questions_asked} Qs{t.ai_search_volume ? ` · vol ${fmtVol(t.ai_search_volume)}` : ''}
              </span>
            </button>
            {openTerm === t.head_term && (
              <div className="px-3 pb-3 space-y-2">
                <div className="flex gap-4 text-xs text-gray-500">
                  <span>Answer share <b>{Math.round((t.answer_share ?? 0) * 100)}%</b></span>
                </div>
                {t.top_questions?.length > 0 && (
                  <div>
                    <div className="text-xs text-gray-400 mb-1">Top AI questions</div>
                    <ul className="text-xs text-gray-700 space-y-1 list-disc list-inside">
                      {t.top_questions.map((q: string, i: number) => <li key={i}>{q}</li>)}
                    </ul>
                  </div>
                )}
                {t.paa?.length > 0 && (
                  <div>
                    <div className="text-xs text-gray-400 mb-1">People also ask</div>
                    <div>{t.paa.map((q: string) => <Chip key={q}>{q}</Chip>)}</div>
                  </div>
                )}
                {t.top_cited_sources?.length > 0 && (
                  <div>
                    <div className="text-xs text-gray-400 mb-1">Cited for this term</div>
                    <div>{t.top_cited_sources.map((d: string) => <Chip key={d}>{d}</Chip>)}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function GenericArtifact({ artifact }: { artifact: Record<string, any> }) {
  return (
    <div className="space-y-2">
      {artifact.title && <div className="text-sm font-semibold text-gray-800">{artifact.title}</div>}
      <pre className="text-xs text-gray-600 whitespace-pre-wrap overflow-auto max-h-64">
        {JSON.stringify(
          Object.fromEntries(Object.entries(artifact).filter(([k]) => !['title', 'source'].includes(k))),
          null,
          2
        )}
      </pre>
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
    case 'audit':
      return <AuditArtifact artifact={stage.artifact} />;
    case 'competitors':
      return <CompetitorsArtifact artifact={stage.artifact} />;
    case 'ai_citability':
      // The GEO graph and the older brief both land on this stage id.
      return stage.artifact?.brief ? (
        <GeoDemandArtifact artifact={stage.artifact} />
      ) : (
        <AiCitabilityArtifact artifact={stage.artifact} />
      );
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
      return <GenericArtifact artifact={stage.artifact} />;
  }
}

export function RunView({ tasks, onClose, initialRunId }: RunViewProps) {
  const [run, setRun] = useState<Run | null>(null);
  const [summaries, setSummaries] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadRun = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const full = await getRun(id);
      setRun(full);
    } catch (e: any) {
      setError(
        e instanceof AuthError
          ? 'Not authenticated.'
          : `Failed to load run: ${e?.message || e}`
      );
    } finally {
      setLoading(false);
    }
  };

  // Silent refetch (no spinner) — used by manual refresh + live polling
  const refresh = async (id?: string) => {
    const target = id || run?.id;
    if (!target) return;
    try {
      const full = await getRun(target);
      setRun(full);
    } catch {
      /* keep the last good copy on transient errors */
    }
  };

  // While a run is in progress, poll so stages stream in without a manual refresh
  useEffect(() => {
    if (run?.status !== 'running') return;
    const t = setInterval(() => refresh(run.id), 1500);
    return () => clearInterval(t);
  }, [run?.id, run?.status]);

  // Live activity feed (graph nodes, tool starts/ends) — cursor-based polling
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const actCursor = useRef(0);

  useEffect(() => {
    setActivity([]);
    actCursor.current = 0;
  }, [run?.id]);

  useEffect(() => {
    if (!run || run.status !== 'running') return;
    const t = setInterval(async () => {
      try {
        const res = await getRunActivity(run.id, actCursor.current);
        actCursor.current = res.cursor;
        if (res.events.length) setActivity((prev) => [...prev, ...res.events].slice(-60));
      } catch {
        /* transient poll errors — keep last good feed */
      }
    }, 1200);
    return () => clearInterval(t);
  }, [run?.id, run?.status]);

  // One final drain when the run leaves "running" so the tail isn't lost
  useEffect(() => {
    if (!run || run.status === 'running') return;
    (async () => {
      try {
        const res = await getRunActivity(run.id, actCursor.current);
        actCursor.current = res.cursor;
        if (res.events.length) setActivity((prev) => [...prev, ...res.events].slice(-60));
      } catch {
        /* ignore */
      }
    })();
  }, [run?.id, run?.status]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const sums = await getRuns();
        if (cancelled) return;
        setSummaries(sums);
        if (!sums.length) {
          setError('No runs yet — ask the agent to run a pipeline.');
          return;
        }
        const wanted =
          initialRunId && sums.some((x: RunSummary) => x.id === initialRunId)
            ? initialRunId
            : sums[0].id;
        await loadRun(wanted);
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
          {/* No decorative icon here: the SEOstrich logo sits top-left on every
              internal view, and a second generic glyph beside the title just
              competes with it. */}
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-primary-700">
                {run ? run.title || run.project || 'Report' : 'Report'}
              </h2>
              {run?.status && <StatusBadge status={run.status} />}
            </div>
            {run?.project && (
              <p className="text-xs text-gray-500">{run.project}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {summaries.length > 1 && (
            <select
              value={run?.id || ''}
              onChange={(e) => loadRun(e.target.value)}
              className="max-w-[220px] px-3 py-2 text-sm border border-surface-300 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-400"
              title="Switch pipeline run"
            >
              {summaries.map((s) => (
                <option key={s.id} value={s.id}>
                  {(s.title || s.id).slice(0, 40)}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={() => refresh()}
            className="p-2 hover:bg-surface-200 rounded-lg transition-colors"
            title="Refresh run"
          >
            <RefreshCw className="w-4 h-4 text-gray-500" />
          </button>
          <button
            onClick={onClose}
            className="p-2 hover:bg-surface-200 rounded-lg transition-colors"
            title="Close pipeline view"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>
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

            {/* Live activity — what the agent is doing right now */}
            {activity.length > 0 && (
              <div className="mb-8 bg-white border border-surface-300 rounded-xl p-4 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="text-sm font-semibold text-gray-800">Live activity</h3>
                  {run.status === 'running' && (
                    <Loader2 className="w-3 h-3 animate-spin text-gray-400" />
                  )}
                </div>
                <ul className="space-y-0.5 font-mono text-[11px] text-gray-500">
                  {activity.slice(-10).map((ev, i) => (
                    <li key={`${ev.ts}-${i}`}>{activityLabel(ev)}</li>
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
