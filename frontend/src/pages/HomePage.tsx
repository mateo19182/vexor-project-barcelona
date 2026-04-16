import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { buildCase, submitCase, parseCsv } from '@/lib/api'

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

  async function handleSubmit() {
    setNameError('')
    setSubmitError('')

    if (!name.trim()) {
      setNameError('Name is required')
      return
    }

    setSubmitting(true)
    try {
      const payload = buildCase({ name: name.trim(), email: email.trim(), phone: phone.trim(), address: address.trim() })
      await submitCase(payload)
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
    // Reset so the same file can be re-selected
    e.target.value = ''
  }

  const inputClasses = "bg-bg-elevated/60 backdrop-blur-sm border-border-default text-text-primary placeholder:text-text-tertiary focus:border-text-primary"

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
            {nameError && (
              <p className="text-xs text-zinc-400">{nameError}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium text-text-secondary">Email</label>
            <Input
              id="email"
              type="email"
              placeholder="email@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className={inputClasses}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="phone" className="text-sm font-medium text-text-secondary">Phone</label>
            <Input
              id="phone"
              type="tel"
              placeholder="+34 600 000 000"
              value={phone}
              onChange={e => setPhone(e.target.value)}
              className={inputClasses}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="address" className="text-sm font-medium text-text-secondary">Address</label>
            <Input
              id="address"
              placeholder="Street, city, country"
              value={address}
              onChange={e => setAddress(e.target.value)}
              className={inputClasses}
            />
          </div>

          {submitError && (
            <p className="text-xs text-zinc-400">{submitError}</p>
          )}

          <div className="flex items-center gap-3 pt-4">
            <Button
              className="bg-white text-text-inverse hover:bg-zinc-200 disabled:opacity-50"
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? 'Running...' : 'Run Enrichment'}
            </Button>

            <div className="text-text-tertiary text-sm">or</div>

            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleCsvImport}
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
