import { useParams } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { LogPanel } from '@/components/run/LogPanel'
import { ModuleGraph } from '@/components/run/ModuleGraph'
import { getMockLogs, getMockModules } from '@/lib/mock-run'

export function RunPage() {
  const { runId } = useParams()
  const logs = getMockLogs()
  const modules = getMockModules()

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border-subtle">
        <h1 className="text-sm font-semibold tracking-tight">Run</h1>
        <Badge variant="outline" className="text-text-primary bg-white/5 border-white/20">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
          {runId}
        </Badge>
        <span className="text-xs text-text-tertiary ml-auto">
          {modules.filter(m => m.status === 'ok').length} ok
          {' / '}
          {modules.filter(m => m.status === 'error').length} error
          {' / '}
          {modules.filter(m => m.status === 'skipped').length} skipped
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
