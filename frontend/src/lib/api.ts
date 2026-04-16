const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface CasePayload {
  case_id: string
  country: string | null
  signals: { kind: string; value: string; source: string; confidence: number; tag?: string }[]
  context: string
}

export interface EnrichmentResponse {
  case_id: string
  status: string
  dossier: unknown
  modules: unknown[]
  audit_log: unknown[]
}

export function buildCase(fields: {
  name: string
  email: string
  phone: string
  address: string
}): CasePayload {
  const signals: CasePayload['signals'] = []

  if (fields.name) {
    signals.push({ kind: 'name', value: fields.name, source: 'case_input', confidence: 1.0 })
  }
  if (fields.email) {
    signals.push({ kind: 'contact', tag: 'email', value: fields.email, source: 'case_input', confidence: 1.0 })
  }
  if (fields.phone) {
    signals.push({ kind: 'contact', tag: 'phone', value: fields.phone, source: 'case_input', confidence: 1.0 })
  }
  if (fields.address) {
    signals.push({ kind: 'address', value: fields.address, source: 'case_input', confidence: 1.0 })
  }

  return {
    case_id: fields.name.toLowerCase().replace(/\s+/g, '_') || 'unknown',
    country: null,
    signals,
    context: '',
  }
}

export async function submitCase(payload: CasePayload): Promise<EnrichmentResponse> {
  const res = await fetch(`${API_BASE}/enrich`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    throw new Error(`Enrichment failed: ${res.status}`)
  }
  return res.json()
}

export function parseCsv(text: string): Array<{ name: string; email: string; phone: string; address: string }> {
  const lines = text.trim().split('\n')
  if (lines.length < 2) return []

  const header = lines[0].toLowerCase().split(',').map(h => h.trim())
  const nameIdx = header.findIndex(h => h === 'name' || h === 'nombre')
  const emailIdx = header.findIndex(h => h === 'email' || h === 'correo')
  const phoneIdx = header.findIndex(h => h === 'phone' || h === 'telefono' || h === 'tel')
  const addressIdx = header.findIndex(h => h === 'address' || h === 'direccion')

  return lines.slice(1).filter(l => l.trim()).map(line => {
    const cols = line.split(',').map(c => c.trim())
    return {
      name: nameIdx >= 0 ? cols[nameIdx] ?? '' : '',
      email: emailIdx >= 0 ? cols[emailIdx] ?? '' : '',
      phone: phoneIdx >= 0 ? cols[phoneIdx] ?? '' : '',
      address: addressIdx >= 0 ? cols[addressIdx] ?? '' : '',
    }
  })
}
