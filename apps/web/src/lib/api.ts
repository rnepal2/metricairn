/** Typed client for the Metricairn API. Read key lives in localStorage after login. */

export const BASE = (
  (import.meta as ImportMeta & { env: Record<string, string> }).env.VITE_API_URL || ''
).replace(/\/$/, '')

// Preserve existing browser credentials through the product rename.
try {
  for (const storage of [localStorage, sessionStorage]) {
    for (const key of ['read_key', 'management_key', 'tracker_key']) {
      const legacy = storage.getItem(`agentlens_${key}`)
      if (legacy && !storage.getItem(`metricairn_${key}`))
        storage.setItem(`metricairn_${key}`, legacy)
      storage.removeItem(`agentlens_${key}`)
    }
  }
} catch {
  /* Credential restoration can be retried when storage is available. */
}

export function getReadKey(): string | null {
  return localStorage.getItem('metricairn_read_key')
}

export function setReadKey(key: string) {
  if (getReadKey() !== key) {
    sessionStorage.removeItem('metricairn_management_key')
    sessionStorage.removeItem('metricairn_tracker_key')
  }
  localStorage.setItem('metricairn_read_key', key)
}

export function clearReadKey() {
  localStorage.removeItem('metricairn_read_key')
  localStorage.removeItem('metricairn_write_key')
  sessionStorage.removeItem('metricairn_management_key')
  sessionStorage.removeItem('metricairn_tracker_key')
}

/** Private management access is optional and stored only for this tab. */
export function getManagementKey(): string | null {
  return sessionStorage.getItem('metricairn_management_key')
}

export function setManagementKey(key: string) {
  sessionStorage.setItem('metricairn_management_key', key)
}

