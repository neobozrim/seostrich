'use client';

import React, { useState, useEffect } from 'react';
import { FileText, Lightbulb, Target, ListTodo, BookOpen, Package, TrendingUp } from 'lucide-react';

interface AdminPanelProps {
  apiBaseUrl: string;
}

export function AdminPanel({ apiBaseUrl }: AdminPanelProps) {
  const [activeTab, setActiveTab] = useState('facts');
  const [files, setFiles] = useState<Record<string, string>>({});
  const [improvements, setImprovements] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const tabs = [
    { id: 'facts', label: 'Facts', icon: FileText },
    { id: 'learnings', label: 'Learnings', icon: Lightbulb },
    { id: 'decisions', label: 'Decisions', icon: Target },
    { id: 'tasks', label: 'Tasks', icon: ListTodo },
    { id: 'runs-summaries', label: 'Run Summaries', icon: BookOpen },
    { id: 'artefacts-index', label: 'Artefacts', icon: Package },
    { id: 'improvements', label: 'Improvements', icon: TrendingUp },
  ];

  const fetchFile = async (filename: string) => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/memory/file/${filename}`);
      if (response.ok) {
        const content = await response.text();
        setFiles(prev => ({ ...prev, [filename]: content }));
      }
    } catch (error) {
      console.error(`Failed to fetch ${filename}:`, error);
    }
  };

  const fetchImprovements = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${apiBaseUrl}/api/memory/improvements`);
      if (response.ok) {
        const data = await response.json();
        setImprovements(data);
      }
    } catch (error) {
      console.error('Failed to fetch improvements:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab !== 'improvements') {
      fetchFile(`${activeTab}.md`);
    } else {
      fetchImprovements();
    }
  }, [activeTab, apiBaseUrl]);

  const renderContent = () => {
    if (activeTab === 'improvements') {
      if (loading) {
        return <div className="p-4 text-gray-500">Loading improvements...</div>;
      }
      if (improvements.length === 0) {
        return <div className="p-4 text-gray-500">No improvement proposals yet.</div>;
      }
      return (
        <div className="p-4 space-y-4">
          {improvements.map((imp, idx) => (
            <div key={idx} className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-semibold text-gray-900">{imp.topic}</h3>
                <span className={`px-2 py-1 text-xs rounded ${
                  imp.status === 'approved' ? 'bg-green-100 text-green-700' :
                  imp.status === 'rejected' ? 'bg-red-100 text-red-700' :
                  'bg-yellow-100 text-yellow-700'
                }`}>
                  {imp.status || 'pending'}
                </span>
              </div>
              <p className="text-sm text-gray-600 mb-2">{imp.rationale}</p>
              <div className="text-xs text-gray-500">
                <span className="font-medium">Category:</span> {imp.category}
              </div>
              {imp.timestamp && (
                <div className="text-xs text-gray-500 mt-1">
                  {new Date(imp.timestamp).toLocaleString()}
                </div>
              )}
            </div>
          ))}
        </div>
      );
    }

    const content = files[`${activeTab}.md`];
    if (!content) {
      return <div className="p-4 text-gray-500">Loading...</div>;
    }

    return (
      <div className="p-4">
        <pre className="whitespace-pre-wrap font-mono text-sm text-gray-800 bg-gray-50 p-4 rounded-lg overflow-auto max-h-[calc(100vh-200px)]">
          {content}
        </pre>
      </div>
    );
  };

  return (
    <div className="w-full h-full flex flex-row bg-white">
      {/* Sidebar */}
      <div className="w-80 min-w-80 border-r border-surface-300 bg-surface-50 overflow-y-auto flex-shrink-0">
        <div className="p-4 border-b border-surface-300">
          <h2 className="text-lg font-semibold text-primary-700">Admin Panel</h2>
          <p className="text-xs text-gray-500 mt-1">Memory & System Files</p>
        </div>
        <nav className="p-2">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg mb-1 transition-colors ${
                activeTab === id
                  ? 'bg-primary-400 text-white'
                  : 'text-gray-700 hover:bg-surface-200'
              }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="text-sm font-medium">{label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-6 border-b border-surface-300 bg-white sticky top-0 z-10">
          <h2 className="text-xl font-semibold text-gray-900 capitalize">
            {activeTab.replace('-', ' ')}
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            {activeTab === 'improvements'
              ? 'Self-learning improvement proposals'
              : `Content of ${activeTab}.md memory file`
            }
          </p>
        </div>
        {renderContent()}
      </div>
    </div>
  );
}
