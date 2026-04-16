import { useEffect, useRef, useState } from 'react'
import type { AuditEvent, EnrichmentResponse, ModuleResult } from '@/api/types'

interface LogPanelProps {
  events: AuditEvent[]
  response: EnrichmentResponse | null
  isStreaming: boolean
}

const statusDot: Record<string, string> = {
  ok: 'bg-white',
  error: 'bg-zinc-400',
  skipped: 'bg-zinc-600',
  no_data: 'bg-zinc-500',
  cached: 'bg-zinc-400',
}

function ModuleAccordion({
  ev,
  moduleResult,
  isOpen,
  onToggle,
}: {
  ev: AuditEvent
  moduleResult: ModuleResult | undefined
  isOpen: boolean
  onToggle: () => void
}) {
  const status = (ev.detail?.status as string) || 'unknown'
  const signals = (ev.detail?.signals as number) || 0
  const facts = (ev.detail?.facts as number) || 0
  const gaps = (ev.detail?.gaps as number) || 0
  const duration = (ev.detail?.duration_s as number) || (ev.detail?.cached_duration_s as number) || 0
  const isCached = ev.kind === 'module_cache_hit'
  const dot = statusDot[isCached ? 'cached' : status] || 'bg-zinc-600'

  return (
    <div className="rounded-lg overflow-hidden">
      {/* Header — always visible, clickable */}
      <button
        onClick={onToggle}
        className={`w-full flex items-start gap-2 px-2 py-1.5 text-left transition-colors rounded-lg ${
          isOpen ? 'bg-bg-elevated/50' : 'hover:bg-bg-elevated/30'
        }`}
      >
        <span className="text-[10px] text-text-tertiary w-12 text-right shrink-0 tabular-nums mt-0.5">
          {ev.elapsed_s.toFixed(1)}s
        </span>
        <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${dot}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-primary font-mono truncate">{ev.module}</span>
            {isCached && (
              <span className="text-[9px] px-1 py-0.5 rounded bg-zinc-800 text-zinc-500">cached</span>
            )}
            {status === 'error' && (
              <span className="text-[9px] px-1 py-0.5 rounded bg-zinc-700 text-zinc-400">error</span>
            )}
            {status === 'skipped' && (
              <span className="text-[9px] px-1 py-0.5 rounded bg-zinc-800 text-zinc-600">skipped</span>
            )}
            <span className={`text-[10px] ml-auto shrink-0 transition-transform ${isOpen ? 'rotate-90' : ''}`}>
              ›
            </span>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-text-tertiary">
            {duration > 0 && <span>{duration.toFixed(2)}s</span>}
            {signals > 0 && <span>{signals} sig</span>}
            {facts > 0 && <span>{facts} fact</span>}
            {gaps > 0 && <span>{gaps} gap</span>}
          </div>
        </div>
      </button>

      {/* Expanded detail */}
      {isOpen && moduleResult && (
        <div className="mx-2 mb-2 px-3 py-2 bg-bg-overlay/50 rounded-lg border border-border-subtle space-y-2">
          {moduleResult.summary && (
            <div>
              <span className="text-[9px] text-text-tertiary uppercase font-semibold">Summary</span>
              <p className="text-[11px] text-text-secondary leading-relaxed mt-0.5">{moduleResult.summary}</p>
            </div>
          )}

          {moduleResult.signals.length > 0 && (
            <div>
              <span className="text-[9px] text-text-tertiary uppercase font-semibold">
                Signals ({moduleResult.signals.length})
              </span>
              <div className="mt-1 space-y-1">
                {moduleResult.signals.map((sig, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-[9px] px-1 py-0.5 rounded bg-bg-surface text-text-tertiary font-mono shrink-0">
                      {sig.tag ? `${sig.kind}:${sig.tag}` : sig.kind}
                    </span>
                    <span className="text-[11px] text-text-secondary flex-1 break-all">{sig.value}</span>
                    <span className="text-[9px] text-text-tertiary shrink-0">{(sig.confidence * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {moduleResult.facts.length > 0 && (
            <div>
              <span className="text-[9px] text-text-tertiary uppercase font-semibold">
                Facts ({moduleResult.facts.length})
              </span>
              <div className="mt-1 space-y-1">
                {moduleResult.facts.map((fact, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-[11px] text-text-secondary flex-1">{fact.claim}</span>
                    <span className="text-[9px] text-text-tertiary shrink-0">{(fact.confidence * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {moduleResult.social_links.length > 0 && (
            <div>
              <span className="text-[9px] text-text-tertiary uppercase font-semibold">
                Social links ({moduleResult.social_links.length})
              </span>
              <div className="mt-1 space-y-1">
                {moduleResult.social_links.map((sl, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="text-text-tertiary font-mono">{sl.platform}</span>
                    <span className="text-text-secondary truncate flex-1">{sl.handle || sl.url}</span>
                    <span className="text-[9px] text-text-tertiary shrink-0">{(sl.confidence * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {moduleResult.gaps.length > 0 && (
            <div>
              <span className="text-[9px] text-text-tertiary uppercase font-semibold">
                Gaps ({moduleResult.gaps.length})
              </span>
              <ul className="mt-1 space-y-0.5">
                {moduleResult.gaps.map((gap, i) => (
                  <li key={i} className="text-[10px] text-text-tertiary">- {gap}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SummaryBar({ response }: { response: EnrichmentResponse }) {
  const okCount = response.modules.filter(m => m.status === 'ok').length
  const errCount = response.modules.filter(m => m.status === 'error').length
  const skipCount = response.modules.filter(m => m.status === 'skipped').length
  const totalSignals = response.modules.reduce((s, m) => s + m.signals.length, 0)
  const totalFacts = response.modules.reduce((s, m) => s + m.facts.length, 0)
  const elapsed = response.audit_log.find(e => e.kind === 'pipeline_completed')?.elapsed_s

  return (
    <div className="px-4 py-3 border-t border-border-subtle bg-bg-surface/50 space-y-2">
      <div className="flex items-center gap-3 text-xs">
        <span className="text-text-primary font-medium">{okCount} ok</span>
        {errCount > 0 && <span className="text-zinc-400">{errCount} error</span>}
        {skipCount > 0 && <span className="text-zinc-600">{skipCount} skip</span>}
        {elapsed && <span className="text-text-tertiary ml-auto">{elapsed.toFixed(1)}s total</span>}
      </div>
      <div className="flex items-center gap-3 text-[10px] text-text-tertiary">
        <span>{totalSignals} signals</span>
        <span>{totalFacts} facts</span>
        <span>{response.status}</span>
      </div>
    </div>
  )
}

export function LogPanel({ events, response, isStreaming }: LogPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [expandedModule, setExpandedModule] = useState<string | null>(null)

  // Build a map of module name -> ModuleResult for accordion detail
  const moduleMap = new Map(
    (response?.modules || []).map(m => [m.name, m])
  )

  // Auto-expand the last completed module
  const lastCompletedModule = [...events]
    .reverse()
    .find(e => (e.kind === 'module_completed' || e.kind === 'module_cache_hit') && e.module)
    ?.module ?? null

  // If user hasn't manually toggled, show last completed
  const effectiveExpanded = expandedModule ?? lastCompletedModule

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length, response])

  // Reset manual selection when a new module completes (so it auto-tracks)
  useEffect(() => {
    setExpandedModule(null)
  }, [lastCompletedModule])

  function handleToggle(moduleName: string) {
    setExpandedModule(prev => prev === moduleName ? null : moduleName)
  }

  return (
    <div className="h-full flex flex-col bg-black/80 backdrop-blur-lg border-r border-border-subtle overflow-hidden">
      <div className="px-4 py-2 border-b border-border-subtle flex items-center gap-2">
        {isStreaming ? (
          <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
        ) : (
          <span className="w-2 h-2 rounded-full bg-zinc-500" />
        )}
        <span className="text-xs font-mono text-text-secondary">
          {response ? 'complete' : 'running...'}
        </span>
        <span className="text-[10px] text-text-tertiary ml-auto">
          {events.length} events
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        {events.length === 0 && (
          <div className="text-[11px] text-zinc-600 py-4 text-center">
            Waiting for pipeline events...
          </div>
        )}
        {events.map((ev, i) => {
          // Module events get the accordion treatment
          if ((ev.kind === 'module_completed' || ev.kind === 'module_cache_hit') && ev.module) {
            return (
              <ModuleAccordion
                key={i}
                ev={ev}
                moduleResult={moduleMap.get(ev.module)}
                isOpen={effectiveExpanded === ev.module}
                onToggle={() => handleToggle(ev.module!)}
              />
            )
          }

          // Pipeline start
          if (ev.kind === 'pipeline_started') {
            const modules = ev.detail?.modules as string[] | undefined
            return (
              <div key={i} className="flex items-start gap-2 px-2 py-1.5">
                <span className="text-[10px] text-text-tertiary w-12 text-right shrink-0 tabular-nums">
                  {ev.elapsed_s.toFixed(1)}s
                </span>
                <span className="w-1.5 h-1.5 rounded-full bg-white mt-1 shrink-0" />
                <span className="text-xs text-white">
                  Pipeline started — {modules?.length || '?'} modules
                </span>
              </div>
            )
          }

          // Pipeline end
          if (ev.kind === 'pipeline_completed') {
            return (
              <div key={i} className="flex items-start gap-2 px-2 py-1.5">
                <span className="text-[10px] text-text-tertiary w-12 text-right shrink-0 tabular-nums">
                  {ev.elapsed_s.toFixed(1)}s
                </span>
                <span className="w-1.5 h-1.5 rounded-full bg-white mt-1 shrink-0" />
                <span className="text-xs text-white">{ev.message}</span>
              </div>
            )
          }

          // Wave header
          if (ev.kind === 'wave_started') {
            const modules = ev.detail?.modules as string[] | undefined
            return (
              <div key={i} className="flex items-start gap-2 mt-3 mb-1 px-2 py-1.5">
                <span className="text-[10px] text-text-tertiary w-12 text-right shrink-0 tabular-nums">
                  {ev.elapsed_s.toFixed(1)}s
                </span>
                <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 mt-1 shrink-0" />
                <div>
                  <span className="text-[10px] text-text-tertiary uppercase font-semibold">
                    Wave {ev.wave}
                  </span>
                  {modules && (
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {modules.map((m) => (
                        <span key={m} className="text-[10px] px-1.5 py-0.5 rounded bg-bg-overlay text-text-secondary font-mono">
                          {m}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          }

          // Fallback
          return (
            <div key={i} className="flex items-start gap-2 px-2 py-1.5">
              <span className="text-[10px] text-text-tertiary w-12 text-right shrink-0 tabular-nums">
                {ev.elapsed_s.toFixed(1)}s
              </span>
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-700 mt-1 shrink-0" />
              <span className="text-[10px] text-text-tertiary truncate">{ev.message || ev.kind}</span>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      {response && <SummaryBar response={response} />}
    </div>
  )
}
