import { readJson, requestResponse } from './api'
import type { Goal, GoalReport, InvestigationReport, RetentionReport } from './exploration'

/** Public key for simulated Billwise data only. Never use for real customer data. */
export const DEMO_READ_KEY = 'alr_bw_demo_9f2k7q4x1m8z3d6v'
export const DEMO_PROMPT =
  'Investigate Billwise’s pageview change over the last seven days. Check coverage and source contributions. Then show signup occurrences by campaign, signup conversion, and weekly returning visitors. Cite the windows and definitions; separate observations from hypotheses.'
export const DEMO_STEPS = [
  'Traffic change',
  'Campaign signups',
  'Signup conversion',
  'Returning visitors',
] as const
export type DemoStep = 0 | 1 | 2 | 3
export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  result: unknown
}
export interface QueryReport {
  total: number
  rows: { value: string; count: number }[]
  truncated: boolean
  plan: { date_from: string; date_to: string }
  notes: string[]
}
export interface DemoResult {
  calls: ToolCall[]
  investigation?: InvestigationReport
  campaigns?: QueryReport
  goal?: GoalReport
  retention?: RetentionReport
  window: { date_from: string; date_to: string }
}
async function demoRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await requestResponse(path, {
    method: body ? 'POST' : 'GET',
    headers: { 'X-Read-Key': DEMO_READ_KEY, 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  if (response.status === 401 || response.status === 403)
    throw new Error(
      'Billwise demo data is unavailable. Run uv run python scripts/seed_billwise.py from the repository root with your local API running, then retry.',
    )
  return readJson<T>(response)
}
/** API-backed previews of MCP results. The browser does not run an MCP client. */
export async function loadDemoStep(step: DemoStep): Promise<DemoResult> {
  const end = new Date()
  const window = {
    date_from: new Date(end.getTime() - (step === 0 ? 7 : 60) * 864e5).toISOString(),
    date_to: end.toISOString(),
  }
  const query = new URLSearchParams(window).toString()
  if (step === 0) {
    const args = { metric: 'pageviews', ...window }
    const investigation = await demoRequest<InvestigationReport>('/api/v1/investigations/run', args)
    return {
      window,
      investigation,
      calls: [{ name: 'investigate_change', arguments: args, result: investigation }],
    }
  }
  if (step === 1) {
    const plan = {
      metric: 'event_count',
      event_name: 'signup',
      mode: 'breakdown',
      dimension: 'utm_campaign',
      limit: 10,
      ...window,
    }
    const campaigns = await demoRequest<QueryReport>('/api/v1/query/run', plan)
    return {
      window,
      campaigns,
      calls: [{ name: 'run_query', arguments: { plan }, result: campaigns }],
    }
  }
  if (step === 2) {
    const goals = await demoRequest<Goal[]>('/api/v1/goals')
    const signup = goals.find((goal) => goal.event_name === 'signup')
    if (!signup)
      throw new Error(
        'The Billwise signup goal is missing. Re-run scripts/seed_billwise.py for the simulated project, then retry.',
      )
    const goal = await demoRequest<GoalReport>(`/api/v1/goals/${signup.id}/report?${query}`)
    return {
      window,
      goal,
      calls: [
        { name: 'list_goals', arguments: {}, result: goals },
        { name: 'goal_report', arguments: { goal_id: signup.id, ...window }, result: goal },
      ],
    }
  }
  const retention = await demoRequest<RetentionReport>(`/api/v1/query/retention?${query}`)
  return {
    window,
    retention,
    calls: [{ name: 'retention_report', arguments: window, result: retention }],
  }
}