export async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const key = getReadKey()
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(key ? { 'X-Read-Key': key } : {}),
      ...(init.headers || {}),
    },
  })
  if (res.status === 401 || res.status === 403) {
    throw new Error('Read access denied — check your project key.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail =
      typeof body.detail === 'string' ? body.detail : 'Request failed. Check inputs and try again.'
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

/** Same as req() but authenticates with the private management key. */
export async function reqManage<T>(path: string, init: RequestInit = {}): Promise<T> {
  const key = getManagementKey()
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(key ? { 'X-Management-Key': key } : {}),
      ...(init.headers || {}),
    },
  })
  if (res.status === 401 || res.status === 403) {
    throw new Error('Invalid management key — enter the private alm_ key in Settings.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail =
      typeof body.detail === 'string' ? body.detail : 'Request failed. Check inputs and try again.'
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export interface Comparison {
  currency: string
  current_window: { from: string; to: string }
  previous_window: { from: string; to: string }
  metrics: {
    metric: string
    current: number
    previous: number
    change: number
    change_pct: number | null
  }[]
  notes: string[]
}
export interface RevenueReport {
  total: number
  currency: string
  currencies: string[]
  transactions: number
  revenue_per_visitor: number
  by_source: { source: string; revenue: number }[]
  timeseries: Point[]
  attributed_revenue_share: number | null
  attribution_model: string
}
export interface ProjectCreated {
  id: string
  name: string
  domain: string
  read_key: string
  write_key: string
  management_key: string
}
export interface Overview {
  visitors: number
  pageviews: number
  sessions: number
  bounce_rate: number
  avg_session_seconds: number
  events: number
  revenue: number
  revenue_currency: string
  revenue_currencies: string[]
}
export interface Point {
  t: string
  value: number
}
export interface DataSummary {
  project_id: string
  events: number
  notes: number
  funnels: number
  revenue_events: number
  first_event_at: string | null
  last_event_at: string | null
  top_events: { name: string; count: number }[]
}
export interface BreakdownRow {
  value: string
  visitors: number
  pageviews: number
  events: number
  revenue: number
}
export interface Anomaly {
  date: string
  metric: string
  value: number
  expected: number
  z_score: number
  direction: string
}
export interface AskResult {
  answer: string
  data: Record<string, unknown>[]
  chart: { type: string; x_key: string; y_key: string; title: string } | null
  sql_hint?: string
  validation?: { confidence?: number; truncated?: boolean }
  planner?: string
  coverage_notes?: string[]
  based_on?: { events: number; event_names: string[]; date_range: { from: string; to: string } }
}
export interface HealthCheck {
  key: string
  label: string
  status: 'ok' | 'warning' | 'missing'
  detail: string
}
export interface IntegrationHealth {
  project_id: string
  checks: HealthCheck[]
  missing: string[]
}
export interface FunnelStepReport {
  step: { kind: string; value: string }
  visitors: number
  conversion_from_start: number
  conversion_from_prev: number
}
export interface FunnelSegment {
  value: string
  visitors: number
  overall_conversion: number
  steps: FunnelStepReport[]
}
export interface FunnelReport {
  name: string
  overall_conversion: number
  steps: FunnelStepReport[]
  segments?: FunnelSegment[]
  segment_by?: string
}
export interface AlertChannel {
  id: string
  kind: string
  target: string
  enabled: boolean
  created_at: string
}
export interface AlertRule {
  id: string
  name: string
  metric: string
  direction: string
  min_z: number
  cooldown_hours: number
  enabled: boolean
  created_at: string
}
export interface AlertDelivery {
  id: string
  channel_id: string
  rule_id: string
  anomaly_key: string
  status: string
  detail: string
  created_at: string
}

export const api = {
  createProject: (name: string, domain: string, token = '') =>
    req<ProjectCreated>('/api/v1/projects', {
      method: 'POST',
      headers: token ? { 'X-Provisioning-Token': token } : {},
      body: JSON.stringify({ name, domain }),
    }),
  verifyManagement: async (projectId: string, key: string) => {
    const response = await fetch(`${BASE}/api/v1/projects/${projectId}/management`, {
      headers: { 'X-Management-Key': key },
    })
    if (!response.ok) throw new Error('Management key is invalid or belongs to another project.')
  },
  compare: (q: string) => req<Comparison>(`/api/v1/query/compare?${q}`),
  me: (key?: string) =>
    req<{ project_id: string; name: string; domain: string }>(
      '/api/v1/projects/me',
      key ? { headers: { 'X-Read-Key': key } } : {},
    ),
  listKeys: () =>
    reqManage<{ id: string; name: string; prefix: string; scopes: string; revoked: boolean }[]>(
      '/api/v1/keys',
    ),
  issueKey: (name: string, kind: 'read' | 'tracking' | 'management') =>
    reqManage<{ key: string }>('/api/v1/keys', {
      method: 'POST',
      body: JSON.stringify({ name, kind }),
    }),
  revokeKey: (id: string) => reqManage('/api/v1/keys/' + id, { method: 'DELETE' }),
  overview: (q: string) => req<Overview>(`/api/v1/query/overview?${q}`),
  timeseries: (q: string, metric: string, interval = 'day') =>
    req<Point[]>(`/api/v1/query/timeseries?${q}&metric=${metric}&interval=${interval}`),
  breakdown: (q: string, dimension: string, limit = 10) =>
    req<BreakdownRow[]>(`/api/v1/query/breakdown?${q}&dimension=${dimension}&limit=${limit}`),
  realtime: () =>
    req<{
      visitors: number
      pageviews: number
      events: number
      top_pages: { path: string; views: number }[]
    }>('/api/v1/query/realtime'),
  revenue: (q: string, currency?: string) =>
    req<RevenueReport>(`/api/v1/query/revenue?${q}${currency ? `&currency=${currency}` : ''}`),
  anomalies: (q: string) => req<Anomaly[]>(`/api/v1/query/anomalies?${q}`),
  mcpUsage: (q: string) =>
    req<{
      total_tool_calls: number
      by_tool: { tool: string; calls: number; error_rate: number; avg_ms: number }[]
      questions_asked: number
      recent_questions: string[]
    }>(`/api/v1/query/mcp-usage?${q}`),
  funnels: () =>
    req<{ id: string; name: string; steps: { kind: string; value: string }[] }[]>(
      '/api/v1/funnels',
    ),
  createFunnel: (name: string, steps: { kind: string; value: string }[]) =>
    reqManage<{ id: string }>('/api/v1/funnels', {
      method: 'POST',
      body: JSON.stringify({ name, steps }),
    }),
  funnelReport: (id: string, q: string, segmentBy?: string) =>
    req<FunnelReport>(
      `/api/v1/funnels/${id}/report?${q}${segmentBy ? `&segment_by=${segmentBy}` : ''}`,
    ),
  ask: (question: string, q: string) =>
    req<AskResult>('/api/v1/ask', {
      method: 'POST',
      body: JSON.stringify({ question, ...Object.fromEntries(new URLSearchParams(q)) }),
    }),
  notes: (projectId: string) =>
    req<{ id: string; text: string; at: string }[]>(`/api/v1/projects/${projectId}/notes`),
  addNote: (projectId: string, text: string) =>
    reqManage(`/api/v1/projects/${projectId}/notes`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  alertChannels: () => req<AlertChannel[]>('/api/v1/alerts/channels'),
  addAlertChannel: (kind: string, target: string) =>
    reqManage<AlertChannel>('/api/v1/alerts/channels', {
      method: 'POST',
      body: JSON.stringify({ kind, target }),
    }),
  deleteAlertChannel: (id: string) =>
    reqManage(`/api/v1/alerts/channels/${id}`, { method: 'DELETE' }),
  testAlertChannel: (id: string) =>
    reqManage<{ ok: boolean; detail: string }>(`/api/v1/alerts/channels/${id}/test`, {
      method: 'POST',
    }),
  alertRules: () => req<AlertRule[]>('/api/v1/alerts/rules'),
  addAlertRule: (rule: {
    name: string
    metric: string
    direction: string
    min_z: number
    cooldown_hours: number
  }) =>
    reqManage<AlertRule>('/api/v1/alerts/rules', { method: 'POST', body: JSON.stringify(rule) }),
  deleteAlertRule: (id: string) => reqManage(`/api/v1/alerts/rules/${id}`, { method: 'DELETE' }),
  alertDeliveries: () => req<AlertDelivery[]>('/api/v1/alerts/deliveries'),
  runAlertCheck: () =>
    reqManage<{ sent: number; skipped: number; failed: number }>('/api/v1/alerts/check', {
      method: 'POST',
    }),
  digestSettings: () =>
    req<{
      project_id: string
      enabled: boolean
      weekday: number
      hour_utc: number
      last_sent_at: string | null
    }>('/api/v1/digest/settings'),
  saveDigestSettings: (s: { enabled: boolean; weekday: number; hour_utc: number }) =>
    reqManage('/api/v1/digest/settings', { method: 'PUT', body: JSON.stringify(s) }),
  digestPreview: () =>
    req<{ subject: string; body: string }>('/api/v1/digest/preview', { method: 'POST' }),
  sendDigestNow: () =>
    reqManage<{ sent: number; failed: number }>('/api/v1/digest/send', { method: 'POST' }),
  dataSummary: (projectId: string) =>
    req<DataSummary>(`/api/v1/projects/${projectId}/data/summary`),
  deleteAllData: (projectId: string) =>
    reqManage<{ ok: boolean; deleted: Record<string, number> }>(
      `/api/v1/projects/${projectId}/data`,
      { method: 'DELETE' },
    ),
  integrationHealth: (projectId: string) =>
    req<IntegrationHealth>(`/api/v1/projects/${projectId}/data/health`),
}
