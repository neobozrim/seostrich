'use client';

import React from 'react';
import { MemoryState } from '@/types';

interface MemoryPanelProps {
  memory: MemoryState;
}

export function MemoryPanel({ memory }: MemoryPanelProps) {
  const sections = [
    {
      key: 'facts',
      label: 'Facts',
      description: 'Verified information',
      borderColor: 'border-secondary-300',
    },
    {
      key: 'learnings',
      label: 'Learnings',
      description: 'Insights and patterns',
      borderColor: 'border-accent-400',
    },
    {
      key: 'decisions',
      label: 'Decisions',
      description: 'Choices and rationale',
      borderColor: 'border-primary-400',
    },
    {
      key: 'tasks',
      label: 'Tasks',
      description: 'Active work items',
      borderColor: 'border-surface-400',
    },
  ];

  return (
    <div className="h-full overflow-y-auto bg-surface-50">
      <div className="sticky top-0 bg-surface-100 border-b border-surface-300 p-4 pr-12">
        <h2 className="text-lg font-semibold text-primary-700">Agent Memory</h2>
        <p className="text-sm text-gray-500">Persistent knowledge base</p>
      </div>

      <div className="p-4 space-y-6">
        {sections.map(({ key, label, description, borderColor }) => {
          const items = memory[key as keyof MemoryState] || [];
          return (
            <div key={key}>
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-semibold text-gray-800">{label}</h3>
                <span className="text-xs text-gray-500 bg-surface-200 px-2 py-0.5 rounded">
                  {items.length}
                </span>
              </div>
              <p className="text-xs text-gray-500 mb-2">{description}</p>

              {items.length === 0 ? (
                <p className="text-sm text-gray-400 italic">No entries yet</p>
              ) : (
                <ul className="space-y-2">
                  {items.map((item, index) => (
                    <li
                      key={index}
                      className={`text-sm p-2 bg-white rounded border-l-2 ${borderColor}`}
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
