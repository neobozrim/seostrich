'use client';

import React from 'react';
import { Message, ToolCall } from '@/types';
import ReactMarkdown from 'react-markdown';
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { activityLabel } from '@/lib/activity';

interface ChatMessageProps {
  message: Message;
  onViewRun?: () => void;
}

const STAGE_ICONS: Record<string, string> = {
  intake: '📝',
  seeds: '🌱',
  keywords: '🔎',
  clusters: '🧩',
  pillars: '🏛️',
  mix: '🗓️',
  audit: '🔧',
  competitors: '🎯',
  onpage: '📄',
  ai_citability: '🤖',
};

export function ChatMessage({ message, onViewRun }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isTyping = !isUser && !message.content && message.statusText;

  return (
    <div className={`flex p-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] ${isUser ? 'order-1' : 'order-1'}`}>
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? 'bg-primary-400 text-white rounded-br-md'
              : 'bg-secondary-300 text-gray-900 rounded-bl-md'
          }`}
        >
          {/* Status indicator */}
          {message.statusText && (
            <div className={`flex items-center gap-1 text-xs mb-1 ${isUser ? 'opacity-80' : 'text-gray-600'}`}>
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>{message.statusText}</span>
            </div>
          )}

          {/* Live activity feed — what the agent is doing between stages */}
          {!isUser && message.activity && message.activity.length > 0 && (
            <div className="text-[11px] leading-5 mb-1 text-gray-500 font-mono space-y-0.5">
              {message.activity.slice(-6).map((ev, i) => (
                <div key={i}>{activityLabel(ev)}</div>
              ))}
            </div>
          )}

          {/* Typing indicator when no content yet */}
          {isTyping && (
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
            </div>
          )}

          {/* Message content */}
          {message.content && (
            <div className={`prose prose-sm max-w-none ${isUser ? 'prose-invert' : ''}`}>
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Timestamp */}
        <div className={`text-xs text-gray-400 mt-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date(message.timestamp).toLocaleTimeString()}
        </div>

        {/* Pipeline stages recorded during this reply */}
        {message.stages && message.stages.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-xs text-gray-500">Pipeline updated:</span>
            {message.stages.map((s, i) => (
              <button
                key={i}
                onClick={onViewRun}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-surface-300 rounded-full text-xs text-gray-700 hover:border-primary-400 hover:text-primary-700 transition-colors"
                title={`Open ${s.label} in the pipeline view`}
              >
                <span>{STAGE_ICONS[s.stage_id] || '▸'}</span>
                <span className="font-medium">{s.label}</span>
              </button>
            ))}
          </div>
        )}

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mt-2 space-y-2">
            {message.toolCalls.map((tool) => (
              <ToolCallCard key={tool.id} tool={tool} />
            ))}
          </div>
        )}

        {/* Attachments */}
        {message.attachments && message.attachments.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {message.attachments.map((file) => (
              <div
                key={file.id}
                className="flex items-center gap-2 px-3 py-1 bg-gray-100 rounded-full text-sm"
              >
                <span>{file.name}</span>
                <span className="text-gray-500">
                  ({(file.size / 1024).toFixed(1)} KB)
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ToolCallCard({ tool }: { tool: ToolCall }) {
  const StatusIcon = {
    running: Loader2,
    success: CheckCircle2,
    error: XCircle,
  }[tool.status];

  const statusColor = {
    running: 'text-blue-500',
    success: 'text-green-500',
    error: 'text-red-500',
  }[tool.status];

  return (
    <div className="border border-surface-300 rounded-lg p-3 bg-surface-100">
      <div className="flex items-center gap-2 mb-2">
        <StatusIcon className={`w-4 h-4 ${statusColor} ${
          tool.status === 'running' ? 'animate-spin' : ''
        }`} />
        <span className="font-mono text-sm font-semibold text-primary-700">{tool.tool}</span>
        {tool.endTime && tool.startTime && (
          <span className="text-xs text-gray-500 ml-auto">
            {((tool.endTime.getTime() - tool.startTime.getTime()) / 1000).toFixed(2)}s
          </span>
        )}
      </div>

      {Object.keys(tool.args).length > 0 && (
        <div className="text-xs text-gray-600 mb-2">
          <span className="font-semibold">Args:</span>{' '}
          <code className="bg-white px-2 py-1 rounded">
            {JSON.stringify(tool.args, null, 2)}
          </code>
        </div>
      )}

      {tool.result && (
        <details className="text-xs">
          <summary className="cursor-pointer text-gray-600 hover:text-gray-900">
            View result
          </summary>
          <pre className="mt-2 p-2 bg-white rounded overflow-auto max-h-40">
            {JSON.stringify(tool.result, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
