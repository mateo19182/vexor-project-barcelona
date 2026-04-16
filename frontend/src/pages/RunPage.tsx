import { useEffect, useRef, useState } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { LogPanel } from '@/components/run/LogPanel'
import { ModuleGraph } from '@/components/run/ModuleGraph'
import { connectEnrichWs, type WsEvent, type CasePayload } from '@/lib/api'
import type { LogEntry, ModuleNode } from '@/lib/mock-run'

export function RunPage() {
  const { runId } = useParams()
  const location = useLocation()
  const state = location.state as { payload?: CasePayload; only?: string[] } | null

  const [logs, setLogs] = useState<LogEntry[]>([])
  const [modules, setModules] = useState<ModuleNode[]>([])
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const logCounter = useRef(0)
  const connected = useRef(false)

  useEffect(() => {
    if (!state?.payload || connected.current) return
    connected.current = true

    const close = connectEnrichWs(
      state.payload,
      (ev: WsEvent) => {
        if (ev.kind === 'module_completed' && ev.module) {
          const id = logCounter.current++
          const ts = new Date().toISOString().slice(11, 19)
          const status = (ev.message?.includes('skipped') ? 'skipped'
            : ev.message?.includes('error') || ev.message?.includes('failed') ? 'error'
            : 'ok') as LogEntry['status']

          setLogs(prev => [...prev, {
            id: `log-${id}`,
            timestamp: ts,
            module: ev.module!,
            status,
            message: ev.message ?? '',
            duration_s: ev.elapsed_s,
          }])
        }

        if (ev.kind === 'module_result' && ev.module) {
          setModules(prev => [...prev, {
            name: ev.module!,
            status: (ev.status as ModuleNode['status']) ?? 'ok',
            signalCount: ev.signal_count ?? 0,
            duration_s: ev.duration_s,
          }])
        }
      },
      () => setDone(true),
      (err) => setError(err),
    )

    return close
  }, [state])

  const okCount = modules.filter(m => m.status === 'ok').length
  const errCount = modules.filter(m => m.status === 'error').length
  const skipCount = modules.filter(m => m.status === 'skipped').length

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border-subtle">
        <h1 className="text-sm font-semibold tracking-tight">Run</h1>
        <Badge variant="outline" className="text-text-primary bg-white/5 border-white/20">
          {done ? (
            <span className="w-1.5 h-1.5 rounded-full bg-white" />
          ) : (
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
          )}
          {runId}
        </Badge>
        {error && <span className="text-xs text-zinc-400">{error}</span>}
        <span className="text-xs text-text-tertiary ml-auto">
          {done ? 'Complete' : 'Running...'}
          {modules.length > 0 && ` — ${okCount} ok / ${errCount} error / ${skipCount} skipped`}
        </span>
      </div>

      <div className="flex-1 flex gap-3 p-3 min-h-0">
        <div className="w-[45%] min-w-[320px]">
          <LogPanel logs={logs} />
        </div>
        <div className="flex-1">
          <ModuleGraph modules={modules} />
        </div>
      </div>
    </div>
  )
}
