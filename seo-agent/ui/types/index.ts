export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
  attachments?: FileAttachment[];
  statusText?: string;
  stages?: StageCard[];
}

export interface StageCard {
  run_id: string;
  stage_id: string;
  label: string;
}

export interface ToolCall {
  id: string;
  tool: string;
  args: Record<string, any>;
  result?: any;
  status: 'running' | 'success' | 'error';
  startTime: Date;
  endTime?: Date;
}

export interface FileAttachment {
  id: string;
  name: string;
  type: string;
  size: number;
  content?: string;
}

export interface MemoryState {
  facts: string[];
  learnings: string[];
  decisions: string[];
  tasks: string[];
}

export interface Session {
  id: string;
  messages: Message[];
  memory: MemoryState;
  createdAt: Date;
}

// --- Pipeline runs ---------------------------------------------------------

export interface RunSummary {
  id: string;
  project?: string;
  title?: string;
  created?: string;
  status?: string;
  stages: number;
  modified?: number;
}

export interface RunStage {
  id: string;
  label: string;
  status: string;
  artifact: Record<string, any>;
}

export interface RunFeedback {
  text: string;
  author?: string;
  at?: string;
}

export interface Run {
  id: string;
  project?: string;
  title?: string;
  created?: string;
  status?: string;
  stages: RunStage[];
  feedback?: RunFeedback[];
}
