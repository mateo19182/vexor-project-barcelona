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
        <Badge variant="outline" className="text-text-primary bg-white/5 border-white/20">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
          {runId}
        </Badge>
      </div>
      <p className="text-text-secondary">
        Pipeline visualization will render here in Phase 4.
      </p>
    </div>
  )
}
