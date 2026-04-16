import type { EnrichmentResponse } from "@/api/types";
import { getStatusColor } from "@/lib/colors";

interface DossierViewProps {
  response: EnrichmentResponse;
}

export function DossierView({ response }: DossierViewProps) {
  const { dossier, llm_summary, modules } = response;

  const signalsByKind = new Map<string, NonNullable<typeof dossier>["signals"]>();
  if (dossier) {
    for (const sig of dossier.signals) {
      const key = sig.tag ? `${sig.kind}:${sig.tag}` : sig.kind;
      const group = signalsByKind.get(key) || [];
      group.push(sig);
      signalsByKind.set(key, group);
    }
  }

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
            <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">{llm_summary.summary}</p>
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

      {signalsByKind.size > 0 && (
        <div>
          <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Signals ({dossier?.signals.length})
          </h2>
          <div className="space-y-3">
            {[...signalsByKind.entries()].map(([kind, signals]) => (
              <div key={kind}>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-bg-overlay text-text-secondary font-mono uppercase">{kind}</span>
                  <span className="text-[10px] text-text-tertiary">{signals.length}</span>
                </div>
                <div className="space-y-1">
                  {signals.map((sig, i) => (
                    <div key={i} className="flex items-center gap-3 bg-bg-elevated/30 rounded px-3 py-1.5">
                      <span className="text-sm text-text-primary flex-1">{sig.value}</span>
                      <span className="text-[10px] text-text-tertiary">{(sig.confidence * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {dossier && dossier.facts.length > 0 && (
        <div>
          <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Facts ({dossier.facts.length})</h2>
          <div className="space-y-1.5">
            {dossier.facts.map((fact, i) => (
              <div key={i} className="bg-bg-elevated/30 rounded px-3 py-2">
                <p className="text-sm text-text-secondary">{fact.claim}</p>
                <span className="text-[10px] text-text-tertiary">{(fact.confidence * 100).toFixed(0)}%</span>
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

      <div>
        <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Module Results</h2>
        <div className="bg-bg-elevated/30 rounded-lg overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-text-tertiary border-b border-border-subtle">
                <th className="text-left px-3 py-2 font-medium">Module</th>
                <th className="text-left px-3 py-2 font-medium">Status</th>
                <th className="text-right px-3 py-2 font-medium">Time</th>
                <th className="text-right px-3 py-2 font-medium">Signals</th>
                <th className="text-right px-3 py-2 font-medium">Facts</th>
              </tr>
            </thead>
            <tbody>
              {modules.map((m) => {
                const colors = getStatusColor(m.status);
                return (
                  <tr key={m.name} className="border-b border-border-subtle/50">
                    <td className="px-3 py-1.5 text-text-primary font-mono">{m.name}</td>
                    <td className="px-3 py-1.5"><span className={colors.text}>{m.status}</span></td>
                    <td className="px-3 py-1.5 text-right text-text-tertiary">{m.duration_s.toFixed(2)}s</td>
                    <td className="px-3 py-1.5 text-right text-text-tertiary">{m.signals.length}</td>
                    <td className="px-3 py-1.5 text-right text-text-tertiary">{m.facts.length}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
