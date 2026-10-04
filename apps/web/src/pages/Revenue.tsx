import { useState } from 'react'
import { ExportButton } from '@/components/ExportButton'
import { FetchError } from '@/components/FetchError'
import { DollarSign, Receipt, UserCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtNum, fmtMoney } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/badge'
import { TimeseriesChart, BarListChart } from '@/components/charts/charts'

export function Revenue() {
  const { query } = useApp()
  const [currency, setCurrency] = useState('')
  const rev = useFetch(() => api.revenue(query, currency || undefined), [query, currency])

  return (
    <div className="space-y-4">
      <FetchError error={rev.error} retry={rev.reload} />
      {rev.data && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            Gross recorded payments · {rev.data.currency} · no FX conversion
          </p>
          <label className="flex items-center gap-2 text-sm">
            Currency
            <select
              className="rounded border bg-white p-2"
              value={currency || rev.data.currency}
              onChange={(e) => setCurrency(e.target.value)}
            >
              {Array.from(new Set([...rev.data.currencies, rev.data.currency])).map((code) => (
                <option key={code}>{code}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {rev.loading ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24" />)
        ) : rev.data ? (
          <>
            <Card>
              <CardContent className="pt-5">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-medium text-slate-500">Total revenue</div>
                  <DollarSign className="h-4 w-4 text-slate-400" />
                </div>
                <div className="mt-1 text-2xl font-bold">
                  {fmtMoney(rev.data.total, rev.data.currency)}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-5">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-medium text-slate-500">Transactions</div>
                  <Receipt className="h-4 w-4 text-slate-400" />
                </div>
                <div className="mt-1 text-2xl font-bold">{fmtNum(rev.data.transactions)}</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-5">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-medium text-slate-500">Revenue / visitor</div>
                  <UserCheck className="h-4 w-4 text-slate-400" />
                </div>
                <div className="mt-1 text-2xl font-bold">
                  {fmtMoney(rev.data.revenue_per_visitor, rev.data.currency)}
                </div>
              </CardContent>
            </Card>
          </>
        ) : null}
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Revenue over time</CardTitle>
          <ExportButton rows={rev.data?.timeseries || []} name="metricairn-revenue" />
        </CardHeader>
        <CardContent>
          {rev.loading ? (
            <Skeleton className="h-64" />
          ) : (
            <TimeseriesChart data={rev.data?.timeseries || []} />
          )}
        </CardContent>
      </Card>

      {rev.data && (
        <p className="rounded border bg-slate-50 p-3 text-xs text-slate-600">
          Campaign/referrer tags are present on{' '}
          {rev.data.attributed_revenue_share === null
            ? 'no'
            : `${Math.round(rev.data.attributed_revenue_share * 100)}% of`}{' '}
          recorded revenue. Unmatched server payments are shown as unattributed; direct browser
          visits may have no campaign tags. Attribution is descriptive and does not measure
          incremental marketing lift.
        </p>
      )}
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Revenue by source</CardTitle>
          <ExportButton rows={rev.data?.by_source || []} name="metricairn-revenue-sources" />
        </CardHeader>
        <CardContent>
          {rev.loading ? (
            <Skeleton className="h-64" />
          ) : (
            <BarListChart
              data={(rev.data?.by_source || []) as unknown as Record<string, unknown>[]}
              xKey="source"
              yKey="revenue"
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
