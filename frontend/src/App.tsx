import { useCallback, useEffect, useState } from "react";
import type {
  EnrichmentResponse,
  ModuleInfo,
  ModuleResult,
  AuditEvent,
} from "./api/types";
import { fetchModules, fetchRun } from "./api/client";
import { streamEnrich } from "./api/stream";

import { Sidebar } from "./components/Sidebar";
import { CaseForm } from "./components/CaseForm";
import { PipelineGraph } from "./components/graph/PipelineGraph";
import { ExecutionTimeline } from "./components/timeline/ExecutionTimeline";
import { ModuleDetail } from "./components/detail/ModuleDetail";
import { DossierView } from "./components/detail/DossierView";

type Tab = "graph" | "timeline" | "dossier";

function App() {
  const [moduleInfos, setModuleInfos] = useState<ModuleInfo[]>([]);
  const [response, setResponse] = useState<EnrichmentResponse | null>(null);
  const [selectedRun, setSelectedRun] = useState<{
    caseId: string;
    filename: string;
  } | null>(null);
  const [selectedModule, setSelectedModule] = useState<ModuleResult | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("graph");
  const [showForm, setShowForm] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveEvents, setLiveEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchModules().then(setModuleInfos).catch(console.error);
  }, []);

  const loadRun = useCallback(
    async (caseId: string, filename: string) => {
      setLoading(true);
      setError(null);
      setSelectedModule(null);
      setLiveEvents([]);
      try {
        const data = await fetchRun(caseId, filename);
        setResponse(data);
        setSelectedRun({ caseId, filename });
      } catch (err) {
        setError(String(err));
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const startEnrichment = useCallback(
    (payload: Record<string, unknown>) => {
      setShowForm(false);
      setIsStreaming(true);
      setResponse(null);
      setSelectedModule(null);
      setLiveEvents([]);
      setError(null);
      setActiveTab("graph");

      streamEnrich(payload, {
        onEvent: (ev) => {
          setLiveEvents((prev) => [...prev, ev]);
        },
        onResult: (res) => {
          setResponse(res);
          setIsStreaming(false);
        },
        onError: (msg) => {
          setError(msg);
          setIsStreaming(false);
        },
      }).catch((err) => {
        setError(String(err));
        setIsStreaming(false);
      });
    },
    []
  );

  const handleNodeClick = useCallback(
    (moduleName: string) => {
      const mod = response?.modules.find((m) => m.name === moduleName);
      if (mod) setSelectedModule(mod);
    },
    [response]
  );

  const totalTime = response?.audit_log.at(-1)?.elapsed_s;

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100">
      <Sidebar
        onSelectRun={loadRun}
        onNewCase={() => setShowForm(true)}
        selectedRun={selectedRun}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-12 shrink-0 border-b border-zinc-800 flex items-center px-4 gap-4">
          <div className="flex items-center gap-2">
            {response && (
              <span className="text-sm font-medium text-zinc-300">
                {response.case_id}
              </span>
            )}
            {isStreaming && (
              <span className="text-xs text-amber-400 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-pulse" />
                Enriching...
              </span>
            )}
            {totalTime != null && !isStreaming && (
              <span className="text-xs text-zinc-500">
                {totalTime.toFixed(2)}s
              </span>
            )}
          </div>

          {/* Tabs */}
          <nav className="flex gap-1 ml-auto">
            {(["graph", "timeline", "dossier"] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  activeTab === tab
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50"
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </nav>
        </header>

        {/* Main content */}
        <div className="flex-1 flex min-h-0">
          <div className="flex-1 min-w-0">
            {error && (
              <div className="m-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-400">
                {error}
              </div>
            )}

            {loading && (
              <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
                Loading...
              </div>
            )}

            {!loading && activeTab === "graph" && (
              <PipelineGraph
                response={response}
                moduleInfos={moduleInfos}
                liveEvents={isStreaming ? liveEvents : undefined}
                onNodeClick={handleNodeClick}
              />
            )}

            {!loading && activeTab === "timeline" && (
              <ExecutionTimeline
                response={response}
                liveEvents={isStreaming ? liveEvents : undefined}
              />
            )}

            {!loading && activeTab === "dossier" && response && (
              <DossierView response={response} />
            )}

            {!loading && activeTab === "dossier" && !response && (
              <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
                No dossier data. Select a run or submit a case.
              </div>
            )}
          </div>

          {/* Module detail panel */}
          {selectedModule && activeTab === "graph" && (
            <ModuleDetail
              module={selectedModule}
              onClose={() => setSelectedModule(null)}
            />
          )}
        </div>
      </div>

      {showForm && (
        <CaseForm
          onSubmit={startEnrichment}
          onClose={() => setShowForm(false)}
          isStreaming={isStreaming}
        />
      )}
    </div>
  );
}

export default App;
