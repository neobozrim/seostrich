'use client';

import React from 'react';
import {
  ClipboardList,
  Sprout,
  Search,
  Boxes,
  Columns3,
  CalendarDays,
  Wrench,
  Crosshair,
  FileText,
  Quote,
  Gavel,
  Target,
  Sparkles,
  Workflow,
  type LucideIcon,
} from 'lucide-react';

/**
 * Stage icons: Lucide glyphs in a brand-coloured disc.
 *
 * These were hand-drawn SVG cut-outs imitating the logo's negative-space
 * technique. At icon size that read as crude blobs — the mark works because it
 * is one considered shape at large size, not because the technique scales down
 * to a set of twelve. Lucide's grid, weights and optical balance are the point
 * of using it; the brand comes from the disc and the palette around it.
 */

type Tone = 'brand' | 'ink' | 'clay';

const TONE: Record<Tone, { bg: string; fg: string }> = {
  // the logo's own pairing: brown disc, sand glyph
  brand: { bg: 'bg-primary-400', fg: 'text-surface-200' },
  // the account avatar, so it reads apart from the pipeline stages
  ink: { bg: 'bg-secondary-900', fg: 'text-surface-200' },
  // services, which are a different class of thing from saved work. A lighter
  // clay disc with a dark glyph was too low-contrast at 36px — it read as
  // greyed-out rather than as a different category.
  clay: { bg: 'bg-accent-400', fg: 'text-surface-100' },
};

const ICONS: Record<string, { icon: LucideIcon; tone: Tone }> = {
  intake: { icon: ClipboardList, tone: 'brand' },
  seeds: { icon: Sprout, tone: 'brand' },
  keywords: { icon: Search, tone: 'brand' },
  clusters: { icon: Boxes, tone: 'brand' },
  pillars: { icon: Columns3, tone: 'brand' },
  mix: { icon: CalendarDays, tone: 'brand' },
  audit: { icon: Wrench, tone: 'brand' },
  competitors: { icon: Crosshair, tone: 'brand' },
  onpage: { icon: FileText, tone: 'brand' },
  ai_citability: { icon: Quote, tone: 'brand' },
  judge: { icon: Gavel, tone: 'ink' },
  flow_keyword_strategy: { icon: Target, tone: 'clay' },
  flow_geo_demand: { icon: Sparkles, tone: 'clay' },
};

const FALLBACK = { icon: Workflow, tone: 'brand' as Tone };

export function StageIcon({
  stage,
  className = 'w-9 h-9',
}: {
  stage: string;
  className?: string;
}) {
  const { icon: Icon, tone } = ICONS[stage] || FALLBACK;
  const { bg, fg } = TONE[tone];
  return (
    <span
      className={`${bg} ${className} inline-flex items-center justify-center rounded-full shrink-0`}
      role="img"
      aria-label={stage.replace(/_/g, ' ')}
    >
      {/* 55% of the disc keeps the glyph optically centred at every size */}
      <Icon className={`${fg} w-[55%] h-[55%]`} strokeWidth={2} />
    </span>
  );
}
