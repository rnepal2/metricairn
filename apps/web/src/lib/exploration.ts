import { req, reqManage } from './api'
export interface Plan {
  metric: 'pageviews' | 'events' | 'event_count'
  event_name?: string
  date_from?: string
  date_to?: string
  filters?: { field: string; values: string[] }[]
}
export interface InvestigationReport {
  metric_version: string
  evidence_id: string
  generated_at: string
  plan: Plan
  current: number
  previous: number
  change: number
  change_pct: number | null
  current_window: { from: string; to: string }
  previous_window: { from: string; to: string }
  segments: {
    dimension: string
    rows: { value: string; current: number; previous: number; change: number }[]
    other: { current: number; previous: number; change: number }
  }[]
  coverage: {
    period: string
    recorded_events: number
    identified_share: number | null
    last_event_at: string | null
  }[]
  notes: { text: string; at: string }[]
  caveats: string[]
  next_checks: string[]
}
export interface SavedInvestigation {
  id: string
  title: string
  status: 'observed' | 'investigating' | 'resolved' | 'dismissed'
  review_note: string
  created_at: string
  evidence_id: string
  evidence: InvestigationReport
}
export type SavedInvestigationSummary = Omit<SavedInvestigation, 'evidence'>
export interface Goal {
  id: string
  name: string
  event_name: string
}
export interface GoalReport extends Goal {
  eligible_visitors: number
  converted_visitors: number
  conversion_rate: number | null
  occurrences: number
  unidentified_occurrences: number
  definition: string
}
export interface RetentionReport {
  cohorts: {
    cohort: string
    size: number
    weeks: { week: number; visitors: number | null; rate: number | null }[]
  }[]
  notes: string[]
}
export const exploration = {
  investigate: (plan: Plan) =>
    req<InvestigationReport>('/api/v1/investigations/run', {
      method: 'POST',
      body: JSON.stringify(plan),
    }),
  investigations: () => req<SavedInvestigationSummary[]>('/api/v1/investigations'),
  investigation: (id: string) => req<SavedInvestigation>(`/api/v1/investigations/${id}`),
  save: (title: string, plan: Plan) =>
    reqManage<SavedInvestigation>('/api/v1/investigations', {
      method: 'POST',
      body: JSON.stringify({ title, plan }),
    }),
  review: (id: string, status: SavedInvestigation['status'], note: string) =>
    reqManage<SavedInvestigation>(`/api/v1/investigations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, note }),
    }),
  goals: () => req<Goal[]>('/api/v1/goals'),
  goalReport: (id: string, query: string) => req<GoalReport>(`/api/v1/goals/${id}/report?${query}`),
  createGoal: (name: string, event_name: string) =>
    reqManage<Goal>('/api/v1/goals', {
      method: 'POST',
      body: JSON.stringify({ name, event_name }),
    }),
  deleteGoal: (id: string) => reqManage(`/api/v1/goals/${id}`, { method: 'DELETE' }),
  retention: (query: string, event: string) =>
    req<RetentionReport>(
      `/api/v1/query/retention?${query}${event ? `&event_name=${encodeURIComponent(event)}` : ''}`,
    ),
}
export function downloadJson(value: unknown, filename: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
