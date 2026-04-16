import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { buildCase, submitCase, parseCsv, fetchModules, type ModuleInfo } from '@/lib/api'

export function HomePage() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [address, setAddress] = useState('')
  const [nameError, setNameError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const [modules, setModules] = useState<ModuleInfo[]>([])
  const [enabled, setEnabled] = useState<Record<string, boolean>>({})
  const [maxMode, setMaxMode] = useState(true)

  useEffect(() => {
    fetchModules()
      .then(mods => {
        setModules(mods)
        const all: Record<string, boolean> = {}
        for (const m of mods) all[m.name] = true
        setEnabled(all)
      })
      .catch(() => {})
  }, [])

  function toggleModule(modName: string) {
    setEnabled(prev => ({ ...prev, [modName]: !prev[modName] }))
  }

  function handleMaxToggle(on: boolean) {
    setMaxMode(on)
    if (on) {
      const all: Record<string, boolean> = {}
      for (const m of modules) all[m.name] = true
      setEnabled(all)
    }
  }

  async function handleSubmit() {
    setNameError('')
    setSubmitError('')

    if (!name.trim()) {
      setNameError('Name is required')
      return
    }

    const selected = modules.filter(m => enabled[m.name]).map(m => m.name)
    const only = maxMode ? undefined : selected

    setSubmitting(true)
    try {
      const payload = buildCase({ name: name.trim(), email: email.trim(), phone: phone.trim(), address: address.trim() })
      await submitCase(payload, only)
      navigate(`/run/${payload.case_id}`)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  function handleCsvImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = () => {
      const rows = parseCsv(reader.result as string)
      if (rows.length > 0) {
        const first = rows[0]
        setName(first.name)
        setEmail(first.email)
        setPhone(first.phone)
        setAddress(first.address)
        setNameError('')
        setSubmitError('')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const inputClasses = "bg-bg-elevated/60 backdrop-blur-sm border-border-default text-text-primary placeholder:text-text-tertiary focus:border-text-primary"
  const enabledCount = modules.filter(m => enabled[m.name]).length
  const [accordionOpen, setAccordionOpen] = useState(false)

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
              value={name}
              onChange={e => { setName(e.target.value); setNameError('') }}
              className={`${inputClasses} ${nameError ? 'border-zinc-400' : ''}`}
            />
            {nameError && <p className="text-xs text-zinc-400">{nameError}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium text-text-secondary">Email</label>
            <Input id="email" type="email" placeholder="email@example.com" value={email} onChange={e => setEmail(e.target.value)} className={inputClasses} />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="phone" className="text-sm font-medium text-text-secondary">Phone</label>
            <Input id="phone" type="tel" placeholder="+34 600 000 000" value={phone} onChange={e => setPhone(e.target.value)} className={inputClasses} />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="address" className="text-sm font-medium text-text-secondary">Address</label>
            <Input id="address" placeholder="Street, city, country" value={address} onChange={e => setAddress(e.target.value)} className={inputClasses} />
          </div>

          {submitError && <p className="text-xs text-zinc-400">{submitError}</p>}

          <div className="flex items-center gap-3 pt-4">
            <Button className="bg-white text-text-inverse hover:bg-zinc-200 disabled:opacity-50" onClick={handleSubmit} disabled={submitting}>
              {submitting ? 'Running...' : 'Run Enrichment'}
            </Button>
            <div className="text-text-tertiary text-sm">or</div>
            <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={handleCsvImport} />
            <Button variant="outline" className="border-border-default text-text-primary hover:border-text-primary hover:bg-bg-overlay" onClick={() => fileInputRef.current?.click()}>
              Import .csv
            </Button>
          </div>
        </CardContent>
      </Card>

      {modules.length > 0 && (
        <Card className="bg-bg-surface/50 backdrop-blur-lg border-border-subtle">
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-text-primary">Modules</span>
                <span className="text-xs text-text-tertiary">
                  {maxMode ? 'MAX' : `${enabledCount}/${modules.length}`}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-text-secondary">MAX</span>
                <Switch checked={maxMode} onCheckedChange={handleMaxToggle} />
              </div>
            </div>

            {!maxMode && (
              <div className="mt-4">
                <button
                  onClick={() => setAccordionOpen(!accordionOpen)}
                  className="flex items-center gap-2 text-xs text-text-secondary hover:text-text-primary transition-colors w-full"
                >
                  <svg
                    className={`w-3 h-3 transition-transform ${accordionOpen ? 'rotate-90' : ''}`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                  Select modules ({enabledCount} active)
                </button>

                {accordionOpen && (
                  <div className="grid grid-cols-2 gap-2 mt-3">
                    {modules.map(m => (
                      <div
                        key={m.name}
                        className="flex items-center justify-between rounded-md px-3 py-2 bg-bg-elevated/40 backdrop-blur-sm border border-border-subtle"
                      >
                        <div className="flex flex-col">
                          <span className="text-xs font-mono text-text-primary">{m.name}</span>
                          {m.requires.length > 0 && (
                            <span className="text-[10px] text-text-tertiary">{m.requires.join(', ')}</span>
                          )}
                        </div>
                        <Switch
                          checked={!!enabled[m.name]}
                          onCheckedChange={() => toggleModule(m.name)}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
