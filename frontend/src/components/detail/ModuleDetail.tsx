import type { ModuleResult } from "@/api/types";
import { getStatusColor, statusDotColors } from "@/lib/colors";

interface ModuleDetailProps {
  module: ModuleResult;
  onClose: () => void;
}

export function ModuleDetail({ module, onClose }: ModuleDetailProps) {
  const colors = getStatusColor(module.status);

  return (
    <div className="w-96 bg-bg-surface/90 backdrop-blur-xl border-l border-border-subtle overflow-y-auto h-full">
      <div className="sticky top-0 bg-bg-surface/95 backdrop-blur border-b border-border-subtle p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${statusDotColors[module.status]}`} />
          <h2 className="text-sm font-bold text-text-primary">{module.name}</h2>
        </div>
        <button onClick={onClose} className="text-text-tertiary hover:text-text-primary text-lg">&times;</button>
      </div>

      <div className="p-4 space-y-4">
        <div className={`flex items-center gap-3 px-3 py-2 rounded-lg ${colors.bg} ${colors.border} border`}>
          <span className={`text-sm font-medium ${colors.text}`}>{module.status}</span>
          {module.duration_s > 0 && <span className="text-xs text-text-tertiary">{module.duration_s.toFixed(2)}s</span>}
        </div>

        {module.summary && (
          <div>
            <h3 className="text-xs font-semibold text-text-tertiary uppercase mb-1">Summary</h3>
            <p className="text-sm text-text-secondary leading-relaxed">{module.summary}</p>
          </div>
        )}

        {module.signals.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-text-tertiary uppercase mb-2">Signals ({module.signals.length})</h3>
            <div className="space-y-1.5">
              {module.signals.map((sig, i) => (
                <div key={i} className="bg-bg-elevated/50 rounded-lg px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-overlay text-text-secondary font-mono">
                      {sig.tag ? `${sig.kind}:${sig.tag}` : sig.kind}
                    </span>
                    <span className="text-xs text-text-tertiary">{(sig.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <p className="text-sm text-text-primary mt-1">{sig.value}</p>
                  {sig.notes && <p className="text-xs text-text-tertiary mt-0.5">{sig.notes}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {module.facts.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-text-tertiary uppercase mb-2">Facts ({module.facts.length})</h3>
            <div className="space-y-1.5">
              {module.facts.map((fact, i) => (
                <div key={i} className="bg-bg-elevated/50 rounded-lg px-3 py-2">
                  <p className="text-sm text-text-secondary">{fact.claim}</p>
                  <span className="text-xs text-text-tertiary">{(fact.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {module.gaps.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-text-tertiary uppercase mb-2">Gaps ({module.gaps.length})</h3>
            <ul className="space-y-1">
              {module.gaps.map((gap, i) => (
                <li key={i} className="text-xs text-text-secondary bg-bg-elevated/50 rounded px-2 py-1.5">{gap}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
