import type { AuditEvent, EnrichmentResponse } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface StreamCallbacks {
  onEvent: (event: AuditEvent) => void;
  onResult: (response: EnrichmentResponse) => void;
  onError: (error: string) => void;
}

export async function streamEnrich(
  casePayload: unknown,
  callbacks: StreamCallbacks,
  only?: string[],
): Promise<void> {
  const params = new URLSearchParams();
  params.set("fresh", "true");
  if (only) {
    for (const m of only) params.append("only", m);
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}/enrich/stream?${params}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(casePayload),
    });
  } catch (err) {
    callbacks.onError(`Network error: ${err}`);
    return;
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    callbacks.onError(`Stream failed: ${res.status} ${res.statusText} — ${body}`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError("No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by double newlines
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";

      for (const chunk of parts) {
        if (!chunk.trim()) continue;
        const dataLine = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!dataLine) continue;

        const json = dataLine.slice(6);
        try {
          const parsed = JSON.parse(json);
          if (parsed.kind === "result") {
            callbacks.onResult(parsed.data);
          } else if (parsed.kind === "error") {
            callbacks.onError(parsed.message);
          } else {
            callbacks.onEvent(parsed as AuditEvent);
          }
        } catch {
          // Ignore malformed SSE lines
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
