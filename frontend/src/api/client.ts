import type { CaseEntry, EnrichmentResponse, ModuleInfo } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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

export async function fetchRun(caseId: string, filename: string): Promise<EnrichmentResponse> {
  const res = await fetch(`${BASE}/cases/${caseId}/runs/${filename}`);
  if (!res.ok) throw new Error(`Failed to fetch run: ${res.statusText}`);
  return res.json();
}
