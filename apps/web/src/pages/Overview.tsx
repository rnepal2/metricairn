import { ExportButton } from '@/components/ExportButton'
import { FetchError } from '@/components/FetchError'
import { Users, Eye, MousePointerClick, DollarSign } from 'lucide-react'
import {
  api,
  type BreakdownRow,
  type Overview as OverviewT,
  type Point,
  type IntegrationHealth,
} from '@/lib/api'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtNum, fmtPct, fmtMoney } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/badge'
import { TimeseriesChart, BarListChart } from '@/components/charts/charts'

function Kpi({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: typeof Users
  label: string
  value: string
  sub?: string
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between">
          <div className="text-xs font-medium text-slate-500">{label}</div>
          <Icon className="h-4 w-4 text-slate-400" />
        </div>
        <div className="mt-1 text-2xl font-bold">{value}</div>
        {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
      </CardContent>
    </Card>
  )
}

function BreakdownCard({
  title,
  rows,
  loading,
}: {
  title: string
  rows: BreakdownRow[] | null
  loading: boolean
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>{title}</CardTitle>
        <ExportButton
          rows={rows || []}
          name={`metricairn-${title.toLowerCase().replaceAll(' ', '-')}`}
        />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-40" />
        ) : (
          <div className="space-y-2">
            {(rows || []).slice(0, 8).map((r) => (
              <div key={r.value} className="flex items-center justify-between text-sm">
                <span className="max-w-[60%] truncate font-mono text-xs" title={r.value}>
                  {r.value}
                </span>
                <span className="text-xs text-slate-500">{fmtNum(r.visitors)} visitors</span>
              </div>
            ))}
            {(!rows || rows.length === 0) && <p className="text-xs text-slate-400">No data yet.</p>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function Overview() {
  const { query, project, setPage } = useApp()
  const comparison = useFetch(() => api.compare(query), [query])
  const ov = useFetch<OverviewT>(() => api.overview(query), [query])
  const ts = useFetch<Point[]>(() => api.timeseries(query, 'visitors'), [query])
  const pages = useFetch<BreakdownRow[]>(() => api.breakdown(query, 'path'), [query])
  const refs = useFetch<BreakdownRow[]>(() => api.breakdown(query, 'utm_source'), [query])
  const devices = useFetch<BreakdownRow[]>(() => api.breakdown(query, 'device'), [query])
  const countries = useFetch<BreakdownRow[]>(() => api.breakdown(query, 'country'), [query])
  const health = useFetch<IntegrationHealth>(
    () =>
      project
        ? api.integrationHealth(project.project_id)
        : Promise.resolve(null as unknown as IntegrationHealth),
    [project?.project_id],
  )

  return (
    <div className="space-y-4">
      <FetchError error={ov.error} retry={ov.reload} />
      <FetchError error={ts.error} retry={ts.reload} />
      <FetchError error={pages.error} retry={pages.reload} />
      <FetchError error={refs.error} retry={refs.reload} />
      <FetchError error={devices.error} retry={devices.reload} />
      <FetchError error={countries.error} retry={countries.reload} />
      <FetchError error={health.error} retry={health.reload} />
      <FetchError error={comparison.error} retry={comparison.reload} />
      {comparison.data && (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle>Compared with the previous period</CardTitle>
            <ExportButton rows={comparison.data.metrics} name="metricairn-period-comparison" />
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b text-xs text-slate-500">
                    <th className="py-2">Metric</th>
                    <th>Current</th>
                    <th>Previous</th>
                    <th>Change</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.data.metrics
                    .filter((row) =>
                      [
                        'visitors',
                        'pageviews',
                        'events',
                        ...(ov.data?.revenue_currencies.length ? ['revenue'] : []),
                      ].includes(row.metric),
                    )
                    .map((row) => (
                      <tr key={row.metric} className="border-b last:border-0">
                        <th className="py-2 font-normal capitalize">{row.metric}</th>
                        <td>
                          {row.metric === 'revenue'
                            ? fmtMoney(row.current, comparison.data!.currency)
                            : fmtNum(row.current)}
                        </td>
                        <td>
                          {row.metric === 'revenue'
                            ? fmtMoney(row.previous, comparison.data!.currency)
                            : fmtNum(row.previous)}
                        </td>
                        <td>
                          {row.change_pct === null
                            ? 'No baseline'
                            : `${row.change_pct > 0 ? '+' : ''}${row.change_pct}%`}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Equal-length rolling UTC windows. Revenue is gross recorded payments in{' '}
              {comparison.data.currency}. Changes are descriptive, not causal or significance tests.
            </p>
          </CardContent>
        </Card>
      )}
      {ov.data && ov.data.revenue_currencies?.length > 1 && (
        <p className="rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          Multiple currencies received. Overview shows {ov.data.revenue_currency} only; choose a
          currency in Revenue. No FX conversion.
        </p>
      )}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {ov.loading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)
        ) : ov.data ? (
          <>
            <Kpi
              icon={Users}
              label="Visitors"
              value={fmtNum(ov.data.visitors)}
              sub={`${fmtNum(ov.data.sessions)} sessions`}
            />
            <Kpi
              icon={Eye}
              label="Pageviews"
              value={fmtNum(ov.data.pageviews)}
              sub={`${fmtPct(ov.data.bounce_rate)} bounce`}
            />
            <Kpi icon={MousePointerClick} label="Custom events" value={fmtNum(ov.data.events)} />
            <Kpi
              icon={DollarSign}
              label={ov.data.revenue_currencies.length ? 'Recorded revenue' : 'Sessions'}
              value={
                ov.data.revenue_currencies.length
                  ? fmtMoney(ov.data.revenue, ov.data.revenue_currency)
                  : fmtNum(ov.data.sessions)
              }
            />
          </>
        ) : null}
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Visitors over time</CardTitle>
          <ExportButton rows={ts.data || []} name="metricairn-visitors" />
        </CardHeader>
        <CardContent>
          {ts.loading ? <Skeleton className="h-64" /> : <TimeseriesChart data={ts.data || []} />}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BreakdownCard title="Top pages" rows={pages.data} loading={pages.loading} />
        <BreakdownCard title="Top sources" rows={refs.data} loading={refs.loading} />
        <BreakdownCard title="Devices" rows={devices.data} loading={devices.loading} />
        <BreakdownCard title="Countries" rows={countries.data} loading={countries.loading} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Sources by visitors</CardTitle>
        </CardHeader>
        <CardContent>
          {refs.loading ? (
            <Skeleton className="h-64" />
          ) : (
            <BarListChart
              data={(refs.data || []) as unknown as Record<string, unknown>[]}
              xKey="value"
              yKey="visitors"
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
