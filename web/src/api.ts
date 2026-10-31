// Client for the FastAPI app. In dev, Vite forwards /api/* to uvicorn (see vite.config.ts).

export const API = "/api";

export type Role = "user" | "assistant";

export interface ChatMessage {
  role: Role;
  content: string;
}

export interface ProfileSummary {
  profile_id: string;
  score: number;
  as_of: string;
  n_accounts: number;
  story: string | null;
}

export interface GuardrailFlag {
  stage: string; // input | tool_result | output | final
  name: string; // pii | injection | compliance
  action: string; // redact | block | rewrite | retract
  reasons: string[];
}

// One event from the /chat SSE stream (see src/assistant/api.py).
export type ChatEvent =
  | { type: "text"; text: string }
  | { type: "tool_call"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; is_error: boolean }
  | { type: "retract"; reason: string[]; replacement: string }
  | { type: "done"; stop: string }
  | {
      type: "transcript";
      transcript_id: string;
      conversation_id: string;
      cost_usd: number;
      model: string;
      prompt_version: string;
      latency_ms: number;
      guardrails: GuardrailFlag[];
    }
  | { type: "error"; message: string };

export async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(API + path);
  if (!resp.ok) throw new Error(`${path}: HTTP ${resp.status}`);
  return (await resp.json()) as T;
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`${path}: HTTP ${resp.status} ${await resp.text()}`);
  return (await resp.json()) as T;
}

// Parse one SSE frame ("event: x\ndata: {...}") into a ChatEvent.
export function parseFrame(frame: string): ChatEvent | null {
  let type = "";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) type = line.slice(7);
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!type || !data) return null;
  return { type, ...JSON.parse(data) } as ChatEvent;
}

// POST /chat and call onEvent for each SSE frame as it arrives. EventSource only does GET,
// so the stream is read with fetch and split on the blank line that ends each frame.
export async function streamChat(
  body: { profile_id: string; conversation_id: string | null; messages: ChatMessage[] },
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const resp = await fetch(API + "/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    onEvent({ type: "error", message: `HTTP ${resp.status}` });
    return;
  }
  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const event = parseFrame(buffer.slice(0, end));
      buffer = buffer.slice(end + 2);
      if (event) onEvent(event);
    }
  }
}
