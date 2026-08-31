const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const TOKEN_KEY = 'omni_auth_token';
const USER_KEY = 'omni_auth_user';

export class AuthError extends Error {
  constructor() {
    super('Not authenticated');
  }
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getUsername(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(USER_KEY);
}

export function setUsername(name: string): void {
  localStorage.setItem(USER_KEY, name);
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function ensureOk(response: Response): Promise<void> {
  if (response.status === 401) throw new AuthError();
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
}

export async function checkAuth(): Promise<{
  auth_required: boolean;
  authenticated: boolean;
  username?: string | null;
}> {
  const response = await fetch(`${API_BASE}/api/auth/check`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  const data = await response.json();
  if (data.username) setUsername(data.username);
  return data;
}

export async function login(username: string, password: string): Promise<void> {
  const formData = new FormData();
  formData.append('username', username);
  formData.append('password', password);

  const response = await fetch(`${API_BASE}/api/login`, {
    method: 'POST',
    body: formData,
  });

  if (response.status === 401) {
    throw new Error('Invalid username or password');
  }
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = await response.json();
  setToken(data.token);
  if (data.username) setUsername(data.username);
}

export async function sendMessage(
  message: string,
  attachments?: File[],
  sessionId?: string | null,
  onChunk?: (chunk: any) => void,
  signal?: AbortSignal
): Promise<void> {
  const formData = new FormData();
  formData.append('message', message);
  if (sessionId) {
    formData.append('session_id', sessionId);
  }

  if (attachments) {
    attachments.forEach((file, index) => {
      formData.append(`file_${index}`, file);
    });
  }

  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
    signal,
  });

  await ensureOk(response);

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          onChunk?.(data);
        } catch (e) {
          console.error('Failed to parse chunk:', e);
        }
      }
    }
  }
}

export async function getMemory(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/memory`, {
    headers: authHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

export async function stopSession(sessionId: string): Promise<{ ok: boolean }> {
  const response = await fetch(`${API_BASE}/api/chat/stop`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  await ensureOk(response);
  return response.json();
}

export async function getSessions(): Promise<any[]> {
  const response = await fetch(`${API_BASE}/api/sessions`, {
    headers: authHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

// --- Pipeline runs ---------------------------------------------------------

export async function getRuns(): Promise<any[]> {
  const response = await fetch(`${API_BASE}/api/runs`, {
    headers: authHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

export async function getRun(runId: string): Promise<any> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}`, {
    headers: authHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

export async function addRunFeedback(
  runId: string,
  text: string,
  author?: string
): Promise<any> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/feedback`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, author: author || 'judge' }),
  });
  await ensureOk(response);
  return response.json();
}

export async function restoreDefaultRuns(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/runs/restore-defaults`, {
    method: 'POST',
    headers: authHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

// --- Cluster governance + stage inspection ---------------------------------

export async function getRunClusters(runId: string, signal?: AbortSignal): Promise<any> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/clusters`, {
    headers: authHeaders(),
    signal,
  });
  await ensureOk(response);
  return response.json();
}

export async function getRunStage(
  runId: string,
  stageId: string,
  signal?: AbortSignal
): Promise<any> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/stages/${stageId}`, {
    headers: authHeaders(),
    signal,
  });
  await ensureOk(response);
  return response.json();
}

export async function promoteRunCluster(
  runId: string,
  clusterName: string,
  signal?: AbortSignal
): Promise<any> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/clusters/promote`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ cluster_name: clusterName }),
    signal,
  });
  await ensureOk(response);
  return response.json();
}

export async function discardRunCluster(
  runId: string,
  clusterName: string,
  reason?: string,
  signal?: AbortSignal
): Promise<any> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/clusters/discard`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ cluster_name: clusterName, reason: reason || '' }),
    signal,
  });
  await ensureOk(response);
  return response.json();
}

export async function proposeRunCluster(
  runId: string,
  topic: string,
  signal?: AbortSignal
): Promise<any> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/clusters/propose`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic }),
    signal,
  });
  await ensureOk(response);
  return response.json();
}

// --- Memory files (for the consolidated System panel) ----------------------

export async function getMemoryFile(filename: string): Promise<string> {
  const response = await fetch(`${API_BASE}/api/memory/file/${filename}`, {
    headers: authHeaders(),
  });
  await ensureOk(response);
  return response.text();
}

export async function getImprovements(): Promise<any[]> {
  const response = await fetch(`${API_BASE}/api/memory/improvements`, {
    headers: authHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

export async function getArtifacts(): Promise<any[]> {
  const response = await fetch(`${API_BASE}/api/artifacts`, {
    headers: authHeaders(),
  });
  await ensureOk(response);
  return response.json();
}
