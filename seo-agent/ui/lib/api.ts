const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const TOKEN_KEY = 'omni_auth_token';

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
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function ensureOk(response: Response): Promise<void> {
  if (response.status === 401) throw new AuthError();
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
}

export async function checkAuth(): Promise<{ auth_required: boolean; authenticated: boolean }> {
  const response = await fetch(`${API_BASE}/api/auth/check`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
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
}

export async function sendMessage(
  message: string,
  attachments?: File[],
  sessionId?: string | null,
  onChunk?: (chunk: any) => void
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

export async function getSessions(): Promise<any[]> {
  const response = await fetch(`${API_BASE}/api/sessions`, {
    headers: authHeaders(),
  });
  await ensureOk(response);
  return response.json();
}
