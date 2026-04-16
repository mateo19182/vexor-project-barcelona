export type SignalKind =
  | "name" | "address" | "location" | "employer" | "role"
  | "business" | "asset" | "lifestyle" | "contact"
  | "affiliation" | "risk_flag";

export interface Signal {
  kind: SignalKind;
  value: string;
  source: string;
  confidence: number;
  notes: string | null;
  tag: string | null;
}

export interface Fact {
  claim: string;
  source: string;
  confidence: number;
}

export interface SocialLink {
  platform: string;
  url: string;
  handle: string | null;
  confidence: number;
}

export interface ModuleResult {
  name: string;
  status: "ok" | "error" | "skipped" | "no_data";
  summary: string;
  social_links: SocialLink[];
  facts: Fact[];
  signals: Signal[];
  gaps: string[];
  raw: Record<string, unknown>;
  duration_s: number;
}

export type EventKind =
  | "pipeline_started" | "pipeline_completed"
  | "wave_started" | "module_completed" | "module_cache_hit"
  | string;

export interface AuditEvent {
  kind: EventKind;
  elapsed_s: number;
  module: string | null;
  wave: number | null;
  message: string;
  detail: Record<string, unknown>;
}

export interface Dossier {
  summary: string;
  facts: Fact[];
  signals: Signal[];
  gaps: string[];
}

export interface LlmSummary {
  executive_brief: string;
  approach_context: string;
  confidence_level: "high" | "moderate" | "low";
  key_facts: string[];
  unanswered_questions: string[];
}

export interface SubjectProfile {
  name: string;
  aliases: string[];
  location: string | null;
  country: string | null;
  phones: string[];
  emails: string[];
  social_handles: Record<string, string>;
}

export interface ContactChannel {
  channel: string;
  value: string;
  verified_on: string[];
  confidence: number;
  notes: string | null;
}

export interface IntelligenceItem {
  category: string;
  finding: string;
  source: string;
  confidence: number;
  actionable: boolean;
}

export interface EnrichedDossier {
  subject: SubjectProfile;
  case_summary: string;
  digital_footprint: "minimal" | "moderate" | "extensive";
  contact_channels: ContactChannel[];
  intelligence: IntelligenceItem[];
  risk_flags: string[];
  platform_registrations: string[];
  gaps: string[];
  technical_issues: string[];
  module_coverage: Record<string, string>;
}

export interface EnrichmentResponse {
  case_id: string;
  status: string;
  dossier: Dossier | null;
  enriched_dossier: EnrichedDossier | null;
  llm_summary: LlmSummary | null;
  modules: ModuleResult[];
  audit_log: AuditEvent[];
}

export interface ModuleInfo {
  name: string;
  requires: string[];
}

export interface CaseRun {
  timestamp: string;
  file: string;
}

export interface CaseEntry {
  case_id: string;
  runs: CaseRun[];
}
