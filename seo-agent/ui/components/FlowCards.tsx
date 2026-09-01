'use client';

import React, { useEffect, useState } from 'react';
import { Target, Sparkles, Workflow, ArrowRight, Lock } from 'lucide-react';
import { getFlows, FlowCatalog, FlowCard } from '@/lib/api';

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  target: Target,
  sparkles: Sparkles,
  workflow: Workflow,
};

// Opening line per flow. The agent still asks for whatever is missing — these
// just save the user typing the obvious part.
const STARTERS: Record<string, string> = {
  keyword_strategy:
    "I want a content strategy. My business is: ",
  geo_demand:
    "I want to know how AI engines answer questions in my space. The topics are: ",
};

interface Props {
  onPick: (prompt: string) => void;
}

export function FlowCards({ onPick }: Props) {
  const [catalog, setCatalog] = useState<FlowCatalog | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    getFlows(ctrl.signal)
      .then(setCatalog)
      .catch(() => setFailed(true));
    return () => ctrl.abort();
  }, []);

  if (failed || !catalog?.flows?.length) return null;

  return (
    <div className="w-full max-w-3xl mx-auto px-4">
      <p className="text-sm text-gray-500 mb-3 text-center">
        Pick a flow to jump straight in
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        {catalog.flows.map((flow: FlowCard) => {
          const Icon = ICONS[flow.icon] || Workflow;
          return (
            <button
              key={flow.id}
              onClick={() => onPick(STARTERS[flow.id] ?? `Run the ${flow.label} flow. `)}
              className="group text-left rounded-lg border border-surface-300 bg-white p-4
                         hover:border-gray-400 hover:shadow-sm transition"
            >
              <div className="flex items-start gap-3">
                <Icon className="w-5 h-5 mt-0.5 text-gray-500 group-hover:text-gray-900 shrink-0" />
                <div className="min-w-0">
                  <div className="font-medium text-gray-900">{flow.label}</div>
                  <div className="text-sm text-gray-500">{flow.tagline}</div>
                </div>
              </div>

              <ol className="mt-3 space-y-1">
                {flow.nodes.slice(0, 4).map((node, i) => (
                  <li key={i} className="text-xs text-gray-500 flex gap-2">
                    <span className="text-gray-400 tabular-nums">{i + 1}.</span>
                    <span className="truncate">{node}</span>
                  </li>
                ))}
                {flow.nodes.length > 4 && (
                  <li className="text-xs text-gray-400 pl-5">
                    +{flow.nodes.length - 4} more
                  </li>
                )}
              </ol>

              {flow.required_inputs.length > 0 && (
                <div className="mt-3 pt-2 border-t border-surface-200 text-xs text-gray-500">
                  Asks first:{' '}
                  {flow.required_inputs.map((i) => i.label).join(' · ')}
                </div>
              )}

              <div className="mt-2 text-xs text-gray-400 group-hover:text-gray-700 flex items-center gap-1">
                Start <ArrowRight className="w-3 h-3" />
              </div>
            </button>
          );
        })}
      </div>

      {catalog.planned?.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 justify-center">
          <span className="text-xs text-gray-400">Coming next:</span>
          {catalog.planned.map((p) => (
            <span
              key={p.id}
              className="inline-flex items-center gap-1 text-xs text-gray-400
                         border border-surface-300 rounded px-2 py-0.5"
            >
              <Lock className="w-3 h-3" />
              {p.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
