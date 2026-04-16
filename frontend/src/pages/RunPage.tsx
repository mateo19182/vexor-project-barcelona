import { useEffect, useState, useRef } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { LogPanel } from '@/components/run/LogPanel'
import { PipelineGraph } from '@/components/graph/PipelineGraph'
import { ExecutionTimeline } from '@/components/timeline/ExecutionTimeline'
import { DossierView } from '@/components/detail/DossierView'
import { ModuleDetail } from '@/components/detail/ModuleDetail'
import { streamEnrich } from '@/api/stream'
import { fetchModules } from '@/api/client'
import type { EnrichmentResponse, ModuleInfo, AuditEvent, ModuleResult } from '@/api/types'
import type { CasePayload } from '@/lib/api'

type Tab = 'graph' | 'timeline'

export function RunPage() {
  const { runId } = useParams()
  const location = useLocation()
  const state = location.state as { payload?: CasePayload; only?: string[] } | null

  const [activeTab, setActiveTab] = useState<Tab>('graph')
  const [moduleInfos, setModuleInfos] = useState<ModuleInfo[]>([])
  const [response, setResponse] = useState<EnrichmentResponse | null>(null)
  const [liveEvents, setLiveEvents] = useState<AuditEvent[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState('')
  const [selectedModule, setSelectedModule] = useState<ModuleResult | null>(null)
  const [showDossier, setShowDossier] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    fetchModules().then(setModuleInfos).catch(() => {})
  }, [])

  useEffect(() => {
    if (!state?.payload || started.current) return
    started.current = true
    setIsStreaming(true)

    streamEnrich(state.payload, {
      onEvent: (ev) => {
        setLiveEvents((prev) => [...prev, ev])
      },
      onResult: (res) => {
        setResponse(res)
        setIsStreaming(false)
        setShowDossier(true)
      },
      onError: (err) => {
        setError(err)
        setIsStreaming(false)
      },
    })
  }, [state])

  function handleNodeClick(moduleName: string) {
    const mod = response?.modules.find((m) => m.name === moduleName)
    if (mod) setSelectedModule(mod)
  }

  const okCount = response?.modules.filter((m) => m.status === 'ok').length ?? 0
  const errCount = response?.modules.filter((m) => m.status === 'error').length ?? 0
  const skipCount = response?.modules.filter((m) => m.status === 'skipped').length ?? 0

  const tabs: { key: Tab; label: string }[] = [
    { key: 'graph', label: 'Graph' },
    { key: 'timeline', label: 'Timeline' },
  ]

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border-subtle">
        <h1 className="text-sm font-semibold tracking-tight">Run</h1>
        <Badge variant="outline" className="text-text-primary bg-white/5 border-white/20">
          {isStreaming ? (
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
          ) : (
            <span className="w-1.5 h-1.5 rounded-full bg-white" />
          )}
          {runId}
        </Badge>

        <div className="flex items-center gap-1 ml-4">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                activeTab === tab.key
                  ? 'bg-white/10 text-text-primary'
                  : 'text-text-tertiary hover:text-text-secondary'
              }`}
            >
              {tab.label}
            </button>
          ))}
          {response && (
            <button
              onClick={() => setShowDossier(true)}
              className="px-3 py-1 text-xs rounded transition-colors text-text-tertiary hover:text-text-secondary"
            >
              Dossier
            </button>
          )}
        </div>

        {error && <span className="text-xs text-zinc-400 ml-2">{error}</span>}

        <span className="text-xs text-text-tertiary ml-auto">
          {isStreaming ? 'Running...' : response ? 'Complete' : 'Waiting...'}
          {response && ` — ${okCount} ok / ${errCount} error / ${skipCount} skipped`}
        </span>
      </div>

      <div className="flex-1 flex min-h-0">
        <div className="w-[380px] shrink-0">
          <LogPanel events={liveEvents} response={response} isStreaming={isStreaming} />
        </div>
        <div className="flex-1">
          {activeTab === 'graph' && (
            <PipelineGraph
              response={response}
              moduleInfos={moduleInfos}
              liveEvents={liveEvents}
              onNodeClick={handleNodeClick}
            />
          )}
          {activeTab === 'timeline' && (
            <ExecutionTimeline response={response} liveEvents={liveEvents} />
          )}
        </div>

        {selectedModule && (
          <ModuleDetail module={selectedModule} onClose={() => setSelectedModule(null)} />
        )}
      </div>

      {/* Dossier popup modal */}
      {showDossier && response && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowDossier(false)}
          />
          <div className="relative w-[90vw] max-w-4xl h-[85vh] bg-bg-surface/95 backdrop-blur-xl border border-border-subtle rounded-xl shadow-2xl overflow-hidden flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">Dossier</h2>
                <span className="text-xs text-text-tertiary">{response.case_id} — {okCount} ok / {errCount} error / {skipCount} skipped</span>
              </div>
              <button
                onClick={() => setShowDossier(false)}
                className="text-text-tertiary hover:text-text-primary text-xl px-2"
              >
                &times;
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <DossierView response={response} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
