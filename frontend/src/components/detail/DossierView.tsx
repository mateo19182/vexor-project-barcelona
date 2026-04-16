import { useState } from "react";
import type { EnrichmentResponse, ContactChannel, IntelligenceItem } from "@/api/types";

interface DossierViewProps {
  response: EnrichmentResponse;
}

const confidenceColor: Record<string, string> = {
  high: "text-white",
  moderate: "text-zinc-300",
  low: "text-zinc-500",
};

const confidenceLabel: Record<string, string> = {
  high: "High confidence",
  moderate: "Moderate confidence",
  low: "Low confidence",
};

const footprintLabel: Record<string, string> = {
  extensive: "Extensive",
  moderate: "Moderate",
  minimal: "Minimal",
};

const categoryIcons: Record<string, string> = {
  identity: "ID",
  location: "LOC",
  employment: "EMP",
  lifestyle: "LIFE",
  financial: "FIN",
  digital: "DIG",
  risk: "RISK",
};

function ChannelRow({ ch }: { ch: ContactChannel }) {
  return (
    <div className="flex items-center gap-3 bg-bg-elevated/30 rounded-lg px-3 py-2">
      <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-bg-overlay text-text-secondary w-16 text-center shrink-0">
        {ch.channel}
      </span>
      <span className="text-sm text-text-primary font-mono flex-1 truncate">{ch.value}</span>
      {ch.verified_on.length > 0 && (
        <div className="flex items-center gap-1 shrink-0">
          {ch.verified_on.map((p) => (
            <span key={p} className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/10 text-text-secondary">
              {p}
            </span>
          ))}
        </div>
      )}
      <span className="text-[10px] text-text-tertiary shrink-0">{(ch.confidence * 100).toFixed(0)}%</span>
    </div>
  );
}

