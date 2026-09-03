'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { X, Search, Sparkles } from 'lucide-react';
import { getRuns, getRun } from '@/lib/api';

/**
 * The two ways in, and the questionnaire behind each.
 *
 * A form, not a conversation: five or six answers compile into the brief the
 * graph already reads, previewed live, sent through the same path as typed
 * text. Deterministic, no model call per question, and the market cannot be
 * skipped — the one thing the pipeline must never guess.
 */
export type DiscoveryKind = 'strategy' | 'geo';

// Mirrors src/market.py MARKETS: the markets the gate accepts, with the
// languages DataForSEO serves for each, most common first.
const MARKETS: Array<{ key: string; country: string; languages: string[] }> = [
  { key: 'US', country: 'United States', languages: ['en', 'es'] },
  { key: 'UK', country: 'United Kingdom', languages: ['en'] },
  { key: 'IE', country: 'Ireland', languages: ['en'] },
  { key: 'CA', country: 'Canada', languages: ['en', 'fr'] },
  { key: 'AU', country: 'Australia', languages: ['en'] },
  { key: 'DE', country: 'Germany', languages: ['de', 'en'] },
  { key: 'FR', country: 'France', languages: ['fr', 'en'] },
  { key: 'ES', country: 'Spain', languages: ['es', 'en'] },
  { key: 'IT', country: 'Italy', languages: ['it', 'en'] },
  { key: 'NL', country: 'Netherlands', languages: ['nl', 'en'] },
  { key: 'BE', country: 'Belgium', languages: ['nl', 'fr', 'en'] },
  { key: 'PL', country: 'Poland', languages: ['pl', 'en'] },
  { key: 'RO', country: 'Romania', languages: ['ro', 'en'] },
  { key: 'GR', country: 'Greece', languages: ['el', 'en'] },
  { key: 'BG', country: 'Bulgaria', languages: ['bg', 'en'] },
];
const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English', es: 'Spanish', fr: 'French', de: 'German', it: 'Italian', nl: 'Dutch',
  pl: 'Polish', ro: 'Romanian', el: 'Greek', bg: 'Bulgarian',
};

const GOALS = [
  { key: 'sales', label: 'Increase sales', text: 'increase sales — bring in people ready to buy' },
  { key: 'awareness', label: 'Increase awareness', text: 'increase awareness — be found by people who do not know us yet' },
  { key: 'reposition', label: 'Reposition the business', text: 'reposition the business — be found for what we are becoming, not what we were' },
  { key: 'other', label: 'Something else', text: '' },
];

const lines = (s: string) => s.split(/\n|,/).map((x) => x.trim()).filter(Boolean);

export function compileStrategyBrief(f: StrategyAnswers): string {
  const name = f.name.trim() || 'the business';
  const goal = f.goal === 'other' ? f.goalText.trim() : (GOALS.find((g) => g.key === f.goal)?.text || '');
  const out: string[] = [];
  out.push(`Build the SEO content strategy for ${name}.`);
  out.push('');
  out.push(`${name}${f.site.trim() ? ` (${f.site.trim()})` : ''}: ${f.description.trim()}`);
  if (goal) out.push(`Goal: ${goal}.`);
  if (f.audience.trim()) out.push(`Audience: ${f.audience.trim()}.`);
  if (f.site.trim()) out.push(`Website: ${f.site.trim()}`);
  const pages = lines(f.pages);
  if (pages.length) out.push(`Our pages: ${pages.join(', ')}`);
  const comps = lines(f.competitors);
  if (comps.length) {
    out.push('Competitors — see what they rank for and where the gaps are:');
    for (const c of comps) out.push(`- ${c}`);
  } else {
    out.push('Competitors: none named — find the closest ones.');
  }
  out.push(`Market: ${f.country}, ${LANGUAGE_NAMES[f.language] || f.language}.`);
  if (f.exclude.trim()) out.push(`Not going after: ${f.exclude.trim()}.`);
  return out.join('\n');
}

