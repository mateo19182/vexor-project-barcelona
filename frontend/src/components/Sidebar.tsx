import { useEffect, useState } from "react";
import { fetchCases } from "../api/client";
import type { CaseEntry } from "../api/types";

interface SidebarProps {
  onSelectRun: (caseId: string, filename: string) => void;
  onNewCase: () => void;
  selectedRun: { caseId: string; filename: string } | null;
}

export function Sidebar({ onSelectRun, onNewCase, selectedRun }: SidebarProps) {
  const [cases, setCases] = useState<CaseEntry[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCases()
      .then(setCases)
      .catch(() => setCases([]))
      .finally(() => setLoading(false));
  }, []);

  const toggle = (caseId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(caseId)) next.delete(caseId);
      else next.add(caseId);
      return next;
    });
  };

  return (
    <aside className="w-64 shrink-0 bg-zinc-900 border-r border-zinc-800 flex flex-col h-full">
      <div className="p-4 border-b border-zinc-800">
        <h1 className="text-sm font-bold text-zinc-100 tracking-wide uppercase">
          Vexor BCN
        </h1>
        <p className="text-xs text-zinc-500 mt-1">Pipeline Viewer</p>
      </div>

      <div className="p-3">
        <button
          onClick={onNewCase}
          className="w-full px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
        >
          + New Case
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {loading ? (
          <div className="text-xs text-zinc-500 p-3">Loading cases...</div>
        ) : cases.length === 0 ? (
          <div className="text-xs text-zinc-500 p-3">No cases found</div>
        ) : (
          cases.map((c) => (
            <div key={c.case_id} className="mb-1">
              <button
                onClick={() => toggle(c.case_id)}
                className="w-full text-left px-3 py-2 rounded-md text-sm text-zinc-300 hover:bg-zinc-800 flex items-center gap-2"
              >
                <span className={`text-[10px] transition-transform ${expanded.has(c.case_id) ? "rotate-90" : ""}`}>
                  &#9654;
                </span>
                <span className="font-medium">{c.case_id}</span>
                <span className="text-zinc-600 text-xs ml-auto">
                  {c.runs.length}
                </span>
              </button>

              {expanded.has(c.case_id) && (
                <div className="ml-5 border-l border-zinc-800 pl-2">
                  {c.runs.map((run) => {
                    const isSelected =
                      selectedRun?.caseId === c.case_id &&
                      selectedRun?.filename === run.file;
                    const ts = run.timestamp;
                    const display = `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(9, 11)}:${ts.slice(11, 13)}`;
                    return (
                      <button
                        key={run.file}
                        onClick={() => onSelectRun(c.case_id, run.file)}
                        className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${
                          isSelected
                            ? "bg-zinc-700 text-zinc-100"
                            : "text-zinc-500 hover:bg-zinc-800/50 hover:text-zinc-300"
                        }`}
                      >
                        {display}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
