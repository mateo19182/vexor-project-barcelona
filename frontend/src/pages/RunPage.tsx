import { useEffect, useState, useRef } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { PipelineGraph } from '@/components/graph/PipelineGraph'
import { ExecutionTimeline } from '@/components/timeline/ExecutionTimeline'
import { DossierView } from '@/components/detail/DossierView'
import { ModuleDetail } from '@/components/detail/ModuleDetail'
import { streamEnrich } from '@/api/stream'
import { fetchModules } from '@/api/client'
import type { EnrichmentResponse, ModuleInfo, AuditEvent, ModuleResult } from '@/api/types'
import type { CasePayload } from '@/lib/api'

type Tab = 'graph' | 'timeline' | 'dossier'

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
    { key: 'dossier', label: 'Dossier' },
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
        </div>

        {error && <span className="text-xs text-zinc-400 ml-2">{error}</span>}

        <span className="text-xs text-text-tertiary ml-auto">
          {isStreaming ? 'Running...' : response ? 'Complete' : 'Waiting...'}
          {response && ` — ${okCount} ok / ${errCount} error / ${skipCount} skipped`}
        </span>
      </div>

      <div className="flex-1 flex min-h-0">
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
          {activeTab === 'dossier' && response && (
            <DossierView response={response} />
          )}
          {activeTab === 'dossier' && !response && (
            <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
              Dossier will appear when the pipeline completes.
            </div>
          )}
        </div>

        {selectedModule && (
          <ModuleDetail module={selectedModule} onClose={() => setSelectedModule(null)} />
        )}
      </div>
    </div>
  )
}
