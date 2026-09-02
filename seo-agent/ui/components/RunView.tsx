'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Send,
  CheckCircle2,
  Circle,
  Sparkles,
  MessageSquare,
  Loader2,
  RefreshCw,
  Pencil,
  Square,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  PencilLine,
  Undo2,
} from 'lucide-react';
import { Run, RunStage, RunFeedback, RunSummary, ActivityEvent, Message } from '@/types';
import { getRuns, getRun, addRunFeedback, getUsername, getRunActivity, getRunChanges, renameRun, fetchCompetitorKeywords, regenerateBrief,
  resetRun, getRunGovernance, AuthError } from '@/lib/api';
import { activityLabel, currentActivity } from '@/lib/activity';
import { StageIcon } from '@/components/StageIcon';
import ReactMarkdown from 'react-markdown';

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
  // True while the chat stream producing this artefact is open. The graph
  // may have finished while the agent still edits the artefact (proposing a
  // cluster, writing the summary), so polling follows the stream too.
  live?: boolean;
  // The conversation this artefact belongs to. Follow-ups go into the same
  // session so "drop the courses cluster" has context; while a run is
  // streaming the same box is Steer: stop, then send the correction.
  isStreaming?: boolean;
  onSend?: (text: string) => void | Promise<void>;
  onSteer?: (text: string) => void | Promise<void>;
  onStop?: () => void;
  recent?: Message[];
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
        {STAGE_PURPOSE[stage.id] && (
          <p className="text-sm text-gray-500 mb-3 max-w-prose leading-relaxed">{STAGE_PURPOSE[stage.id]}</p>
        )}
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

// The rail shows each step once, in words; consecutive duplicates and the
// model's internal rounds are noise.
function dedupeLabels(events: ActivityEvent[]): string[] {
  const out: string[] = [];
  for (const ev of events) {
    if (ev.kind === 'llm_round' || (ev.kind === 'tool_end' && ev.success)) continue;
    const l = activityLabel(ev);
    if (l && out[out.length - 1] !== l) out.push(l);
  }
  return out;
}

