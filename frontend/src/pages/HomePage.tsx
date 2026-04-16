import { useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

export function HomePage() {
  const fileInputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="mx-auto max-w-2xl px-8 py-8">
      <h1 className="text-2xl font-semibold tracking-tight mb-8">
        New Case
      </h1>

      <Card className="bg-bg-surface/50 backdrop-blur-lg border-border-subtle mb-6">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-text-primary">
            Debtor Information
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="name" className="text-sm font-medium text-text-secondary">Name</label>
            <Input
              id="name"
              placeholder="Full name"
              className="bg-bg-elevated/60 backdrop-blur-sm border-border-default text-text-primary placeholder:text-text-tertiary focus:border-text-primary"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium text-text-secondary">Email</label>
            <Input
              id="email"
              type="email"
              placeholder="email@example.com"
              className="bg-bg-elevated/60 backdrop-blur-sm border-border-default text-text-primary placeholder:text-text-tertiary focus:border-text-primary"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="phone" className="text-sm font-medium text-text-secondary">Phone</label>
            <Input
              id="phone"
              type="tel"
              placeholder="+34 600 000 000"
              className="bg-bg-elevated/60 backdrop-blur-sm border-border-default text-text-primary placeholder:text-text-tertiary focus:border-text-primary"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="address" className="text-sm font-medium text-text-secondary">Address</label>
            <Input
              id="address"
              placeholder="Street, city, country"
              className="bg-bg-elevated/60 backdrop-blur-sm border-border-default text-text-primary placeholder:text-text-tertiary focus:border-text-primary"
            />
          </div>

          <div className="flex items-center gap-3 pt-4">
            <Button className="bg-white text-text-inverse hover:bg-zinc-200">
              Run Enrichment
            </Button>

            <div className="text-text-tertiary text-sm">or</div>

            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
            />
            <Button
              variant="outline"
              className="border-border-default text-text-primary hover:border-text-primary hover:bg-bg-overlay"
              onClick={() => fileInputRef.current?.click()}
            >
              Import .csv
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
