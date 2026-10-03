import { TrendingUp, TrendingDown, Bell } from 'lucide-react'
import { api, type Anomaly } from '@/lib/api'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtNum } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton, Badge } from '@/components/ui/badge'

export function Alerts() {
  const { query } = useApp()
  const an = useFetch<Anomaly[]>(() => api.anomalies(query), [query])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Bell className="h-4 w-4" /> Anomaly alerts</CardTitle>
      </CardHeader>
      <CardContent>
        {an.loading ? <Skeleton className="h-48" /> : (an.data || []).length === 0 ? (
          <div className="py-10 text-center">
            <p className="text-sm font-medium">All quiet.</p>
            <p className="mt-1 text-xs text-slate-500">No statistically significant spikes or dips in pageviews or revenue for this period. AgentLens checks daily with z-score detection.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {(an.data || []).map((a, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border border-slate-200 p-3">
                <div className="flex items-center gap-3">
                  {a.direction === 'spike' ? <TrendingUp className="h-4 w-4 text-emerald-600" /> : <TrendingDown className="h-4 w-4 text-red-600" />}
                  <div>
                    <div className="text-sm font-medium capitalize">{a.metric} {a.direction} — {a.date}</div>
                    <div className="text-xs text-slate-500">
                      {fmtNum(a.value)} observed vs ~{fmtNum(a.expected)} expected (z = {a.z_score})
                    </div>
                  </div>
                </div>
                <Badge variant={a.direction === 'spike' ? 'success' : 'danger'}>{a.direction}</Badge>
              </div>
            ))}
          </div>
        )}
        <p className="mt-4 text-[11px] text-slate-400">
          Tip: ask your AI agent "any anomalies this month?" — the MCP server exposes the same detection.
        </p>
      </CardContent>
    </Card>
  )
}
