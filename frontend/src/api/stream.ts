import type { AuditEvent, EnrichmentResponse } from "./types";

const BASE = "http://localhost:8000";

export interface StreamCallbacks {
  onEvent: (event: AuditEvent) => void;
  onResult: (response: EnrichmentResponse) => void;
  onError: (error: string) => void;
}

export async function streamEnrich(
  casePayload: Record<string, unknown>,
  callbacks: StreamCallbacks
): Promise<void> {
  const res = await fetch(`${BASE}/enrich/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(casePayload),
  });

  if (!res.ok) {
    callbacks.onError(`Stream failed: ${res.statusText}`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError("No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE lines
    const lines = buffer.split("\n\n");
    buffer = lines.pop() || "";

    for (const chunk of lines) {
      const dataLine = chunk
        .split("\n")
        .find((l) => l.startsWith("data: "));
      if (!dataLine) continue;

      const json = dataLine.slice(6); // strip "data: "
      try {
        const parsed = JSON.parse(json);
        if (parsed.kind === "result") {
          callbacks.onResult(parsed.data);
        } else if (parsed.kind === "error") {
          callbacks.onError(parsed.message);
        } else {
          // It's an AuditEvent
          callbacks.onEvent(parsed as AuditEvent);
        }
      } catch {
        // Ignore malformed lines
      }
    }
  }
}
