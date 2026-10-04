import { ExportButton } from '@/components/ExportButton'
import { FetchError } from '@/components/FetchError'
import { api, type BreakdownRow } from '@/lib/api'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtNum } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export function Events() {
  const { query } = useApp()
  const ev = useFetch<BreakdownRow[]>(() => api.breakdown(query, 'event', 50), [query])

  return (
    <Card>
      <ExportButton rows={ev.data || []} name="metricairn-events" />
      <FetchError error={ev.error} retry={ev.reload} />
      <CardHeader>
        <CardTitle>Custom events</CardTitle>
      </CardHeader>
      <CardContent>
        {ev.loading ? (
          <Skeleton className="h-64" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead className="text-right">Visitors</TableHead>
                <TableHead className="text-right">Occurrences</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(ev.data || []).map((r) => (
                <TableRow key={r.value}>
                  <TableCell className="font-mono text-xs">{r.value}</TableCell>
                  <TableCell className="text-right">{fmtNum(r.visitors)}</TableCell>
                  <TableCell className="text-right">{fmtNum(r.events)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {!ev.loading && (ev.data || []).length === 0 && (
          <p className="py-8 text-center text-sm text-slate-400">
            No custom events yet. Track them with{' '}
            <code className="rounded bg-slate-100 px-1 font-mono text-xs">
              metricairn.event('signup')
            </code>{' '}
            — see Settings for the snippet.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
