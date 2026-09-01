'use client';

// Throwaway preview page for checking the icon set at real size.
// Not linked from anywhere; delete once the icons are settled.
import React from 'react';
import { StageIcon } from '@/components/StageIcon';

const STAGES = [
  'intake', 'seeds', 'keywords', 'clusters', 'pillars',
  'mix', 'audit', 'competitors', 'onpage', 'ai_citability', 'judge',
];

export default function IconPreview() {
  return (
    <div className="p-10 bg-surface-50 min-h-screen">
      <div className="flex flex-wrap gap-8">
        {STAGES.map((s) => (
          <div key={s} className="text-center">
            <StageIcon stage={s} className="w-16 h-16" />
            <div className="text-[11px] text-gray-500 mt-1">{s}</div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-4 mt-10 items-center">
        {STAGES.map((s) => (
          <StageIcon key={s} stage={s} className="w-6 h-6" />
        ))}
        <span className="text-xs text-gray-400 ml-2">at 24px</span>
      </div>
      <div className="flex gap-4 mt-8 items-center">
        <img src="/logo/seostrich-mark.svg" alt="" className="w-16 h-16" />
        <span className="text-xs text-gray-400">the mark, for comparison</span>
      </div>
    </div>
  );
}
