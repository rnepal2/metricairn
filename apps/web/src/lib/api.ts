/** Typed client for the AgentLens API. Read key lives in localStorage after login. */

const BASE = '';

export function getReadKey(): string | null {
  return localStorage.getItem('agentlens_read_key');
}

export function setReadKey(key: string) {
  localStorage.setItem('agentlens_read_key', key);
}

export function clearReadKey() {
  localStorage.removeItem('agentlens_read_key');
}

/** Write key is optional in the dashboard — needed only for managing alert
 *  channels/rules. Stored alongside the read key, never sent otherwise. */
export function getWriteKey(): string | null {
  return localStorage.getItem('agentlens_write_key');
}

export function setWriteKey(key: string) {
  localStorage.setItem('agentlens_write_key', key);
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const key = getReadKey();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(key ? { 'X-Read-Key': key } : {}), ...(init.headers || {}) },
  });
  if (res.status === 401 || res.status === 403) {
    clearReadKey();
    throw new Error('Invalid API key — please log in again.');
  }
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

/** Same as req() but authenticates with the write key (for alert management). */
async function reqWrite<T>(path: string, init: RequestInit = {}): Promise<T> {
  const key = getWriteKey();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(key ? { 'X-Write-Key': key } : {}), ...(init.headers || {}) },
  });
  if (res.status === 401 || res.status === 403) {
    throw new Error('Invalid write key — check it in Settings.');
  }
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export interface Overview {
  visitors: number; pageviews: number; sessions: number; bounce_rate: number;
  avg_session_seconds: number; events: number; revenue: number; revenue_currency: string;
}
export interface Point { t: string; value: number }
export interface BreakdownRow { value: string; visitors: number; pageviews: number; revenue: number }
export interface Anomaly { date: string; metric: string; value: number; expected: number; z_score: number; direction: string }
export interface AskResult { answer: string; data: Record<string, unknown>[]; chart: { type: string; x_key: string; y_key: string; title: string } | null }
export interface AlertChannel { id: string; kind: string; target: string; enabled: boolean; created_at: string }
export interface AlertRule { id: string; name: string; metric: string; direction: string; min_z: number; cooldown_hours: number; enabled: boolean; created_at: string }
export interface AlertDelivery { id: string; channel_id: string; rule_id: string; anomaly_key: string; status: string; detail: string; created_at: string }

export const api = {
  me: () => req<{ project_id: string; name: string; domain: string }>('/api/v1/projects/me'),
  overview: (q: string) => req<Overview>(`/api/v1/query/overview?${q}`),
  timeseries: (q: string, metric: string, interval = 'day') =>
    req<Point[]>(`/api/v1/query/timeseries?${q}&metric=${metric}&interval=${interval}`),
  breakdown: (q: string, dimension: string, limit = 10) =>
    req<BreakdownRow[]>(`/api/v1/query/breakdown?${q}&dimension=${dimension}&limit=${limit}`),
  realtime: () => req<{ visitors: number; pageviews: number; events: number; top_pages: { path: string; views: number }[] }>('/api/v1/query/realtime'),
  revenue: (q: string) => req<{ total: number; currency: string; transactions: number; revenue_per_visitor: number; by_source: { source: string; revenue: number }[]; timeseries: Point[] }>(`/api/v1/query/revenue?${q}`),
  anomalies: (q: string) => req<Anomaly[]>(`/api/v1/query/anomalies?${q}`),
  mcpUsage: (q: string) => req<{ total_tool_calls: number; by_tool: { tool: string; calls: number; error_rate: number; avg_ms: number }[]; questions_asked: number; recent_questions: string[] }>(`/api/v1/query/mcp-usage?${q}`),
  funnels: () => req<{ id: string; name: string; steps: { kind: string; value: string }[] }[]>('/api/v1/funnels'),
  createFunnel: (name: string, steps: { kind: string; value: string }[]) =>
    req<{ id: string }>('/api/v1/funnels', { method: 'POST', body: JSON.stringify({ name, steps }) }),
  funnelReport: (id: string, q: string) =>
    req<{ name: string; overall_conversion: number; steps: { step: { kind: string; value: string }; visitors: number; conversion_from_start: number; conversion_from_prev: number }[] }>(`/api/v1/funnels/${id}/report?${q}`),
  ask: (question: string, q: string) =>
    req<AskResult>('/api/v1/ask', { method: 'POST', body: JSON.stringify({ question, ...Object.fromEntries(new URLSearchParams(q)) }) }),
  notes: (projectId: string) => req<{ id: string; text: string; at: string }[]>(`/api/v1/projects/${projectId}/notes`),
  addNote: (projectId: string, text: string) =>
    req(`/api/v1/projects/${projectId}/notes`, { method: 'POST', body: JSON.stringify({ text }) }),
  alertChannels: () => req<AlertChannel[]>('/api/v1/alerts/channels'),
  addAlertChannel: (kind: string, target: string) =>
    reqWrite<AlertChannel>('/api/v1/alerts/channels', { method: 'POST', body: JSON.stringify({ kind, target }) }),
  deleteAlertChannel: (id: string) =>
    reqWrite(`/api/v1/alerts/channels/${id}`, { method: 'DELETE' }),
  testAlertChannel: (id: string) =>
    reqWrite<{ ok: boolean; detail: string }>(`/api/v1/alerts/channels/${id}/test`, { method: 'POST' }),
  alertRules: () => req<AlertRule[]>('/api/v1/alerts/rules'),
  addAlertRule: (rule: { name: string; metric: string; direction: string; min_z: number; cooldown_hours: number }) =>
    reqWrite<AlertRule>('/api/v1/alerts/rules', { method: 'POST', body: JSON.stringify(rule) }),
  deleteAlertRule: (id: string) =>
    reqWrite(`/api/v1/alerts/rules/${id}`, { method: 'DELETE' }),
  alertDeliveries: () => req<AlertDelivery[]>('/api/v1/alerts/deliveries'),
  runAlertCheck: () =>
    reqWrite<{ sent: number; skipped: number; failed: number }>('/api/v1/alerts/check', { method: 'POST' }),
  digestSettings: () => req<{ project_id: string; enabled: boolean; weekday: number; hour_utc: number; last_sent_at: string | null }>('/api/v1/digest/settings'),
  saveDigestSettings: (s: { enabled: boolean; weekday: number; hour_utc: number }) =>
    reqWrite('/api/v1/digest/settings', { method: 'PUT', body: JSON.stringify(s) }),
  digestPreview: () => req<{ subject: string; body: string }>('/api/v1/digest/preview', { method: 'POST' }),
  sendDigestNow: () => reqWrite<{ sent: number; failed: number }>('/api/v1/digest/send', { method: 'POST' }),
};
