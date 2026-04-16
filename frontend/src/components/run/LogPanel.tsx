import { useEffect, useRef } from 'react'
import type { LogEntry } from '@/lib/mock-run'

const statusDot: Record<string, string> = {
  ok: 'bg-white',
  running: 'bg-white animate-pulse',
  skipped: 'bg-zinc-600',
  error: 'bg-zinc-400',
  no_data: 'bg-zinc-500',
}

export function LogPanel({ logs }: { logs: LogEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  return (
    <div className="h-full flex flex-col bg-bg-surface/40 backdrop-blur-lg rounded-lg border border-border-subtle overflow-hidden">
      <div className="px-4 py-3 border-b border-border-subtle">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Log</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5 font-mono text-xs">
        {logs.map(entry => (
          <div key={entry.id} className="flex items-start gap-2 px-2 py-1 rounded hover:bg-bg-overlay/50">
            <span className="text-text-tertiary shrink-0 w-16">{entry.timestamp}</span>
            <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${statusDot[entry.status] ?? 'bg-zinc-600'}`} />
            <span className="text-text-primary shrink-0 w-32 truncate">{entry.module}</span>
            <span className="text-text-secondary">{entry.message}</span>
            {entry.duration_s != null && (
              <span className="text-text-tertiary ml-auto shrink-0">{entry.duration_s.toFixed(1)}s</span>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
