'use client';

import React from 'react';
import { Message } from '@/types';
import ReactMarkdown from 'react-markdown';
import { Loader2, Check } from 'lucide-react';
import { activityLabel } from '@/lib/activity';

interface ChatMessageProps {
  message: Message;
}

/**
 * What an assistant turn shows while it works: ONE line saying what the agent
 * is on right now, and beneath it the steps already done — in words, with
 * no tool names, arguments or timings. The old view listed every tool call
 * with its JSON args and a stopwatch; that is a debugger, not a status.
 */
function progressLines(message: Message): string[] {
  const lines: string[] = [];
  for (const ev of message.activity || []) {
    // A tool's start and end say the same thing; keep one of them.
    if (ev.kind === 'tool_end' && ev.success) continue;
    if (ev.kind === 'llm_round') continue;
    const label = activityLabel(ev);
    if (label && lines[lines.length - 1] !== label) lines.push(label);
  }
  return lines;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const working = !isUser && !message.content && (message.statusText || (message.activity || []).length > 0);
  const lines = isUser ? [] : progressLines(message);
  const current = message.statusText && lines[lines.length - 1] !== message.statusText
    ? message.statusText
    : lines[lines.length - 1];
  const done = message.content ? lines : lines.slice(0, -1);

  return (
    <div className={`flex p-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className="max-w-[85%]">
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? 'bg-primary-400 text-white rounded-br-md'
              : 'bg-secondary-300 text-gray-900 rounded-bl-md'
          }`}
        >
          {working && (
            <div className="space-y-1">
              {done.map((l, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
                  <Check className="w-3 h-3 text-green-600 shrink-0" />
                  <span>{l}</span>
                </div>
              ))}
              <div className="flex items-center gap-2 text-sm text-gray-800">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-primary-500 shrink-0" />
                <span>{current || 'Working'}…</span>
              </div>
            </div>
          )}

          {message.content && (
            <div className={`prose prose-sm max-w-none ${isUser ? 'prose-invert' : ''}`}>
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}

          {/* Once the answer is in, the steps fold away but stay reachable. */}
          {message.content && !isUser && done.length > 0 && (
            <details className="mt-2 text-xs text-gray-500">
              <summary className="cursor-pointer hover:text-gray-700">
                What it did · {done.length} step{done.length === 1 ? '' : 's'}
              </summary>
              <ul className="mt-1 space-y-0.5">
                {done.map((l, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <Check className="w-3 h-3 text-green-600 shrink-0" />
                    <span>{l}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>

        <div className={`text-xs text-gray-400 mt-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date(message.timestamp).toLocaleTimeString()}
        </div>

        {message.attachments && message.attachments.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {message.attachments.map((file) => (
              <div key={file.id} className="flex items-center gap-2 px-3 py-1 bg-gray-100 rounded-full text-sm">
                <span>{file.name}</span>
                <span className="text-gray-500">({(file.size / 1024).toFixed(1)} KB)</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