function IntelCard({ item }: { item: IntelligenceItem }) {
  const icon = categoryIcons[item.category] || "?";
  return (
    <div className={`bg-bg-elevated/30 rounded-lg px-3 py-2 ${item.actionable ? "border border-white/10" : ""}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-bg-overlay text-text-secondary">
          {icon}
        </span>
        <span className="text-[10px] text-text-tertiary">{(item.confidence * 100).toFixed(0)}%</span>
        {item.actionable && (
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/10 text-white ml-auto">actionable</span>
        )}
      </div>
      <p className="text-sm text-text-secondary leading-relaxed">{item.finding}</p>
      <p className="text-[10px] text-text-tertiary mt-1 truncate">{item.source}</p>
    </div>
  );
}

export function DossierView({ response }: DossierViewProps) {
  const { enriched_dossier: ed, llm_summary, modules } = response;
  const [showTechIssues, setShowTechIssues] = useState(false);

  const okCount = modules.filter((m) => m.status === "ok").length;
  const errorCount = modules.filter((m) => m.status === "error").length;
  const totalModules = modules.length;

  // Fallback: if enriched_dossier is not present, show legacy view
  if (!ed) {
    return <LegacyDossierView response={response} />;
  }

  const subject = ed.subject;
  const conf = llm_summary?.confidence_level || "low";

  // Group intelligence by category
  const intelByCategory = new Map<string, IntelligenceItem[]>();
  for (const item of ed.intelligence) {
    const group = intelByCategory.get(item.category) || [];
    group.push(item);
    intelByCategory.set(item.category, group);
  }

  return (
    <div className="p-6 h-full overflow-y-auto space-y-6">
      {/* ── Subject header ── */}
      <div className="bg-bg-elevated/50 border border-border-subtle rounded-xl p-5">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-text-primary tracking-tight">
              {subject.name || "Unknown subject"}
            </h2>
            {subject.aliases.length > 0 && (
              <p className="text-xs text-text-tertiary mt-0.5">
                aka {subject.aliases.join(", ")}
              </p>
            )}
            <div className="flex items-center gap-3 mt-2">
              {subject.location && (
                <span className="text-sm text-text-secondary">{subject.location}</span>
              )}
              {subject.country && !subject.location?.includes(subject.country) && (
                <span className="text-xs text-text-tertiary">{subject.country}</span>
              )}
            </div>
          </div>
          <div className="text-right space-y-1">
            <div className={`text-xs font-medium ${confidenceColor[conf]}`}>
              {confidenceLabel[conf]}
            </div>
            <div className="text-[10px] text-text-tertiary">
              Footprint: {footprintLabel[ed.digital_footprint] || ed.digital_footprint}
            </div>
            <div className="text-[10px] text-text-tertiary">
              {okCount}/{totalModules} modules OK
            </div>
          </div>
        </div>

        {/* Case summary */}
        <p className="text-xs text-text-tertiary mt-3 border-t border-border-subtle pt-3">
          {ed.case_summary}
        </p>
      </div>

      {/* ── Contact channels ── */}
      {ed.contact_channels.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Contact channels ({ed.contact_channels.length})
          </h3>
          <div className="space-y-1.5">
            {ed.contact_channels.map((ch, i) => (
              <ChannelRow key={i} ch={ch} />
            ))}
          </div>
        </div>
      )}

      {/* ── Executive brief ── */}
      {llm_summary && (
        <div>
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Executive brief
          </h3>
          <div className="bg-bg-elevated/50 border border-border-subtle rounded-lg p-4">
            <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
              {llm_summary.executive_brief}
            </p>
            {llm_summary.approach_context && (
              <div className="mt-3 pt-3 border-t border-border-subtle">
                <span className="text-[10px] font-semibold text-text-tertiary uppercase">Context</span>
                <p className="text-sm text-text-secondary leading-relaxed mt-1">
                  {llm_summary.approach_context}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Key facts + unanswered questions side by side ── */}
      {llm_summary && (llm_summary.key_facts.length > 0 || llm_summary.unanswered_questions.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          {llm_summary.key_facts.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                Key facts
              </h3>
              <ul className="space-y-1">
                {llm_summary.key_facts.map((fact, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                    <span className="text-text-tertiary mt-0.5 shrink-0">&#8226;</span>
                    {fact}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {llm_summary.unanswered_questions.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                Unanswered
              </h3>
              <ul className="space-y-1">
                {llm_summary.unanswered_questions.map((q, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-text-tertiary">
                    <span className="mt-0.5 shrink-0">?</span>
                    {q}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ── Risk flags ── */}
      {ed.risk_flags.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Risk flags ({ed.risk_flags.length})
          </h3>
          <div className="space-y-1.5">
            {ed.risk_flags.map((flag, i) => (
              <div key={i} className="flex items-center gap-2 bg-zinc-500/5 border border-zinc-500/10 rounded px-3 py-2">
                <span className="text-zinc-400 text-xs shrink-0">!</span>
                <span className="text-sm text-text-secondary">{flag}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Intelligence ── */}
      {ed.intelligence.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Intelligence ({ed.intelligence.length})
          </h3>
          <div className="space-y-4">
            {[...intelByCategory.entries()].map(([category, items]) => (
              <div key={category}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] font-semibold text-text-tertiary uppercase">{category}</span>
                  <span className="text-[10px] text-text-tertiary">{items.length}</span>
                </div>
                <div className="space-y-1.5">
                  {items.map((item, i) => (
                    <IntelCard key={i} item={item} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Platform registrations ── */}
      {ed.platform_registrations.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Platform registrations
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {ed.platform_registrations.map((p) => (
              <span key={p} className="text-xs px-2 py-1 rounded-full bg-white/5 text-text-secondary border border-white/10">
                {p}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Gaps ── */}
      {ed.gaps.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Intelligence gaps ({ed.gaps.length})
          </h3>
          <ul className="space-y-1">
            {ed.gaps.map((gap, i) => (
              <li key={i} className="text-xs text-text-tertiary bg-bg-elevated/30 rounded px-3 py-2">{gap}</li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Module coverage ── */}
      <div>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
          Module coverage
        </h3>
        <div className="grid grid-cols-4 gap-1.5">
          {Object.entries(ed.module_coverage).map(([name, status]) => (
            <div key={name} className="flex items-center gap-2 bg-bg-elevated/30 rounded px-2 py-1.5">
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                status === "ok" ? "bg-white" :
                status === "error" ? "bg-zinc-400" :
                status === "no_data" ? "bg-zinc-500" :
                "bg-zinc-600"
              }`} />
              <span className="text-[10px] text-text-secondary font-mono truncate">{name}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Technical issues (collapsible) ── */}
      {ed.technical_issues.length > 0 && (
        <div>
          <button
            onClick={() => setShowTechIssues(!showTechIssues)}
            className="text-[10px] text-text-tertiary hover:text-text-secondary transition-colors"
          >
            {showTechIssues ? "Hide" : "Show"} technical issues ({ed.technical_issues.length})
          </button>
          {showTechIssues && (
            <ul className="mt-2 space-y-1">
              {ed.technical_issues.map((issue, i) => (
                <li key={i} className="text-[10px] text-text-tertiary bg-bg-elevated/20 rounded px-2 py-1.5 font-mono">{issue}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Fallback for responses that don't have enriched_dossier yet
 * (e.g. loading old cached results).
 */
function LegacyDossierView({ response }: DossierViewProps) {
  const { dossier, llm_summary, modules } = response;

  const okCount = modules.filter((m) => m.status === "ok").length;
  const errorCount = modules.filter((m) => m.status === "error").length;
  const skippedCount = modules.filter((m) => m.status === "skipped").length;

  return (
    <div className="p-6 h-full overflow-y-auto space-y-6">
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-center">
          <div className="text-2xl font-bold text-text-primary">{okCount}</div>
          <div className="text-xs text-text-tertiary">Completed</div>
        </div>
        <div className="bg-zinc-500/10 border border-zinc-500/20 rounded-lg px-4 py-3 text-center">
          <div className="text-2xl font-bold text-zinc-400">{errorCount}</div>
          <div className="text-xs text-text-tertiary">Errors</div>
        </div>
        <div className="bg-zinc-700/10 border border-zinc-700/20 rounded-lg px-4 py-3 text-center">
          <div className="text-2xl font-bold text-zinc-500">{skippedCount}</div>
          <div className="text-xs text-text-tertiary">Skipped</div>
        </div>
      </div>

      {llm_summary && (
        <div>
          <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">AI Summary</h2>
          <div className="bg-bg-elevated/50 border border-border-subtle rounded-lg p-4">
            <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">{llm_summary.executive_brief}</p>
            {llm_summary.key_facts.length > 0 && (
              <ul className="mt-3 space-y-1">
                {llm_summary.key_facts.map((fact, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                    <span className="text-text-primary mt-0.5 shrink-0">&#8226;</span>
                    {fact}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {dossier && dossier.signals.length > 0 && (
        <div>
          <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Signals ({dossier.signals.length})
          </h2>
          <div className="space-y-1">
            {dossier.signals.map((sig, i) => (
              <div key={i} className="flex items-center gap-3 bg-bg-elevated/30 rounded px-3 py-1.5">
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-overlay text-text-secondary font-mono">
                  {sig.tag ? `${sig.kind}:${sig.tag}` : sig.kind}
                </span>
                <span className="text-sm text-text-primary flex-1">{sig.value}</span>
                <span className="text-[10px] text-text-tertiary">{(sig.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {dossier && dossier.gaps.length > 0 && (
        <div>
          <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Gaps ({dossier.gaps.length})</h2>
          <ul className="space-y-1">
            {dossier.gaps.map((gap, i) => (
              <li key={i} className="text-xs text-text-secondary bg-bg-elevated/30 rounded px-3 py-2">{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