// Older runs are titled with the prompt that started them. A name is short
// and does not end like a sentence; anything else is clamped at a word
// boundary so the heading never cuts mid-word.
function artefactName(run: Run): string {
  const t = (run.title || '').trim();
  const p = (run.project || '').trim();
  if (t && t.length <= 48 && !/[.!?]$/.test(t)) return t;
  if (p && p.toLowerCase() !== 'chat pipeline') return p.split(' · ')[0];
  if (!t) return 'Untitled';
  const words = t.split(/\s+/);
  let out = '';
  for (const w of words) {
    if ((out + ' ' + w).trim().length > 44) break;
    out = (out + ' ' + w).trim();
  }
  return out ? out + '…' : t.slice(0, 44) + '…';
}
// The kind of artefact, read from what it contains rather than stored — an
// old run gets the right tag too.
function flowTag(run: Run): string {
  const ids = new Set((run.stages || []).map((s) => s.id));
  if (ids.has('pillars') || ids.has('clusters') || ids.has('keywords') || ids.has('seeds')) return 'SEO content strategy';
  if (ids.has('ai_citability')) return 'AI visibility';
  if (ids.has('audit')) return 'Technical audit';
  return 'Strategy';
}
function artefactLine(run: Run): string {
  const t = (run.title || '').trim();
  const p = (run.project || '').trim();
  if (p && p.toLowerCase() !== 'chat pipeline' && p !== artefactName(run)) return p;
  if (t && t !== artefactName(run) && t.length > 48) return t;
  return '';
}
function formatCreated(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// What each step is FOR, and what it hands to the next one. A reader lands on
// an artefact cold; the stage names alone ("Intake", "Clusters") explain
// nothing. One short paragraph each, in plain words.
const STAGE_PURPOSE: Record<string, string> = {
  intake:
    'The market you confirmed: which country your audience searches from and in which language. Never inferred from the domain. Every number below is measured for this market only.',
  seeds:
    'A handful of searchable phrases pulled from your brief, your site and your competitors. They are the starting points, not the answer: each one is expanded into everything people actually search around it.',
  keywords:
    'The keyword universe: every phrase found by expanding the seeds, plus what your competitors rank for, each with real search volume, difficulty, cost-per-click and intent from DataForSEO. Difficulty is 0–100 and measures how strong the pages ranking today are, not how many people search — a low number on a real-volume keyword is a gap a new site can win. Nothing here is estimated by a model.',
  competitors:
    'What the competition ranks for, keyword by keyword, and where they overlap. These keywords join the universe above — capped at the number found from your own seeds, most-shared first — and are clustered with everything else on equal footing; there is no separate weight. Every keyword that came from a competitor is tagged with its source wherever it appears.',
  clusters:
    'The universe grouped into themes a single page could own, verified against live Google results: two keywords belong together only if Google shows the same pages for both. Each theme is measured, then kept or parked with a stated reason — and any decision can be argued with, here or over WebMCP.',
  pillars:
    'The recommendation: which themes to build content around, in what order, and why — citing the measured numbers that earned each one its place. This is what you take to a writer.',
  mix:
    'The publishing plan built from the pillars: what to write first, and at what cadence.',
  ai_citability:
    'What AI engines already do with these topics: how much AI search demand there is, which sources ChatGPT and Google AI cite today, how much of the answer space is unclaimed, and the questions people actually ask. Write against those questions to get cited.',
  audit:
    'Technical checks on the site itself — crawlability, metadata, rendering — the things that keep good content from being found.',
  onpage:
    'How specific pages measure up against what they are trying to rank for.',
};

function briefOf(run: Run | null): any | null {
  if (!run) return null;
  const st = (run.stages || []).find((s) => s.id === 'brief');
  return st?.artifact && st.artifact.the_call ? st.artifact : null;
}

// The brief is the deliverable: it sits under the heading, before the
// working. Six pieces, the call, who to out-answer, what was parked.
function BriefCard({ brief, onRegenerate, regenerating }: { brief: any; onRegenerate: () => void; regenerating: boolean }) {
  const pieces: any[] = brief.pieces || [];
  const out: any[] = brief.out_answer || [];
  const parked: any[] = brief.parked || [];
  return (
    <div className="mt-5 bg-white border border-surface-300 rounded-xl px-5 py-5 shadow-sm">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="text-[10px] font-semibold tracking-[0.16em] uppercase text-gray-400">The brief</div>
        {brief.stale ? (
          <button
            onClick={onRegenerate}
            disabled={regenerating}
            className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 hover:bg-amber-100 disabled:opacity-50"
            title="The selection changed since this brief was written"
          >
            {regenerating ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
            {regenerating ? 'Rebuilding…' : `Out of date — ${brief.stale_reason || 'the selection changed'} · Rebuild`}
          </button>
        ) : (
          <button onClick={onRegenerate} disabled={regenerating} className="text-xs text-gray-400 hover:text-gray-700 disabled:opacity-50">
            {regenerating ? 'Rebuilding…' : 'Rebuild'}
          </button>
        )}
      </div>

      <div className="mb-4">
        <div className="text-xs font-semibold text-gray-500 mb-1">The call</div>
        <div className="font-display text-lg text-primary-700">{brief.the_call?.pillar}</div>
        <p className="text-sm text-gray-700 mt-1 leading-relaxed">{brief.the_call?.why}</p>
      </div>

      {out.length > 0 && (
        <div className="mb-4">
          <div className="text-xs font-semibold text-gray-500 mb-1">Who to out-answer</div>
          <ul className="text-sm text-gray-700 space-y-0.5">
            {out.map((o, i) => (
              <li key={i}><span className="font-medium text-gray-800">{o.who}</span> — {o.for_what}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mb-4">
        <div className="text-xs font-semibold text-gray-500 mb-2">{pieces.length} pieces</div>
        <ol className="space-y-2">
          {pieces.map((pc, i) => (
            <li key={i} className="border border-surface-200 rounded-lg px-3 py-2">
              <div className="flex items-start gap-2">
                <span className="text-xs font-semibold text-gray-400 pt-0.5 w-5 shrink-0">{i + 1}.</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-900">{pc.title}</div>
                  <div className="text-sm text-gray-600 mt-0.5">Answers: <span className="italic">{pc.question}</span></div>
                  <div className="text-[11px] text-gray-400 mt-1">
                    {pc.cluster}{pc.target_keyword ? ' · ' + pc.target_keyword : ''}{pc.format ? ' · ' + pc.format : ''}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>

      {parked.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-gray-500 mb-1">Parked</div>
          <ul className="text-sm text-gray-600 space-y-0.5">
            {parked.map((pk, i) => (
              <li key={i}><span className="text-gray-800">{pk.cluster}</span> — {pk.why}</li>
            ))}
          </ul>
        </div>
      )}
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

type SortKey = 'keyword' | 'volume' | 'difficulty' | 'cpc' | 'intent';
type SortDir = 'asc' | 'desc';

// Numbers are most useful biggest-first, names A-Z, difficulty easiest-first.
// Clicking a column applies the direction people actually want first, and
// clicking again reverses it — the pattern every spreadsheet and data grid
// uses, so nobody has to learn it here.
const DEFAULT_DIR: Record<SortKey, SortDir> = {
  keyword: 'asc',
  volume: 'desc',
  difficulty: 'asc',
  cpc: 'desc',
  intent: 'asc',
};

const COLUMNS: Array<{
  key: SortKey;
  label: string;
  align: 'left' | 'right';
  className: string;
}> = [
  { key: 'keyword', label: 'Keyword', align: 'left', className: 'pl-2' },
  { key: 'volume', label: 'Volume', align: 'right', className: 'w-20' },
  { key: 'difficulty', label: 'KD', align: 'right', className: 'w-14' },
  { key: 'cpc', label: 'CPC', align: 'right', className: 'w-16' },
  { key: 'intent', label: 'Intent', align: 'left', className: 'pl-3 w-28' },
];

function sortValue(row: Record<string, any>, key: SortKey): string | number | null {
  if (key === 'keyword') return String(row.keyword || row.query || '').toLowerCase();
  if (key === 'intent') return String(row.intent || '').toLowerCase();
  const v = row[key];
  return v === undefined || v === null ? null : Number(v);
}

function sortRows(
  rows: Record<string, any>[],
  key: SortKey,
  dir: SortDir,
): Record<string, any>[] {
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = sortValue(a, key);
    const bv = sortValue(b, key);
    // Missing values sink to the bottom in BOTH directions. Sorting by CPC
    // descending should not fill the top of the table with blanks.
    const aMissing = av === null || av === '';
    const bMissing = bv === null || bv === '';
    if (aMissing && bMissing) return 0;
    if (aMissing) return 1;
    if (bMissing) return -1;
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * sign;
    return String(av).localeCompare(String(bv)) * sign;
  });
}

function SortHeader({
  column,
  active,
  dir,
  onSort,
}: {
  column: (typeof COLUMNS)[number];
  active: boolean;
  dir: SortDir;
  onSort: (key: SortKey) => void;
}) {
  const nextDir = active ? (dir === 'asc' ? 'desc' : 'asc') : DEFAULT_DIR[column.key];
  const readable =
    column.key === 'keyword' || column.key === 'intent'
      ? nextDir === 'asc'
        ? 'A to Z'
        : 'Z to A'
      : nextDir === 'asc'
        ? 'lowest first'
        : 'highest first';
  return (
    <th
      className={CLS_TH(column, active)}
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button
        onClick={() => onSort(column.key)}
        title={'Sort by ' + column.label + ', ' + readable}
        className={CLS_BTN(column, active)}
      >
        {column.label}
        {active ? (
          dir === 'asc' ? (
            <ArrowUp className="w-3 h-3" />
          ) : (
            <ArrowDown className="w-3 h-3" />
          )
        ) : (
          // Inactive columns stay quiet until hovered: the active sort is then
          // never ambiguous, but every column still advertises that it sorts.
          <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-60 transition-opacity" />
        )}
      </button>
    </th>
  );
}

function CLS_TH(column: (typeof COLUMNS)[number], _active: boolean): string {
  return (
    'font-medium pb-1 ' +
    column.className +
    (column.align === 'right' ? ' text-right' : ' text-left')
  );
}

function CLS_BTN(column: (typeof COLUMNS)[number], active: boolean): string {
  return (
    'group inline-flex items-center gap-0.5 uppercase tracking-wide transition-colors ' +
    (column.align === 'right' ? 'flex-row-reverse ' : '') +
    (active ? 'text-primary-600' : 'text-gray-400 hover:text-gray-600')
  );
}

// Keywords are read by SCANNING a column — "which of these has volume?" — so
// they are laid out as a table with fixed columns and right-aligned numbers,
// not as inline chips where every row starts at a different x position. And
// scanning a column is exactly when you want to sort by it.
function KeywordTable({
  rows,
  limit,
  hideOwner = false,
}: {
  rows: Array<string | Record<string, any>>;
  limit?: number;
  // Inside one competitor's own list every row is "from" that competitor;
  // the tag would only repeat the heading.
  hideOwner?: boolean;
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir } | null>(null);

  const objects = rows.filter((r) => typeof r === 'object') as Record<string, any>[];
  const plain = rows.filter((r) => typeof r === 'string') as string[];

  const handleSort = (key: SortKey) =>
    setSort((prev) =>
      prev?.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: DEFAULT_DIR[key] },
    );

  // Sort the WHOLE set before truncating: sorting only the visible 24 would
  // quietly answer a different question than the one the click asked.
  const ordered = sort ? sortRows(objects, sort.key, sort.dir) : objects;
  const visible = limit != null ? ordered.slice(0, limit) : ordered;

  return (
    <div>
      {objects.length > 0 && (
        <div className="overflow-x-auto -mx-1">
          <table className="w-full min-w-[480px] text-xs border-separate border-spacing-y-1 px-1">
            <thead>
              <tr className="text-[10px]">
                {COLUMNS.map((c) => (
                  <SortHeader
                    key={c.key}
                    column={c}
                    active={sort?.key === c.key}
                    dir={sort?.key === c.key ? sort.dir : DEFAULT_DIR[c.key]}
                    onSort={handleSort}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((k, i) => (
                <tr key={i} className="bg-surface-100">
                  <td
                    className="pl-2 py-1.5 rounded-l-lg text-gray-800 max-w-[260px] truncate"
                    title={(k.keyword || k.query || '') + (Array.isArray(k.owned_by) && k.owned_by.length ? ' — ranked by ' + k.owned_by.join(', ') : '')}
                  >
                    {k.keyword || k.query || ''}
                    {!hideOwner && Array.isArray(k.owned_by) && k.owned_by.length > 0 && (
                      <span className="ml-1.5 text-[10px] text-accent-500 font-medium">
                        from {k.owned_by[0].replace(/^www\./, '').split('.')[0]}{k.owned_by.length > 1 ? ' +' + (k.owned_by.length - 1) : ''}
                      </span>
                    )}
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
        <KeywordTable rows={keywords} limit={open ? undefined : 24} />
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
          {/* One row per keyword, in the same table as keyword discovery —
              the same columns, the same sort, so the eye does not relearn. */}
          <KeywordTable
            rows={(c.keywords || []).map((k: any) => {
              const name = typeof k === 'string' ? k : k?.keyword || '';
              const st = stats[name] || (typeof k === 'object' ? k : {}) || {};
              return { keyword: name, volume: st.volume, difficulty: st.difficulty, cpc: st.cpc, intent: st.intent, owned_by: st.owned_by };
            })}
          />
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

function CompetitorsArtifact({ artifact, universe = [], runId }: { artifact: Record<string, any>; universe?: any[]; runId?: string }) {
  // Rows fetched on demand for runs that predate full storage.
  const [fetched, setFetched] = useState<Record<string, any[]>>({});
  const [fetching, setFetching] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const fetchAll = async (d: string) => {
    if (!runId) return;
    setFetching(d);
    setFetchError(null);
    try {
      const res = await fetchCompetitorKeywords(runId, d);
      setFetched((prev) => ({ ...prev, [d]: res.rows || [] }));
    } catch (e: any) {
      setFetchError(e?.message || 'Could not fetch');
    } finally {
      setFetching(null);
    }
  };
  // Runs recorded before the map kept every keyword: rebuild each
  // competitor's list from the universe rows tagged with their owners.
  const rowsFor = (d: string): any[] => {
    if (fetched[d]) return fetched[d];
    const own = artifact.per_domain?.[d]?.rows;
    if (Array.isArray(own) && own.length) return own;
    return (universe || []).filter((k: any) => Array.isArray(k?.owned_by) && k.owned_by.includes(d));
  };
  const queried: string[] = artifact.competitors || [];
  const user: string[] = artifact.user_supplied || [];
  const discovered: string[] = artifact.discovered || [];
  const per: Record<string, any> = artifact.per_domain || {};
  const kept = artifact.kept_in_universe;
  const contributed = artifact.keywords_contributed;
  const [openDomain, setOpenDomain] = useState<string | null>(null);
  const [gridOpen, setGridOpen] = useState(true);

  if (queried.length === 0) {
    return (
      <div className="text-sm text-gray-500">
        No competitors were checked for this run. Add competitor URLs to the brief and the
        keywords they rank for join the universe.
      </div>
    );
  }

  // Overlap grid: every keyword any competitor ranks for, most-shared first,
  // then by volume. Columns are the competitors; a dot means "ranks for it".
  const owners = new Map<string, { row: any; by: Set<string> }>();
  for (const d of queried) {
    for (const r of rowsFor(d)) {
      const k = (r.keyword || '').toLowerCase();
      if (!k) continue;
      const cur = owners.get(k) || { row: r, by: new Set<string>() };
      cur.by.add(d);
      if ((r.volume || 0) > (cur.row.volume || 0)) cur.row = r;
      owners.set(k, cur);
    }
  }
  const grid = Array.from(owners.values())
    .sort((a, b) => b.by.size - a.by.size || (b.row.volume || 0) - (a.row.volume || 0))
    .slice(0, 40);
  const shared = grid.filter((g) => g.by.size >= 2).length;
  const short = (d: string) => d.replace(/^www\./, '').split('.')[0];

  const named = user.length;
  const checkedLine =
    queried.length + ' checked' +
    (named > queried.length ? ' of the ' + named + ' you named' : named ? ' · ' + named + ' you named' : '') +
    (discovered.length ? ' · ' + discovered.length + ' discovered' : '');
  const contributedLine =
    contributed != null
      ? contributed + ' keywords they rank for' + (kept != null ? ' · ' + kept + ' kept in the universe' : '')
      : '';

  return (
    <div className="space-y-4">
      <div className="text-sm text-gray-700">
        <span className="font-semibold">{checkedLine}</span>
        {contributedLine && <span className="text-gray-400"> · {contributedLine}</span>}
      </div>
      {named > queried.length && (
        <div className="text-xs text-gray-500">
          At most five are checked per run, yours first. Not checked: {user.filter((d) => !queried.includes(d)).join(', ')}.
        </div>
      )}
      {artifact.site_has_rankings === false && (
        <div className="text-xs text-gray-500">
          Your site does not rank for anything yet, so every keyword here is one you are absent from.
        </div>
      )}
      {artifact.relevance?.ran ? (
        <div className="text-xs text-gray-600 bg-surface-100 border border-surface-200 rounded-lg px-3 py-2">
          <span className="font-semibold">Relevance gate:</span> kept {artifact.relevance.kept}, dropped {artifact.relevance.dropped} as not about this business
          {artifact.relevance.dropped_because ? ' — ' + artifact.relevance.dropped_because : ''}
          {Array.isArray(artifact.relevance.dropped_examples) && artifact.relevance.dropped_examples.length > 0 && (
            <span className="text-gray-400"> · e.g. {artifact.relevance.dropped_examples.slice(0, 5).join(', ')}</span>
          )}
        </div>
      ) : artifact.relevance && artifact.relevance.ran === false && artifact.keywords_contributed ? (
        <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          The relevance gate did not run on this map{artifact.relevance.error ? ' (' + artifact.relevance.error + ')' : ''} — competitor keywords were kept unfiltered.
        </div>
      ) : null}

      {/* Who ranks for what */}
      {grid.length > 0 && (
        <div>
          <button
            onClick={() => setGridOpen(!gridOpen)}
            className="flex items-center gap-1 text-xs font-semibold text-gray-700 mb-1"
          >
            {gridOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            Who ranks for what · top {grid.length}{shared ? ' · ' + shared + ' shared by two or more' : ''}
          </button>
          {gridOpen && (
            <div className="overflow-x-auto -mx-1">
              <table className="w-full text-xs border-separate border-spacing-y-1 px-1 min-w-[420px]">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wide text-gray-400">
                    <th className="text-left font-medium pl-2 pb-1">Keyword</th>
                    <th className="text-right font-medium pb-1 w-16">Vol</th>
                    <th className="text-left font-medium pb-1 pl-3">Ranked by</th>
                  </tr>
                </thead>
                <tbody>
                  {grid.map((g, i) => (
                    <tr key={i} className={g.by.size >= 2 ? 'bg-action-50' : 'bg-surface-100'}>
                      <td className="pl-2 py-1 rounded-l-lg text-gray-800 max-w-[220px] truncate" title={g.row.keyword}>{g.row.keyword}</td>
                      <td className="py-1 text-right tabular-nums text-gray-600">{g.row.volume != null ? fmtVol(g.row.volume) : '—'}</td>
                      <td className="py-1 pl-3 pr-2 rounded-r-lg">
                        <span className="flex flex-wrap gap-1">
                          {Array.from(g.by).map((d) => (
                            <span key={d} className="text-[10px] px-1.5 py-0.5 rounded bg-white border border-surface-300 text-accent-600 font-medium" title={d}>
                              {short(d)}
                            </span>
                          ))}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Each competitor, with everything it ranks for */}
      <div className="space-y-2">
        {queried.map((d) => {
          const v = per[d] || {};
          const rows: any[] = rowsFor(d);
          const open = openDomain === d;
          const meta =
            (v.keywords ?? rows.length) + ' keywords' +
            (v.shared_with_site ? ' · ' + v.shared_with_site + ' shared with you' : '') +
            (user.includes(d) ? '' : ' · discovered');
          return (
            <div key={d} className="border border-surface-300 rounded-lg">
              <button
                onClick={() => setOpenDomain(open ? null : d)}
                className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-50 rounded-lg text-left"
              >
                <span className="flex items-center gap-2 min-w-0">
                  {open ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                  <span className="text-sm font-medium text-gray-800">{d}</span>
                </span>
                <span className="text-xs text-gray-400">{meta}</span>
              </button>
              {open && (
                <div className="px-3 pb-3">
                  {rows.length > 0 && v.keywords && rows.length < v.keywords && !fetched[d] && (
                    <div className="text-xs text-gray-500 mb-2 flex flex-wrap items-center gap-2">
                      <span>
                        Showing the {rows.length} of {v.keywords} that made it into the universe — this run was recorded before the full list was kept.
                      </span>
                      <button
                        onClick={() => fetchAll(d)}
                        disabled={fetching === d}
                        className="text-action-500 hover:underline underline-offset-2 font-medium disabled:opacity-50"
                        title="One DataForSEO lookup, saved onto this artefact"
                      >
                        {fetching === d ? 'Fetching…' : 'Show all ' + v.keywords + ' (1 lookup)'}
                      </button>
                      {fetchError && fetching === null && <span className="text-red-600">{fetchError}</span>}
                    </div>
                  )}
                  {rows.length ? (
                    <KeywordTable rows={rows} hideOwner />
                  ) : (
                    <div className="text-xs text-gray-400">{(v.top || []).join(' · ') || 'No keywords recorded.'}</div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
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
  submitting: boolean,
  universe: any[] = [],
  runId?: string
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
      return <CompetitorsArtifact artifact={stage.artifact} universe={universe} runId={runId} />;
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

export function RunView({ tasks, onClose, initialRunId, live, isStreaming, onSend, onSteer, onStop, recent = [] }: RunViewProps) {
  const [draft, setDraft] = useState('');
  const submitDraft = async () => {
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    if (isStreaming && onSteer) await onSteer(text);
    else if (onSend) await onSend(text);
  };
  const [run, setRun] = useState<Run | null>(null);
  const [summaries, setSummaries] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Whether this report still matches what the pipeline produced. On a shared
  // deployment somebody else's edits are indistinguishable from the pipeline's
  // own verdict unless the report says so.
  const [changes, setChanges] = useState<any | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const regenerate = async () => {
    if (!run) return;
    setRegenerating(true);
    try {
      await regenerateBrief(run.id);
      await refresh(run.id);
    } catch (e: any) {
      setError(e?.message || 'Could not rebuild the brief');
    } finally {
      setRegenerating(false);
    }
  };
  const [titleDraft, setTitleDraft] = useState('');
  const commitTitle = async () => {
    if (!run) return;
    const next = titleDraft.trim();
    setEditingTitle(false);
    if (!next || next === run.title) return;
    setRun({ ...run, title: next });
    try {
      await renameRun(run.id, next);
    } catch (e: any) {
      setError(e?.message || 'Could not rename');
    }
  };
  const [resetting, setResetting] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<any[] | null>(null);

  const loadRun = async (id: string) => {
    setLoading(true);
    setError(null);
    setChanges(null);
    setHistory(null);
    setShowHistory(false);
    try {
      const full = await getRun(id);
      setRun(full);
      // Non-blocking: a report that cannot report its edit state is still a
      // readable report.
      getRunChanges(id).then(setChanges).catch(() => setChanges(null));
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

  const handleReset = async () => {
    if (!run) return;
    const n = changes?.change_count ?? 0;
    if (!window.confirm(
      `Undo ${n} change${n === 1 ? '' : 's'} and put this report back to what ` +
      `the pipeline produced?\n\nThe record of what was changed is kept.`
    )) return;
    setResetting(true);
    try {
      await resetRun(run.id);
      await refresh(run.id);
      setHistory(null);
    } catch (e: any) {
      setError(e?.message || 'Could not reset');
    } finally {
      setResetting(false);
    }
  };

  const toggleHistory = async () => {
    const next = !showHistory;
    setShowHistory(next);
    if (next && history === null && run) {
      try {
        const res = await getRunGovernance(run.id);
        setHistory(res.changes || []);
      } catch {
        setHistory([]);
      }
    }
  };

  // Silent refetch (no spinner) — used by manual refresh + live polling
  const refresh = async (id?: string) => {
    const target = id || run?.id;
    if (!target) return;
    try {
      const full = await getRun(target);
      setRun(full);
      getRunChanges(target).then(setChanges).catch(() => {});
    } catch {
      /* keep the last good copy on transient errors */
    }
  };

  // While a run is in progress, poll so stages stream in without a manual refresh
  useEffect(() => {
    if (!run) return;
    if (run.status !== 'running' && !live) return;
    const t = setInterval(() => refresh(run.id), 1500);
    return () => clearInterval(t);
  }, [run?.id, run?.status, live]);

  // When the stream closes, fetch once more so the summary and any late edit
  // (a proposed cluster) are on screen without a manual refresh.
  const wasLive = useRef(false);
  useEffect(() => {
    if (wasLive.current && !live && run) refresh(run.id);
    wasLive.current = !!live;
  }, [live]);

  // Live activity feed (graph nodes, tool starts/ends) — cursor-based polling
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const actCursor = useRef(0);

  useEffect(() => {
    setActivity([]);
    actCursor.current = 0;
  }, [run?.id]);

  useEffect(() => {
    if (!run || (run.status !== 'running' && !live)) return;
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
          setError('Nothing here yet.');
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
    <div className="fixed inset-x-0 bottom-0 top-16 z-40 bg-surface-50 overflow-y-auto">

      {/* The report is ABOUT something — say so as a page heading rather than
          shrinking it into the chrome. No status badge: "complete" on a
          finished report tells the reader nothing, and a run that failed says
          so in its own body. */}
      {run && !loading && !error && (
        <div className="max-w-3xl lg:max-w-6xl mx-auto px-6 pt-8"><div className="lg:max-w-[48rem]">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-semibold tracking-[0.16em] uppercase px-2 py-0.5 rounded bg-accent-50 text-accent-600 border border-accent-100">
              {flowTag(run)}
            </span>
            {run.created && <span className="text-xs text-gray-400">{formatCreated(run.created)}</span>}
          </div>
          {editingTitle ? (
            <input
              autoFocus
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitTitle();
                if (e.key === 'Escape') setEditingTitle(false);
              }}
              onBlur={commitTitle}
              maxLength={80}
              className="w-full text-2xl font-display text-primary-700 bg-white border-b-2 border-action-400 focus:outline-none py-0.5"
            />
          ) : (
            <button
              onClick={() => { setTitleDraft(artefactName(run)); setEditingTitle(true); }}
              title="Rename"
              className="group text-left flex items-start gap-2 max-w-full"
            >
              <h1 className="text-2xl font-display text-primary-700 break-words">{artefactName(run)}</h1>
              <Pencil className="w-4 h-4 mt-2 text-gray-300 group-hover:text-gray-600 shrink-0" />
            </button>
          )}
          {briefOf(run) && <BriefCard brief={briefOf(run)} onRegenerate={regenerate} regenerating={regenerating} />}
          {run.summary && (
            <div className="mt-5 bg-white border border-surface-300 rounded-xl px-5 py-4 prose prose-sm max-w-none text-gray-800">
              <ReactMarkdown>{run.summary}</ReactMarkdown>
            </div>
          )}

          {/* Only ever shown when it is true. An "unedited" badge on every
              report would be noise; "someone changed this" is news. */}
          {changes?.edited && (
            <div className="mt-4 flex flex-wrap items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              <PencilLine className="w-4 h-4 text-amber-700 shrink-0" />
              <span className="text-sm text-amber-900">
                <strong>{changes.change_count}</strong>{' '}
                {changes.change_count === 1 ? 'change' : 'changes'} since the
                pipeline produced this
                {changes.last_change?.by && (
                  <span className="text-amber-700"> · last by {changes.last_change.by}</span>
                )}
              </span>
              <button
                onClick={toggleHistory}
                className="text-sm font-medium text-amber-800 hover:text-amber-900 underline underline-offset-2"
              >
                {showHistory ? 'Hide' : 'What changed?'}
              </button>
              <button
                onClick={handleReset}
                disabled={resetting || !changes.can_reset}
                className="ml-auto flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-lg bg-white border border-amber-300 text-amber-900 hover:bg-amber-100 disabled:opacity-50 transition-colors"
              >
                <Undo2 className="w-3.5 h-3.5" />
                {resetting ? 'Restoring…' : 'Reset to as-produced'}
              </button>
            </div>
          )}

          {showHistory && (
            <ul className="mt-2 border border-surface-300 rounded-lg divide-y divide-surface-200 bg-white">
              {history === null && (
                <li className="px-3 py-2 text-sm text-gray-400">Loading history…</li>
              )}
              {history?.length === 0 && (
                <li className="px-3 py-2 text-sm text-gray-400">No changes recorded.</li>
              )}
              {history?.map((h, i) => (
                <li key={i} className="px-3 py-2 text-sm flex flex-wrap gap-x-2 gap-y-0.5">
                  <span className="font-mono text-xs uppercase text-primary-500 pt-0.5">{h.op}</span>
                  <span className="font-medium text-gray-800">{h.cluster}</span>
                  {h.reason && <span className="text-gray-500">— {h.reason}</span>}
                  <span className="text-gray-400 ml-auto">{h.by}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        </div>
      )}

      <div className="max-w-3xl lg:max-w-6xl mx-auto px-6 pt-4 pb-8 lg:grid lg:grid-cols-[minmax(0,48rem)_16rem] lg:gap-10">
       <div className="min-w-0">
        {loading && (
          <div className="flex items-center justify-center py-24 text-gray-400 gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> Loading…
          </div>
        )}
        {error && !loading && (
          <div className="text-center py-24 text-gray-500">{error}</div>
        )}

        {run && !loading && !error && (
          <>

            {/* Vertical stage flow */}
            <div>
              {run.stages.filter((st) => st.id !== 'brief').map((stage, i) => (
                <StageCard
                  key={stage.id}
                  stage={stage}
                  index={i}
                  isLast={i === run.stages.filter((st) => st.id !== 'brief').length - 1}
                >
                  {renderStage(
                    stage,
                    run.feedback || [],
                    handleSubmitFeedback,
                    submitting
                  ,
                    (run.stages.find((x) => x.id === 'keywords')?.artifact?.keywords || []),
                    run.id)}
                </StageCard>
              ))}
            </div>

            {/* What is happening NOW, where the next stage will appear. One
                line, in words. The full log lives in the rail on wide screens. */}
            {(run.status === 'running' || live) && (
              <div className="flex items-center gap-3 pl-1 mt-2 text-gray-800">
                <Loader2 className="w-4 h-4 animate-spin text-action-500 shrink-0" />
                <span className="text-sm">
                  {activity.length ? currentActivity(activity) : 'Starting'}…
                </span>
              </div>
            )}
          </>
        )}
       </div>
       {/* Desktop only: the steps so far, newest last. On a phone this would
           push the artefact itself below the fold, so it is not shown. */}
       {activity.length > 0 && (
         <aside className="hidden lg:block pt-2">
           <div className="sticky top-20 text-xs text-gray-500">
             <div className="font-semibold text-gray-700 mb-2">Steps</div>
             <ol className="space-y-1.5">
               {dedupeLabels(activity).slice(-14).map((l, i, arr) => (
                 <li key={i} className={`flex gap-2 ${i === arr.length - 1 && run?.status === 'running' ? 'text-gray-800' : ''}`}>
                   <span className="shrink-0">{i === arr.length - 1 && run?.status === 'running' ? '›' : '✓'}</span>
                   <span>{l}</span>
                 </li>
               ))}
             </ol>
           </div>
         </aside>
       )}
      </div>

      {/* The conversation, on the artefact. The last exchange shows so a
          reply is visible without leaving; the box sends into the same
          session. While a run streams it steers instead. */}
      {onSend && (
        <div className="sticky bottom-0 z-20 border-t border-surface-300 bg-surface-50/95 backdrop-blur">
          <div className="max-w-3xl lg:max-w-6xl mx-auto px-6 py-3">
            {/* One line, not the transcript: while it runs, the progress is
                already on the artefact; once it answers, the reply — clamped,
                expandable — sits here where you asked. */}
            {(() => {
              const last = [...recent].reverse().find((m) => m.role === 'assistant');
              if (!last || isStreaming || !last.content) return null;
              return (
                <div className="mb-2 text-sm text-gray-700 bg-white border border-surface-300 rounded-xl px-4 py-2.5">
                  <details>
                    <summary className="cursor-pointer list-none">
                      <span className="line-clamp-2">{last.content}</span>
                      <span className="text-xs text-gray-400">show the full reply</span>
                    </summary>
                    <div className="mt-2 prose prose-sm max-w-none max-h-64 overflow-y-auto">
                      <ReactMarkdown>{last.content}</ReactMarkdown>
                    </div>
                  </details>
                </div>
              );
            })()}
            <div className="flex items-end gap-2">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    submitDraft();
                  }
                }}
                rows={1}
                placeholder={isStreaming ? 'Steer it — this stops the current step and sends your correction' : 'Ask a follow-up, or change something: "drop the courses cluster"'}
                className="flex-1 resize-none rounded-xl border border-surface-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-action-400"
              />
              {isStreaming && onStop && (
                <button onClick={onStop} title="Stop" className="p-2.5 rounded-xl border border-surface-300 bg-white text-gray-600 hover:bg-surface-100">
                  <Square className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={submitDraft}
                disabled={!draft.trim()}
                title={isStreaming ? 'Steer' : 'Send'}
                className="px-4 py-2.5 rounded-xl bg-action-300 text-primary-700 hover:bg-action-400 hover:text-white text-sm font-semibold disabled:opacity-60 disabled:hover:bg-action-300 disabled:hover:text-primary-700 flex items-center gap-1.5 transition"
              >
                {isStreaming ? 'Steer' : <Send className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
