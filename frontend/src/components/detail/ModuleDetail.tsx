import type { ModuleResult } from "../../api/types";
import { getStatusColor, statusDotColors } from "../../lib/colors";

interface ModuleDetailProps {
  module: ModuleResult;
  onClose: () => void;
}

export function ModuleDetail({ module, onClose }: ModuleDetailProps) {
  const colors = getStatusColor(module.status);

  return (
    <div className="w-96 bg-zinc-900 border-l border-zinc-800 overflow-y-auto h-full">
      <div className="sticky top-0 bg-zinc-900/95 backdrop-blur border-b border-zinc-800 p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${statusDotColors[module.status]}`} />
          <h2 className="text-sm font-bold text-zinc-100">{module.name}</h2>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-500 hover:text-zinc-300 text-lg"
        >
          &times;
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Status bar */}
        <div className={`flex items-center gap-3 px-3 py-2 rounded-lg ${colors.bg} ${colors.border} border`}>
          <span className={`text-sm font-medium ${colors.text}`}>{module.status}</span>
          {module.duration_s > 0 && (
            <span className="text-xs text-zinc-400">{module.duration_s.toFixed(2)}s</span>
          )}
        </div>

        {/* Summary */}
        {module.summary && (
          <div>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase mb-1">Summary</h3>
            <p className="text-sm text-zinc-300 leading-relaxed">{module.summary}</p>
          </div>
        )}

        {/* Signals */}
        {module.signals.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase mb-2">
              Signals ({module.signals.length})
            </h3>
            <div className="space-y-1.5">
              {module.signals.map((sig, i) => (
                <div key={i} className="bg-zinc-800/50 rounded-lg px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300 font-mono">
                      {sig.tag ? `${sig.kind}:${sig.tag}` : sig.kind}
                    </span>
                    <span className="text-xs text-zinc-500">
                      {(sig.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-sm text-zinc-200 mt-1">{sig.value}</p>
                  {sig.notes && (
                    <p className="text-xs text-zinc-500 mt-0.5">{sig.notes}</p>
                  )}
                  <a
                    href={sig.source}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-blue-400/70 hover:text-blue-400 truncate block mt-0.5"
                  >
                    {sig.source}
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Facts */}
        {module.facts.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase mb-2">
              Facts ({module.facts.length})
            </h3>
            <div className="space-y-1.5">
              {module.facts.map((fact, i) => (
                <div key={i} className="bg-zinc-800/50 rounded-lg px-3 py-2">
                  <p className="text-sm text-zinc-300">{fact.claim}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-zinc-500">
                      {(fact.confidence * 100).toFixed(0)}%
                    </span>
                    <a
                      href={fact.source}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[10px] text-blue-400/70 hover:text-blue-400 truncate"
                    >
                      {fact.source}
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Social Links */}
        {module.social_links.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase mb-2">
              Social Links ({module.social_links.length})
            </h3>
            <div className="space-y-1">
              {module.social_links.map((sl, i) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300">
                    {sl.platform}
                  </span>
                  <a
                    href={sl.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-400 hover:underline truncate text-xs"
                  >
                    {sl.handle || sl.url}
                  </a>
                  <span className="text-xs text-zinc-500 shrink-0">
                    {(sl.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Gaps */}
        {module.gaps.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase mb-2">
              Gaps ({module.gaps.length})
            </h3>
            <ul className="space-y-1">
              {module.gaps.map((gap, i) => (
                <li key={i} className="text-xs text-amber-400/80 bg-amber-500/10 rounded px-2 py-1.5">
                  {gap}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