export function compileGeoBrief(f: GeoAnswers): string {
  const name = f.name.trim() || 'the business';
  const site = f.site.trim();
  const out: string[] = [];
  out.push(`Run the AI visibility (GEO) report for ${name}${site ? ` (${site})` : ''}. Market: ${f.country}, ${LANGUAGE_NAMES[f.language] || f.language}.`);
  if (f.description.trim()) out.push(f.description.trim());
  const topics = lines(f.topics);
  if (topics.length) out.push(`Topics to measure: ${topics.join(', ')}.`);
  if (site) out.push(`Also check which AI answers already cite ${site}.`);
  const comps = lines(f.compare);
  if (comps.length) out.push(`Also compare against: ${comps.join(', ')}.`);
  return out.join('\n');
}

export interface StrategyAnswers {
  name: string; description: string; site: string; pages: string; goal: string; goalText: string;
  audience: string; competitors: string; country: string; language: string; exclude: string;
}
export interface GeoAnswers {
  name: string; site: string; description: string; country: string; language: string; topics: string; compare: string;
}

const EMPTY_STRATEGY: StrategyAnswers = {
  name: '', description: '', site: '', pages: '', goal: 'awareness', goalText: '', audience: '',
  competitors: '', country: 'United States', language: 'en', exclude: '',
};
const EMPTY_GEO: GeoAnswers = { name: '', site: '', description: '', country: 'United States', language: 'en', topics: '', compare: '' };

// ---------------------------------------------------------------------------

