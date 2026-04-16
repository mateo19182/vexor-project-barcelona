const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const WS_BASE = API_BASE.replace(/^http/, 'ws')

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

  // Infer country from address
  const addrLower = fields.address.toLowerCase()
  const esKeywords = ['spain', 'españa', 'espana', ', es', 'madrid', 'barcelona',
    'valencia', 'sevilla', 'bilbao', 'málaga', 'malaga', 'zaragoza', 'murcia',
    'vigo', 'coruña', 'galicia', 'cataluña', 'euskadi']
  const country = esKeywords.some(kw => addrLower.includes(kw)) ? 'ES' : null

  return {
    case_id: fields.name.toLowerCase().replace(/\s+/g, '_') || 'unknown',
    country,
    signals,
    context: '',
  }
}

export interface ModuleInfo {
  name: string
  requires: string[]
}

export async function fetchModules(): Promise<ModuleInfo[]> {
  const res = await fetch(`${API_BASE}/modules`)
  if (!res.ok) throw new Error(`Failed to fetch modules: ${res.status}`)
  const data = await res.json()
  return data.modules
}

export async function submitCase(payload: CasePayload, only?: string[]): Promise<EnrichmentResponse> {
  const params = only ? '?' + only.map(m => `only=${encodeURIComponent(m)}`).join('&') : ''
  const res = await fetch(`${API_BASE}/enrich${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    throw new Error(`Enrichment failed: ${res.status}`)
  }
  return res.json()
}

export interface WsEvent {
  kind: string
  module?: string
  wave?: number
  message?: string
  elapsed_s?: number
  status?: string
  signal_count?: number
  fact_count?: number
  gaps?: string[]
  summary?: string
  duration_s?: number
}

export function connectEnrichWs(
  payload: CasePayload,
  onEvent: (ev: WsEvent) => void,
  onDone: () => void,
  onError: (err: string) => void,
): () => void {
  const ws = new WebSocket(`${WS_BASE}/ws/enrich`)

  ws.onopen = () => {
    ws.send(JSON.stringify(payload))
  }

  ws.onmessage = (msg) => {
    const ev: WsEvent = JSON.parse(msg.data)
    if (ev.kind === 'pipeline_completed') {
      onDone()
      ws.close()
    } else if (ev.kind === 'error') {
      onError(ev.message ?? 'Unknown error')
      ws.close()
    } else {
      onEvent(ev)
    }
  }

  ws.onerror = () => {
    onError('WebSocket connection failed')
  }

  ws.onclose = () => {}

  return () => ws.close()
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
