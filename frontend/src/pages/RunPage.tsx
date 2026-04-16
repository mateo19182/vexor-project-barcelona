import { useParams } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'

export function RunPage() {
  const { runId } = useParams()

  return (
    <div className="mx-auto max-w-[1440px] px-8 py-8">
      <div className="flex items-center gap-3 mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Run View
        </h1>
        <Badge variant="outline" className="text-accent-cyan bg-cyan-500/10 border-cyan-500/20">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          {runId}
        </Badge>
      </div>
      <p className="text-text-secondary">
        Pipeline visualization will render here in Phase 4.
      </p>
    </div>
  )
}
