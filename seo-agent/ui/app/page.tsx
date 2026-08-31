'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Plus, X, Settings2, Workflow } from 'lucide-react';
import { Message, MemoryState, ToolCall } from '@/types';
import { ChatMessage } from '@/components/ChatMessage';
import { SystemPanel } from '@/components/SystemPanel';
import { RunView } from '@/components/RunView';
import { ProfileMenu } from '@/components/ProfileMenu';
import { LoginForm } from '@/components/LoginForm';
import {
  sendMessage,
  getMemory,
  checkAuth,
  clearToken,
  getUsername,
  AuthError,
} from '@/lib/api';
import { registerWebMcpTools } from '@/lib/webmcp';

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [attachments, setAttachments] = useState<File[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [memory, setMemory] = useState<MemoryState>({
    facts: [],
    learnings: [],
    decisions: [],
    tasks: [],
  });
  const [showSystem, setShowSystem] = useState(false);
  const [showRun, setShowRun] = useState(false);
  const [username, setUser] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [authed, setAuthed] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    addFiles(droppedFiles);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files);
      addFiles(selectedFiles);
    }
  };

  const addFiles = (newFiles: File[]) => {
    const allowedTypes = [
      'text/markdown',
      'text/csv',
      'application/pdf',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'text/plain',
    ];

    const validFiles = newFiles.filter((file) => {
      const ext = file.name.split('.').pop()?.toLowerCase();
      return allowedTypes.includes(file.type) ||
             ['md', 'csv', 'pdf', 'doc', 'docx', 'txt'].includes(ext || '');
    });

    const updatedFiles = [...attachments, ...validFiles].slice(0, 3);
    setAttachments(updatedFiles);
  };

  const removeAttachment = (index: number) => {
    setAttachments(attachments.filter((_, i) => i !== index));
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    checkAuth()
      .then(({ auth_required, authenticated }) => {
        setAuthRequired(auth_required);
        setAuthed(auth_required ? authenticated : true);
        setUser(getUsername());
      })
      .catch(() => {
        // API unreachable — proceed and let chat surface the error
        setAuthRequired(false);
        setAuthed(true);
      })
      .finally(() => setAuthReady(true));
  }, []);

  useEffect(() => {
    if (!authReady) return;
    if (authRequired && !authed) return;
    // Load initial memory state
    getMemory().then(setMemory).catch(console.error);
    // Expose the pipeline to in-browser AI agents via WebMCP
    registerWebMcpTools();
  }, [authReady, authRequired, authed]);

  // Handle browser back button to close panels
  useEffect(() => {
    if (!showSystem && !showRun) return;

    const handlePopState = () => {
      if (showRun) setShowRun(false);
      else if (showSystem) setShowSystem(false);
    };

    window.history.pushState({ panel: true }, '');
    window.addEventListener('popstate', handlePopState);

    return () => {
      window.removeEventListener('popstate', handlePopState);
      if (window.history.state?.panel) {
        window.history.back();
      }
    };
  }, [showSystem, showRun]);

  const handleSend = async () => {
    if (!input.trim() && attachments.length === 0) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: input,
      timestamp: new Date(),
      attachments: attachments.map((file) => ({
        id: crypto.randomUUID(),
        name: file.name,
        type: file.type,
        size: file.size,
      })),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setAttachments([]);
    setIsStreaming(true);

    const assistantMessage: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      toolCalls: [],
    };

    setMessages((prev) => [...prev, assistantMessage]);

    try {
      await sendMessage(input, attachments, sessionId, (chunk) => {
        if (chunk.type === 'session_id') {
          setSessionId(chunk.session_id);
        } else if (chunk.type === 'status') {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id
                ? { ...msg, statusText: chunk.content }
                : msg
            )
          );
        } else if (chunk.type === 'text') {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id
                ? { ...msg, content: msg.content + chunk.content, statusText: undefined }
                : msg
            )
          );
        } else if (chunk.type === 'tool_start') {
          const toolCall: ToolCall = {
            id: crypto.randomUUID(),
            tool: chunk.tool,
            args: chunk.args,
            status: 'running',
            startTime: new Date(),
          };
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id
                ? { ...msg, toolCalls: [...(msg.toolCalls || []), toolCall], statusText: `Running ${chunk.tool}...` }
                : msg
            )
          );
        } else if (chunk.type === 'tool_end') {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id
                ? {
                    ...msg,
                    toolCalls: msg.toolCalls?.map((tc) =>
                      tc.tool === chunk.tool
                        ? {
                            ...tc,
                            result: chunk.result,
                            status: chunk.success ? 'success' : 'error',
                            endTime: new Date(),
                          }
                        : tc
                    ),
                    statusText: undefined,
                  }
                : msg
            )
          );
        } else if (chunk.type === 'memory_update') {
          setMemory(chunk.memory);
        } else if (chunk.type === 'done') {
          setIsStreaming(false);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id
                ? { ...msg, statusText: undefined }
                : msg
            )
          );
        } else if (chunk.type === 'error') {
          setIsStreaming(false);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id
                ? { ...msg, content: msg.content + '\n\n⚠️ Error: ' + chunk.content, statusText: undefined }
                : msg
            )
          );
        }
      });
    } catch (error) {
      console.error('Failed to send message:', error);
      if (error instanceof AuthError) {
        clearToken();
        setAuthed(false);
        setUser(null);
        setIsStreaming(false);
        return;
      }
      setIsStreaming(false);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessage.id
            ? { ...msg, statusText: undefined }
            : msg
        )
      );
    }
  };

  const handleLogout = () => {
    clearToken();
    setAuthed(false);
    setUser(null);
    setMessages([]);
    setSessionId(null);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!authReady) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-50">
        <p className="text-sm text-gray-400">Loading...</p>
      </div>
    );
  }

  if (authRequired && !authed) {
    return (
      <LoginForm
        onLoggedIn={() => {
          setAuthed(true);
          setUser(getUsername());
        }}
      />
    );
  }

  return (
    <div className="flex h-screen bg-surface-50">
      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-surface-100 border-b border-surface-300 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <img src="/logo/seostrich-lockup-horizontal.svg" alt="SEOstrich" className="h-8 w-auto" />
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowRun(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg transition-colors bg-primary-400 text-white hover:bg-primary-500"
              >
                <Workflow className="w-4 h-4" />
                Pipeline
              </button>
              <button
                onClick={() => setShowSystem(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg transition-colors bg-surface-200 hover:bg-secondary-100 text-gray-700"
              >
                <Settings2 className="w-4 h-4" />
                System
              </button>
              <ProfileMenu
                username={username}
                authRequired={authRequired}
                onLogout={handleLogout}
              />
            </div>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-lg">
                <img
                  src="/logo/seostrich-lockup-vertical.svg"
                  alt="SEOstrich"
                  className="h-40 w-auto mx-auto mb-4"
                />
                <p className="text-gray-500">
                  An SEO agent that has memory, inspects its work and self-improves.
                </p>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto divide-y divide-gray-200">
              {messages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="bg-surface-50 border-t border-surface-300 p-4">
          <div className="max-w-3xl mx-auto">
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".md,.csv,.pdf,.doc,.docx,.txt"
              onChange={handleFileChange}
              className="hidden"
            />

            {/* Attachment chips */}
            {attachments.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {attachments.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center gap-2 px-3 py-1 bg-accent-100 rounded-full text-sm"
                  >
                    <span className="truncate max-w-[150px]">{file.name}</span>
                    <span className="text-gray-400 text-xs">
                      ({(file.size / 1024).toFixed(1)} KB)
                    </span>
                    <button
                      onClick={() => removeAttachment(index)}
                      className="text-gray-500 hover:text-gray-700"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="p-3 text-gray-500 hover:text-primary-500 hover:bg-primary-50 rounded-lg transition-colors"
                disabled={isStreaming || attachments.length >= 3}
                title="Attach files"
              >
                <Plus className="w-5 h-5" />
              </button>
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                placeholder="Ask about SEO strategy..."
                className={`flex-1 px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400 resize-none transition-colors bg-white ${
                  dragActive
                    ? 'border-primary-400 bg-primary-50'
                    : 'border-surface-300'
                }`}
                rows={2}
                disabled={isStreaming}
              />
              <button
                onClick={handleSend}
                disabled={isStreaming || (!input.trim() && attachments.length === 0)}
                className="px-6 py-3 bg-primary-400 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* System panel drawer (merged memory + admin) */}
      {showSystem && (
        <SystemPanel memory={memory} onClose={() => setShowSystem(false)} />
      )}

      {/* Pipeline / Run view */}
      {showRun && <RunView tasks={memory.tasks} onClose={() => setShowRun(false)} />}
    </div>
  );
}
