import { useEffect } from 'react'
import { Activity } from 'lucide-react'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton, Badge } from '@/components/ui/badge'
import { fmtNum } from '@/lib/utils'

export function Realtime() {
  const rt = useFetch(() => api.realtime(), [])

  useEffect(() => {
    const t = setInterval(() => rt.reload(), 10000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {rt.loading && !rt.data ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24" />)
        ) : rt.data ? (
          <>
            <Card><CardContent className="pt-5">
              <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" /></span>
                Visitors now
              </div>
              <div className="mt-1 text-2xl font-bold">{fmtNum(rt.data.visitors)}</div>
            </CardContent></Card>
            <Card><CardContent className="pt-5">
              <div className="text-xs font-medium text-slate-500">Pageviews (30 min)</div>
              <div className="mt-1 text-2xl font-bold">{fmtNum(rt.data.pageviews)}</div>
            </CardContent></Card>
            <Card><CardContent className="pt-5">
              <div className="text-xs font-medium text-slate-500">Events (30 min)</div>
              <div className="mt-1 text-2xl font-bold">{fmtNum(rt.data.events)}</div>
            </CardContent></Card>
          </>
        ) : null}
      </div>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Activity className="h-4 w-4" /> Active pages</CardTitle></CardHeader>
        <CardContent>
          {rt.loading && !rt.data ? <Skeleton className="h-40" /> : (
            <div className="space-y-2">
              {(rt.data?.top_pages || []).map((p) => (
                <div key={p.path} className="flex items-center justify-between text-sm">
                  <span className="truncate font-mono text-xs">{p.path}</span>
                  <Badge variant="secondary">{p.views} views</Badge>
                </div>
              ))}
              {(rt.data?.top_pages || []).length === 0 && <p className="text-xs text-slate-400">No activity in the last 30 minutes.</p>}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
