'use client';

import React from 'react';

/**
 * Stage icons in the brand mark's language.
 *
 * The SEOstrich logo is a SOLID filled disc with no outline ring, and the
 * ostrich's neck is a NEGATIVE-SPACE channel cut through the disc that runs
 * out past its edge — so the silhouette is notched rather than a tidy circle.
 * That is the signature; a contained glyph inside a ring reads as a generic
 * icon set, which is what the emoji placeholders were.
 *
 * So each icon is built the same way the logo is: a filled shape masked by a
 * white disc with black cut-outs, at least one of which crosses r=15 and
 * breaks the edge. Drawn in a 40x40 box, disc r=15 at (20,20).
 */

type Tone = 'brand' | 'ink' | 'sand';

const DISC: Record<Tone, string> = {
  brand: '#6B4226', // the logo's brown
  ink: '#191411',
  sand: '#C9A487', // muted clay: services read apart from the brown work cards
};

/** Cut-outs per stage. Stroke width is the channel width, as in the logo. */
const CUTS: Record<string, { tone: Tone; cuts: React.ReactNode }> = {
  // Intake — a pen stroke running out of the lower left
  intake: {
    tone: 'brand',
    cuts: (
      <>
        <path d="M28 10 L 12 26" strokeWidth="6" />
        {/* nib, narrowing to a point past the edge */}
        <path d="M12 26 L 4 34" strokeWidth="2.5" />
      </>
    ),
  },
  // Seeds — a shoot breaking the top edge, with one leaf
  seeds: {
    tone: 'brand',
    cuts: (
      <>
        <path d="M20 30 L 20 0" strokeWidth="5" />
        <path d="M20 15 C 27 13, 30 9, 30 3" strokeWidth="4.5" />
      </>
    ),
  },
  // Keyword discovery — a lens whose handle leaves the disc
  keywords: {
    tone: 'brand',
    cuts: (
      <>
        <circle cx="17" cy="16" r="6" strokeWidth="4.5" fill="none" />
        <path d="M22 21 L 40 39" strokeWidth="6" />
      </>
    ),
  },
  // Clusters — a group, and one member pulled outside
  clusters: {
    tone: 'brand',
    cuts: (
      <>
        <circle cx="14" cy="16" r="3.2" strokeWidth="0" />
        <circle cx="23" cy="14" r="3.2" strokeWidth="0" />
        <circle cx="17" cy="25" r="3.2" strokeWidth="0" />
        <path d="M26 22 L 40 33" strokeWidth="5" />
      </>
    ),
  },
  // Pillars — columns, the centre one through the top edge
  pillars: {
    tone: 'brand',
    cuts: (
      <>
        <path d="M12 30 L 12 10" strokeWidth="4.5" />
        <path d="M20 30 L 20 0" strokeWidth="4.5" />
        <path d="M28 30 L 28 10" strokeWidth="4.5" />
      </>
    ),
  },
  // Calendar — rows, and a marker overshooting the top right
  mix: {
    tone: 'brand',
    cuts: (
      <>
        {/* week columns */}
        <path d="M14 12 V 29" strokeWidth="4" />
        <path d="M22 12 V 29" strokeWidth="4" />
        {/* the header rule, running out past the right edge */}
        <path d="M8 14 H 40" strokeWidth="4.5" />
      </>
    ),
  },
  // Technical audit — a wrench out of the bottom right
  audit: {
    tone: 'brand',
    cuts: (
      <>
        <circle cx="15" cy="15" r="5.5" strokeWidth="4.5" fill="none" />
        <path d="M19 19 L 40 40" strokeWidth="6.5" />
      </>
    ),
  },
  // Competitors — a target with a line arriving from outside
  competitors: {
    tone: 'brand',
    cuts: (
      <>
        <circle cx="19" cy="21" r="4.5" strokeWidth="4" fill="none" />
        <path d="M22 18 L 40 2" strokeWidth="5" />
      </>
    ),
  },
  // On-page — text rows with the top line running off
  onpage: {
    tone: 'brand',
    cuts: (
      <>
        {/* body copy */}
        <path d="M12 20 H 28" strokeWidth="3.5" />
        <path d="M12 26 H 24" strokeWidth="3.5" />
        {/* the H1, overshooting the disc */}
        <path d="M12 13 H 38" strokeWidth="5" />
      </>
    ),
  },
  // AI citability — a quote, cited outward
  ai_citability: {
    tone: 'brand',
    cuts: (
      <>
        <circle cx="15" cy="17" r="3.4" strokeWidth="0" />
        <circle cx="24" cy="17" r="3.4" strokeWidth="0" />
        <path d="M24 23 L 40 37" strokeWidth="5" />
      </>
    ),
  },
  // The judge / account avatar — a gavel striking, handle out of frame
  judge: {
    tone: 'ink',
    cuts: (
      <>
        {/* mallet head, angled out through the top-left edge */}
        <path d="M7 15 L 24 3" strokeWidth="7" />
        {/* handle, out through the bottom-right */}
        <path d="M14 10 L 33 31" strokeWidth="4.5" />
        {/* the block it strikes, contained */}
        <path d="M11 32 H 29" strokeWidth="4" />
      </>
    ),
  },
  // ---- Flow marks. Sand disc so the service cards read as a different
  // ---- class of thing from the brown work cards. ----

  // Content strategy — pillars rising, the centre one out through the top
  flow_keyword_strategy: {
    tone: 'sand',
    cuts: (
      <>
        <path d="M11 31 L 11 14" strokeWidth="4.5" />
        <path d="M20 31 L 20 0" strokeWidth="5" />
        <path d="M29 31 L 29 14" strokeWidth="4.5" />
        <path d="M8 31 H 32" strokeWidth="3.5" />
      </>
    ),
  },
  // AI visibility — a quote being carried outward as a citation
  flow_geo_demand: {
    tone: 'sand',
    cuts: (
      <>
        <circle cx="15" cy="16" r="3.6" strokeWidth="0" />
        <circle cx="25" cy="16" r="3.6" strokeWidth="0" />
        <path d="M20 23 L 40 38" strokeWidth="5" />
      </>
    ),
  },
};

const FALLBACK = { tone: 'brand' as Tone, cuts: <path d="M20 30 L 20 0" strokeWidth="5" /> };

export function StageIcon({
  stage,
  className = 'w-6 h-6',
}: {
  stage: string;
  className?: string;
}) {
  const mark = CUTS[stage] || FALLBACK;
  // Mask ids must be unique per stage or the first one wins for every instance.
  const id = `mk-${stage}`;
  return (
    <svg viewBox="0 0 40 40" className={className} role="img" aria-label={stage}>
      <defs>
        <mask id={id} maskUnits="userSpaceOnUse" x="0" y="0" width="40" height="40">
          <circle cx="20" cy="20" r="15" fill="#fff" />
          <g stroke="#000" fill="#000" strokeLinecap="round" strokeLinejoin="round">
            {mark.cuts}
          </g>
        </mask>
      </defs>
      <rect width="40" height="40" fill={DISC[mark.tone]} mask={`url(#${id})`} />
    </svg>
  );
}
