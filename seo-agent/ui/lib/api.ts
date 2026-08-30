const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

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
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

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
  const response = await fetch(`${API_BASE}/api/memory`);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function getSessions(): Promise<any[]> {
  const response = await fetch(`${API_BASE}/api/sessions`);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}
