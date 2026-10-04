import { useState } from 'react'
import { Search, ArrowRight } from 'lucide-react'
import { BASE, api, setReadKey, type Point, type FunnelReport } from '@/lib/api'
import type { InvestigationReport } from '@/lib/exploration'
import { useApp, type PageKey } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { DEMO_READ_KEY } from '@/lib/demo'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { TimeseriesChart } from '@/components/charts/charts'
import { FetchError } from '@/components/FetchError'
import { fmtNum, fmtPct } from '@/lib/utils'

async function demoRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'X-Read-Key': DEMO_READ_KEY, 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  if (!response.ok)
    throw new Error(
      'Billwise demo data is unavailable. Run scripts/seed_billwise.py on your local API, then retry.',
    )
  return response.json()
}
export function Demo() {
  const { setPage, setProject } = useApp()
  const [entering, setEntering] = useState(false)
  const [error, setError] = useState('')
  const demo = useFetch(async () => {
    const date_to = new Date().toISOString()
    const date_from = new Date(Date.now() - 7 * 864e5).toISOString()
    const range = new URLSearchParams({
      date_from: new Date(Date.now() - 60 * 864e5).toISOString(),
      date_to,
    }).toString()
    const [investigation, traffic, funnels] = await Promise.all([
      demoRequest<InvestigationReport>('/api/v1/investigations/run', {
        metric: 'pageviews',
        date_from,
        date_to,
      }),
      demoRequest<Point[]>(`/api/v1/query/timeseries?metric=visitors&${range}`),
      demoRequest<{ id: string }[]>('/api/v1/funnels'),
    ])
    const funnel = funnels[0]
      ? await demoRequest<FunnelReport>(`/api/v1/funnels/${funnels[0].id}/report?${range}`)
      : null
    return { investigation, traffic, funnel }
  }, [])
  async function open(target: PageKey = 'investigations') {
    setEntering(true)
    setError('')
    try {
      const project = await api.me(DEMO_READ_KEY)
      setReadKey(DEMO_READ_KEY)
      setProject(project)
      setPage(target)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Demo unavailable')
    } finally {
      setEntering(false)
    }
  }
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <span className="flex items-center gap-2 font-bold">
            <Search /> Metricairn{' '}
            <span className="text-xs font-normal text-slate-500">Simulated product story</span>
          </span>
          <Button variant="outline" onClick={() => setPage('overview')}>
            Back to your project
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl space-y-8 p-6 py-12">
        <div className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-teal-700">
            Maya Chen · Billwise · fictional founder scenario
          </p>
          <h1 className="max-w-3xl text-4xl font-bold leading-tight">
            How Maya investigates growth at Billwise.
          </h1>
          <p className="max-w-2xl text-lg text-slate-600">
            Maya Chen runs Billwise, a one-person invoicing app for freelancers. On Monday morning,
            she wants to know what changed in traffic, whether visitors are signing up, and where to
            look next. Follow the evidence she can inspect from her dashboard or AI agent.
          </p>
          <p className="max-w-2xl text-sm text-slate-500">
            Maya and Billwise are fictional. The walkthrough uses 60 days of simulated events;
            displayed results are calculated by the API. Core analytics needs no AI key.
          </p>
          <Button onClick={() => void open()} disabled={entering}>
            {entering ? 'Connecting…' : 'Explore dashboard'} <ArrowRight />
          </Button>
          <FetchError error={error} />
        </div>
        <FetchError error={demo.error} retry={demo.reload} />
        {demo.loading && <p role="status">Querying the simulated dataset…</p>}
        {demo.data && (
          <>
            <Card>
              <CardHeader>
                <CardTitle>1. Start with the recorded change</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-3xl font-semibold">
                  {fmtNum(demo.data.investigation.current)} pageviews{' '}
                  <span className="text-base font-normal text-slate-500">
                    vs {fmtNum(demo.data.investigation.previous)} in the preceding 7 days
                  </span>
                </p>
                <p className="text-xs text-slate-500">
                  Exact UTC window: {demo.data.investigation.current_window.from} →{' '}
                  {demo.data.investigation.current_window.to}
                </p>
                <TimeseriesChart data={demo.data.traffic} />
                <p className="text-xs text-slate-500">
                  Visitor trend · 60 days. Daily distinct visitors should not be summed into period
                  uniques.
                </p>
                <p className="border-l-2 border-teal-200 pl-3 text-sm text-slate-600">
                  Maya’s first question: “What changed in pageviews over the last week, and is
                  collection still working?”
                </p>
              </CardContent>
            </Card>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>2. Inspect where it changed</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {demo.data.investigation.segments[0].rows.map((row) => (
                    <div key={row.value} className="flex justify-between text-sm">
                      <span>{row.value}</span>
                      <span>
                        {row.change > 0 ? '+' : ''}
                        {fmtNum(row.change)} pageviews
                      </span>
                    </div>
                  ))}
                  <p className="text-xs text-slate-500">
                    Event-stamped source segments. Their changes and the remaining tail reconcile to
                    the total; they do not prove cause.
                  </p>
                  <p className="text-sm text-slate-600">
                    Maya uses the largest changed sources to choose what to investigate, then checks
                    campaign-tagged signup events before deciding what content to write next.
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>3. Check the conversion path</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {demo.data.funnel?.steps.map((step, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span>{step.step.value}</span>
                      <span>
                        {fmtNum(step.visitors)} · {fmtPct(step.conversion_from_start)}
                      </span>
                    </div>
                  ))}
                  <p className="text-xs text-slate-500">
                    Ordered, visitor-based funnel · 60 days. Goals and retention are also available
                    in the dashboard.
                  </p>
                  <p className="text-sm text-slate-600">
                    She checks the signup path, measures the Account signup goal, and inspects
                    returning visitor cohorts rather than judging growth from traffic alone.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      disabled={entering}
                      onClick={() => void open('goals')}
                    >
                      Inspect signup goal
                    </Button>
                    <Button
                      variant="outline"
                      disabled={entering}
                      onClick={() => void open('retention')}
                    >
                      Inspect retention
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader>
                <CardTitle>4. Keep uncertainty visible</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-slate-600">
                {demo.data.investigation.next_checks.map((check) => (
                  <p key={check}>{check}</p>
                ))}
                <p className="text-xs text-slate-500">
                  Maya can export the evidence, or save it with a private management key and record
                  her next check. Review notes are stored separately from the immutable report.
                </p>
              </CardContent>
            </Card>
          </>
        )}
        <p className="rounded-lg border bg-white p-4 text-sm text-slate-600">
          Maya Chen and Billwise are fictional. This demonstrates the workflow, not verified
          customer savings or causal impact. All displayed results are computed from seeded,
          simulated events.
        </p>
      </main>
    </div>
  )
}