/** The two cards. Home puts them above the reports; a new chat under GET FOUND. */
export function DiscoveryCtas({ onPick, compact = false }: { onPick: (kind: DiscoveryKind) => void; compact?: boolean }) {
  const card = 'flex-1 min-w-[15rem] text-left rounded-xl border border-surface-300 bg-white hover:border-action-400 hover:shadow-sm transition px-4 py-3';
  return (
    <div className={`flex flex-col sm:flex-row gap-3 ${compact ? '' : 'w-full'}`}>
      <button onClick={() => onPick('strategy')} className={card}>
        <div className="flex items-center gap-2 text-base font-semibold text-gray-900">
          <Search className="w-4 h-4 text-action-500" /> Create SEO strategy
        </div>
        <div className="text-sm text-gray-500 mt-0.5">Six questions, then the strategy builds in front of you: keywords, competitors, themes, the brief.</div>
      </button>
      <button onClick={() => onPick('geo')} className={card}>
        <div className="flex items-center gap-2 text-base font-semibold text-gray-900">
          <Sparkles className="w-4 h-4 text-action-500" /> Analyse AI visibility
        </div>
        <div className="text-sm text-gray-500 mt-0.5">Which questions AI engines already answer on your topics, who they cite, and where you stand.</div>
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------

const FIELD = 'w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:outline-none focus:border-action-400';
const LABEL = 'text-sm font-semibold text-gray-700';
const HINT = 'text-sm text-gray-500';

function Field({ label, hint, children, required }: { label: string; hint?: string; children: React.ReactNode; required?: boolean }) {
  return (
    <label className="block">
      <div className={LABEL}>{label}{required && <span className="text-action-500"> *</span>}</div>
      {hint && <div className={`${HINT} mb-1`}>{hint}</div>}
      {children}
    </label>
  );
}

function MarketFields({ country, language, onChange }: { country: string; language: string; onChange: (c: string, l: string) => void }) {
  const m = MARKETS.find((x) => x.country === country) || MARKETS[0];
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label="Country" required hint="Where your customers search from.">
        <select
          value={country}
          onChange={(e) => {
            const next = MARKETS.find((x) => x.country === e.target.value) || MARKETS[0];
            onChange(next.country, next.languages.includes(language) ? language : next.languages[0]);
          }}
          className={FIELD}
        >
          {MARKETS.map((x) => <option key={x.key} value={x.country}>{x.country}</option>)}
        </select>
      </Field>
      <Field label="Language" required hint="The language they search in.">
        <select value={language} onChange={(e) => onChange(country, e.target.value)} className={FIELD}>
          {m.languages.map((l) => <option key={l} value={l}>{LANGUAGE_NAMES[l] || l}</option>)}
        </select>
      </Field>
    </div>
  );
}

export function DiscoveryForm({ kind, onClose, onSubmit }: { kind: DiscoveryKind; onClose: () => void; onSubmit: (brief: string) => void }) {
  const [st, setSt] = useState<StrategyAnswers>(EMPTY_STRATEGY);
  const [geo, setGeo] = useState<GeoAnswers>(EMPTY_GEO);
  const [prefillNote, setPrefillNote] = useState<string>('');

  // GEO: the strategy on the canvas already chose the themes; start from them.
  useEffect(() => {
    if (kind !== 'geo') return;
    let cancelled = false;
    (async () => {
      try {
        const runs = await getRuns();
        const pick = runs.find((r: any) => r.pinned && r.flow === 'SEO content strategy') || runs.find((r: any) => r.flow === 'SEO content strategy');
        if (!pick) return;
        const run = await getRun(pick.id);
        if (cancelled) return;
        const clusters = run.stages?.find((s: any) => s.id === 'clusters')?.artifact?.clusters || [];
        const terms = clusters.map((c: any) => c.head_term || c.cluster_name).filter(Boolean).slice(0, 8);
        const site = run.project?.split(' · ')[0] || '';
        setGeo((g) => ({
          ...g,
          name: g.name || pick.title || '',
          site: g.site || (site.includes('.') ? site : ''),
          topics: g.topics || terms.join('\n'),
        }));
        if (terms.length) setPrefillNote(`Topics start from the selected themes of "${pick.title}" — edit freely.`);
      } catch {
        /* no prefill; the form still works */
      }
    })();
    return () => { cancelled = true; };
  }, [kind]);

  const brief = useMemo(() => (kind === 'strategy' ? compileStrategyBrief(st) : compileGeoBrief(geo)), [kind, st, geo]);
  const ready = kind === 'strategy'
    ? !!(st.name.trim() && st.description.trim() && st.country && st.language && (st.goal !== 'other' || st.goalText.trim()))
    : !!(geo.name.trim() && geo.site.trim() && geo.country && geo.language && lines(geo.topics).length >= 3);

  return (
    <div className="fixed inset-x-0 bottom-0 top-16 z-40 bg-surface-50 overflow-y-auto">
      <div className="max-w-3xl lg:max-w-6xl mx-auto px-6 pt-8 pb-28 lg:grid lg:grid-cols-[minmax(0,32rem)_minmax(0,1fr)] lg:gap-10">
        <div className="min-w-0">
          <div className="flex items-start justify-between gap-4 mb-1">
            <h1 className="text-2xl font-display text-primary-700">
              {kind === 'strategy' ? 'Create SEO strategy' : 'Analyse AI visibility'}
            </h1>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-surface-200 text-gray-500" title="Close">
              <X className="w-5 h-5" />
            </button>
          </div>
          <p className="text-sm text-gray-500 mb-6">
            {kind === 'strategy'
              ? 'Answer what you can. The brief on the right is what the strategy will be built from; you can edit it afterwards as a follow-up.'
              : 'Three things and it runs. The report measures what AI engines already answer on your topics and who they cite.'}
          </p>

          {kind === 'strategy' ? (
            <div className="space-y-5">
              <Field label="What is the business called?" required>
                <input value={st.name} onChange={(e) => setSt({ ...st, name: e.target.value })} className={FIELD} placeholder="Product Pirates Club" />
              </Field>
              <Field label="What does it do?" required hint="A few sentences, the way you would tell a friend. This is where the seeds come from.">
                <textarea value={st.description} onChange={(e) => setSt({ ...st, description: e.target.value })} rows={4} className={FIELD} placeholder="An AI community of practice for product people who learn by building…" />
              </Field>
              <Field label="Does it have a website?" hint="Optional. Your site and any pages of yours worth reading (blog, docs) — one per line.">
                <input value={st.site} onChange={(e) => setSt({ ...st, site: e.target.value })} className={`${FIELD} mb-2`} placeholder="https://example.com" />
                <textarea value={st.pages} onChange={(e) => setSt({ ...st, pages: e.target.value })} rows={2} className={FIELD} placeholder="https://example.com/blog" />
              </Field>
              <Field label="What do you want to happen?" required hint="What getting found should do for the business.">
                <div className="flex flex-wrap gap-2 mb-2">
                  {GOALS.map((g) => (
                    <button
                      key={g.key}
                      type="button"
                      onClick={() => setSt({ ...st, goal: g.key })}
                      className={`px-3 py-1.5 rounded-full text-sm border transition ${st.goal === g.key ? 'bg-action-300 border-action-400 text-primary-700 font-semibold' : 'bg-white border-surface-300 text-gray-700 hover:border-action-300'}`}
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
                {st.goal === 'other' && (
                  <input value={st.goalText} onChange={(e) => setSt({ ...st, goalText: e.target.value })} className={FIELD} placeholder="Tell me what you want to happen" />
                )}
              </Field>
              <Field label="Who is it for?" hint="One line: the person who should find you.">
                <input value={st.audience} onChange={(e) => setSt({ ...st, audience: e.target.value })} className={FIELD} placeholder="Product managers and product engineers who build with AI" />
              </Field>
              <Field label="Competitors to consider" hint="Optional, up to ten, one per line. The report shows what each ranks for and where the gaps are. Leave empty and the closest ones are found for you.">
                <textarea value={st.competitors} onChange={(e) => setSt({ ...st, competitors: e.target.value })} rows={3} className={FIELD} placeholder={'https://lennysnewsletter.com\nproductschool.com'} />
              </Field>
              <MarketFields country={st.country} language={st.language} onChange={(c, l) => setSt({ ...st, country: c, language: l })} />
              <Field label="Not going after" hint="Optional. Topics the strategy should stay away from.">
                <input value={st.exclude} onChange={(e) => setSt({ ...st, exclude: e.target.value })} className={FIELD} placeholder='"what is an LLM" explainers, prompt-engineering tips' />
              </Field>
            </div>
          ) : (
            <div className="space-y-5">
              <Field label="What is the business called?" required>
                <input value={geo.name} onChange={(e) => setGeo({ ...geo, name: e.target.value })} className={FIELD} placeholder="Braintrust" />
              </Field>
              <Field label="Its website" required hint="The report checks which AI answers already cite it.">
                <input value={geo.site} onChange={(e) => setGeo({ ...geo, site: e.target.value })} className={FIELD} placeholder="braintrust.dev" />
              </Field>
              <Field label="What does it do?" hint="Optional, one or two sentences — it keeps the topics on the right business (an LLM eval platform, not a talent marketplace).">
                <textarea value={geo.description} onChange={(e) => setGeo({ ...geo, description: e.target.value })} rows={2} className={FIELD} />
              </Field>
              <MarketFields country={geo.country} language={geo.language} onChange={(c, l) => setGeo({ ...geo, country: c, language: l })} />
              <Field label="The topics or questions you want to be the answer for" required hint={prefillNote || 'Three to ten, one per line.'}>
                <textarea value={geo.topics} onChange={(e) => setGeo({ ...geo, topics: e.target.value })} rows={6} className={FIELD} placeholder={'llm evaluation\nllm observability\nllm as a judge'} />
              </Field>
              <Field label="Also compare against" hint="Optional. Competitor domains to check for citations alongside yours.">
                <input value={geo.compare} onChange={(e) => setGeo({ ...geo, compare: e.target.value })} className={FIELD} placeholder="langfuse.com, langsmith.com" />
              </Field>
            </div>
          )}
        </div>

        {/* The brief, as it will be sent. */}
        <aside className="mt-8 lg:mt-0">
          <div className="lg:sticky lg:top-4">
            <div className="text-sm font-semibold text-gray-700 mb-1">Your request, as it will be sent</div>
            <pre className="whitespace-pre-wrap text-sm text-gray-700 bg-white border border-surface-300 rounded-xl px-4 py-3 leading-relaxed max-h-[60vh] overflow-y-auto font-sans">{brief}</pre>
            <div className="mt-3 flex items-center gap-3">
              <button
                onClick={() => ready && onSubmit(brief)}
                disabled={!ready}
                className="px-5 py-2 rounded-full bg-action-300 text-primary-700 hover:bg-action-400 hover:text-white font-semibold text-sm disabled:opacity-50 disabled:hover:bg-action-300 disabled:hover:text-primary-700 transition"
              >
                Go
              </button>
              {!ready && (
                <span className="text-sm text-gray-500">
                  {kind === 'strategy' ? 'Name, what it does and the market are needed.' : 'Name, website, market and at least three topics are needed.'}
                </span>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
