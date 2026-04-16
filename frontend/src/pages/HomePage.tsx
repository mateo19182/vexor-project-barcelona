import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'

export function HomePage() {
  return (
    <div className="mx-auto max-w-2xl px-8 py-8">
      <h1 className="text-2xl font-semibold tracking-tight mb-8">
        New Case
      </h1>

      {/* Theme validation card */}
      <Card className="bg-bg-surface border-border-subtle mb-6">
        <CardHeader>
          <div className="flex items-center gap-3">
            <CardTitle className="text-lg font-semibold text-text-primary">
              Design System Preview
            </CardTitle>
            <Badge variant="outline" className="text-emerald-400 bg-emerald-500/10 border-emerald-500/20">
              ok
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Status badges */}
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="text-emerald-400 bg-emerald-500/10 border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              ok
            </Badge>
            <Badge variant="outline" className="text-text-secondary bg-slate-500/10 border-slate-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
              no_data
            </Badge>
            <Badge variant="outline" className="text-text-tertiary bg-slate-700/20 border-slate-700/30">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-600" />
              skipped
            </Badge>
            <Badge variant="outline" className="text-red-400 bg-red-500/10 border-red-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              error
            </Badge>
            <Badge variant="outline" className="text-accent-cyan bg-cyan-500/10 border-cyan-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              running
            </Badge>
          </div>

          {/* Typography samples */}
          <div className="space-y-2">
            <p className="text-text-primary text-base">Primary body text (#E8EDF5)</p>
            <p className="text-text-secondary text-sm">Secondary muted text (#8A9BB8)</p>
            <p className="text-text-tertiary text-xs">Tertiary disabled text (#4A5A72)</p>
            <p className="font-mono text-sm text-accent-cyan">Monospace signal value</p>
          </div>

          {/* Input sample */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-secondary">Sample input</label>
            <Input
              placeholder="Enter debtor name..."
              className="bg-bg-elevated border-border-default text-text-primary placeholder:text-text-tertiary focus:border-accent-cyan"
            />
          </div>

          {/* Button variants */}
          <div className="flex flex-wrap gap-3">
            <Button className="bg-accent-cyan text-text-inverse hover:bg-cyan-300 hover:shadow-[0_0_16px_rgba(0,229,255,0.4)]">
              Primary
            </Button>
            <Button variant="outline" className="border-border-default text-text-primary hover:border-accent-cyan hover:text-accent-cyan">
              Secondary
            </Button>
            <Button variant="ghost" className="text-text-secondary hover:text-text-primary hover:bg-bg-overlay">
              Ghost
            </Button>
            <Button variant="outline" className="border-red-500/40 text-red-400 hover:border-red-500 hover:bg-red-500/10">
              Destructive
            </Button>
          </div>

          {/* Glow effects preview */}
          <div className="flex gap-4">
            <div className="glow-cyan rounded-md p-4 bg-bg-elevated text-xs text-text-secondary">
              glow-cyan
            </div>
            <div className="glow-violet rounded-md p-4 bg-bg-elevated text-xs text-text-secondary">
              glow-violet
            </div>
            <div className="glow-ok rounded-md p-4 bg-bg-elevated text-xs text-text-secondary">
              glow-ok
            </div>
            <div className="glow-error rounded-md p-4 bg-bg-elevated text-xs text-text-secondary">
              glow-error
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
