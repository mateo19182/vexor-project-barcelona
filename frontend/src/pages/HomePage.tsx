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
            <Badge variant="outline" className="text-text-primary bg-white/5 border-white/20">
              ok
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Status badges */}
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="text-text-primary bg-white/5 border-white/20">
              <span className="w-1.5 h-1.5 rounded-full bg-white" />
              ok
            </Badge>
            <Badge variant="outline" className="text-text-secondary bg-zinc-500/10 border-zinc-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-500" />
              no_data
            </Badge>
            <Badge variant="outline" className="text-text-tertiary bg-zinc-700/20 border-zinc-700/30">
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-600" />
              skipped
            </Badge>
            <Badge variant="outline" className="text-zinc-400 bg-zinc-500/10 border-zinc-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-400" />
              error
            </Badge>
            <Badge variant="outline" className="text-text-primary bg-white/5 border-white/20">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
              running
            </Badge>
          </div>

          {/* Typography samples */}
          <div className="space-y-2">
            <p className="text-text-primary text-base">Primary body text</p>
            <p className="text-text-secondary text-sm">Secondary muted text</p>
            <p className="text-text-tertiary text-xs">Tertiary disabled text</p>
            <p className="font-mono text-sm text-text-primary">Monospace signal value</p>
          </div>

          {/* Input sample */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-secondary">Sample input</label>
            <Input
              placeholder="Enter debtor name..."
              className="bg-bg-elevated border-border-default text-text-primary placeholder:text-text-tertiary focus:border-text-primary"
            />
          </div>

          {/* Button variants */}
          <div className="flex flex-wrap gap-3">
            <Button className="bg-white text-text-inverse hover:bg-zinc-200">
              Primary
            </Button>
            <Button variant="outline" className="border-border-default text-text-primary hover:border-text-primary hover:bg-bg-overlay">
              Secondary
            </Button>
            <Button variant="ghost" className="text-text-secondary hover:text-text-primary hover:bg-bg-overlay">
              Ghost
            </Button>
            <Button variant="outline" className="border-zinc-600 text-zinc-400 hover:border-zinc-500 hover:bg-zinc-800/50">
              Destructive
            </Button>
          </div>

          {/* Glow effects preview */}
          <div className="flex gap-4">
            <div className="glow-white rounded-md p-4 bg-bg-elevated text-xs text-text-secondary">
              glow-white
            </div>
            <div className="glow-muted rounded-md p-4 bg-bg-elevated text-xs text-text-secondary">
              glow-muted
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
