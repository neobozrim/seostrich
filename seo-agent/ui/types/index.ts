export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
  attachments?: FileAttachment[];
  statusText?: string;
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
