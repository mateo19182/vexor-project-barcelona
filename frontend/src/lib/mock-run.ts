export interface LogEntry {
  id: string
  timestamp: string
  module: string
  status: 'ok' | 'skipped' | 'error' | 'running' | 'no_data'
  message: string
  duration_s?: number
}

export interface ModuleNode {
  name: string
  status: 'ok' | 'skipped' | 'error' | 'running' | 'no_data' | 'pending'
  signalCount: number
  duration_s?: number
}

const MOCK_MODULES: ModuleNode[] = [
  { name: 'boe', status: 'ok', signalCount: 2, duration_s: 1.2 },
  { name: 'borme', status: 'ok', signalCount: 1, duration_s: 0.8 },
  { name: 'brave_social', status: 'ok', signalCount: 3, duration_s: 2.1 },
  { name: 'breach_scout', status: 'skipped', signalCount: 0, duration_s: 0.1 },
  { name: 'github_check', status: 'no_data', signalCount: 0, duration_s: 0.5 },
  { name: 'gaia_enrichment', status: 'skipped', signalCount: 0, duration_s: 0.1 },
  { name: 'icloud_check', status: 'ok', signalCount: 1, duration_s: 0.9 },
  { name: 'image_search', status: 'skipped', signalCount: 0, duration_s: 0.1 },
  { name: 'instagram', status: 'skipped', signalCount: 0, duration_s: 0.1 },
  { name: 'instagram_check', status: 'ok', signalCount: 1, duration_s: 1.1 },
  { name: 'jooble', status: 'skipped', signalCount: 0, duration_s: 0.1 },
  { name: 'linkedin', status: 'skipped', signalCount: 0, duration_s: 0.1 },
  { name: 'nosint', status: 'ok', signalCount: 4, duration_s: 3.2 },
  { name: 'osint_web', status: 'ok', signalCount: 5, duration_s: 8.4 },
  { name: 'property', status: 'no_data', signalCount: 0, duration_s: 1.5 },
  { name: 'twitter_check', status: 'ok', signalCount: 1, duration_s: 0.7 },
  { name: 'twitter', status: 'skipped', signalCount: 0, duration_s: 0.1 },
  { name: 'wallapop', status: 'ok', signalCount: 3, duration_s: 4.1 },
  { name: 'xon', status: 'error', signalCount: 0, duration_s: 0.3 },
]

export function getMockModules(): ModuleNode[] {
  return MOCK_MODULES
}

export function getMockLogs(): LogEntry[] {
  let t = 0
  return MOCK_MODULES.map((m, i) => {
    t += m.duration_s ?? 0.5
    const ts = new Date(Date.now() - (MOCK_MODULES.length - i) * 1000)
    return {
      id: `log-${i}`,
      timestamp: ts.toISOString().slice(11, 19),
      module: m.name,
      status: m.status === 'pending' ? 'running' : m.status,
      message: m.status === 'ok'
        ? `${m.signalCount} signal${m.signalCount !== 1 ? 's' : ''} found`
        : m.status === 'skipped'
        ? 'requirements not met'
        : m.status === 'error'
        ? 'module failed'
        : 'no data found',
      duration_s: m.duration_s,
    }
  })
}
