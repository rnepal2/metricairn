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
  const rev = useFetch(() => api.revenue(query), [query])

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {rev.loading ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24" />)
        ) : rev.data ? (
          <>
            <Card><CardContent className="pt-5">
              <div className="flex items-center justify-between"><div className="text-xs font-medium text-slate-500">Total revenue</div><DollarSign className="h-4 w-4 text-slate-400" /></div>
              <div className="mt-1 text-2xl font-bold">{fmtMoney(rev.data.total, rev.data.currency)}</div>
            </CardContent></Card>
            <Card><CardContent className="pt-5">
              <div className="flex items-center justify-between"><div className="text-xs font-medium text-slate-500">Transactions</div><Receipt className="h-4 w-4 text-slate-400" /></div>
              <div className="mt-1 text-2xl font-bold">{fmtNum(rev.data.transactions)}</div>
            </CardContent></Card>
            <Card><CardContent className="pt-5">
              <div className="flex items-center justify-between"><div className="text-xs font-medium text-slate-500">Revenue / visitor</div><UserCheck className="h-4 w-4 text-slate-400" /></div>
              <div className="mt-1 text-2xl font-bold">{fmtMoney(rev.data.revenue_per_visitor, rev.data.currency)}</div>
            </CardContent></Card>
          </>
        ) : null}
      </div>

      <Card>
        <CardHeader><CardTitle>Revenue over time</CardTitle></CardHeader>
        <CardContent>
          {rev.loading ? <Skeleton className="h-64" /> : <TimeseriesChart data={rev.data?.timeseries || []} />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Revenue by source</CardTitle></CardHeader>
        <CardContent>
          {rev.loading ? <Skeleton className="h-64" /> : (
            <BarListChart data={(rev.data?.by_source || []) as unknown as Record<string, unknown>[]} xKey="source" yKey="revenue" />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
