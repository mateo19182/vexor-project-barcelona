import type { CaseEntry, EnrichmentResponse, ModuleInfo } from "./types";

const BASE = "http://localhost:8000";

export async function fetchModules(): Promise<ModuleInfo[]> {
  const res = await fetch(`${BASE}/modules`);
  const data = await res.json();
  return data.modules;
}

export async function fetchCases(): Promise<CaseEntry[]> {
  const res = await fetch(`${BASE}/cases`);
  const data = await res.json();
  return data.cases;
}

export async function fetchRun(
  caseId: string,
  filename: string
): Promise<EnrichmentResponse> {
  const res = await fetch(`${BASE}/cases/${caseId}/runs/${filename}`);
  if (!res.ok) throw new Error(`Failed to fetch run: ${res.statusText}`);
  return res.json();
}

export async function enrichCase(
  casePayload: Record<string, unknown>
): Promise<EnrichmentResponse> {
  const res = await fetch(`${BASE}/enrich`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(casePayload),
  });
  if (!res.ok) throw new Error(`Enrichment failed: ${res.statusText}`);
  return res.json();
}
