import { useEffect, useState } from 'react'
import { Search, Download, Bookmark } from 'lucide-react'
import { getManagementKey } from '@/lib/api'
import { exploration, downloadJson, type Plan, type SavedInvestigation } from '@/lib/exploration'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtNum, fmtPct } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input, Label } from '@/components/ui/input'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { FetchError } from '@/components/FetchError'
import { ExportButton } from '@/components/ExportButton'

const selectClass = 'h-9 rounded-md border border-slate-200 bg-white px-3 text-sm'
export function Investigations() {
  const { query } = useApp()
  const [metric, setMetric] = useState<Plan['metric']>('pageviews')
  const [event, setEvent] = useState('signup')
  const [source, setSource] = useState('')
  const [applied, setApplied] = useState<Plan>({ metric: 'pageviews' })
  const [selected, setSelected] = useState<SavedInvestigation | null>(null)
  const [title, setTitle] = useState('Traffic change')
  const [status, setStatus] = useState<SavedInvestigation['status']>('observed')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const current = useFetch(
    () =>
      exploration.investigate({ ...applied, ...Object.fromEntries(new URLSearchParams(query)) }),
    [applied, query],
  )
  const history = useFetch(exploration.investigations, [])
  const report = selected?.evidence || current.data
  const canManage = !!getManagementKey()
  useEffect(() => {
    setSelected(null)
    setNotice('')
  }, [query, applied])
  async function action(fn: () => Promise<SavedInvestigation>, message = '') {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const saved = await fn()
      setSelected(saved)
      setStatus(saved.status)
      setNote(saved.review_note)
      setNotice(message)
      void history.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-6">
      <div className="max-w-3xl">
        <h2 className="text-2xl font-semibold tracking-tight">What changed—and where?</h2>
        <p className="mt-2 text-sm text-slate-500">
          Compare recorded activity with the preceding period, inspect the changed segments, and
          keep the evidence behind your decision.
        </p>
      </div>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          setApplied({
            metric,
            ...(metric === 'event_count' ? { event_name: event.trim() } : {}),
            filters: source.trim() ? [{ field: 'utm_source', values: [source.trim()] }] : [],
          })
        }}
      >
        <div>
          <Label htmlFor="investigation-metric">Metric</Label>
          <select
            id="investigation-metric"
            className={selectClass + ' block mt-1'}
            value={metric}
            onChange={(e) => setMetric(e.target.value as Plan['metric'])}
          >
            <option value="pageviews">Pageviews</option>
            <option value="events">Custom events</option>
            <option value="event_count">Specific event</option>
          </select>
        </div>
        {metric === 'event_count' && (
          <div>
            <Label htmlFor="investigation-event">Event name</Label>
            <Input
              id="investigation-event"
              required
              maxLength={200}
              value={event}
              onChange={(e) => setEvent(e.target.value)}
              className="mt-1 w-44"
            />
          </div>
        )}
        <div>
          <Label htmlFor="investigation-source">Source filter (optional)</Label>
          <Input
            id="investigation-source"
            placeholder="e.g. google"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="mt-1 w-44"
          />
        </div>
        <Button disabled={current.loading || busy}>
          <Search /> Investigate change
        </Button>
        {selected && (
          <Button type="button" variant="outline" onClick={() => setSelected(null)}>
            Return to current data
          </Button>
        )}
      </form>
      <FetchError error={error || (!selected ? current.error : '')} />
      {notice && (
        <p role="status" className="text-sm text-emerald-700">
          {notice}
        </p>
      )}
      {!selected && current.loading && (
        <p role="status" className="text-sm text-slate-500">
          Comparing periods and checking coverage…
        </p>
      )}
      {report && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-slate-500">
                {selected
                  ? `Saved evidence · ${selected.title}`
                  : report.plan.event_name || report.plan.metric}
              </p>
              <div className="mt-1 flex items-baseline gap-3">
                <strong className="text-4xl tracking-tight">{fmtNum(report.current)}</strong>
                <span className="text-sm text-slate-500">
                  vs {fmtNum(report.previous)} previously · {report.change > 0 ? '+' : ''}
                  {fmtNum(report.change)} (
                  {report.change_pct == null
                    ? 'no baseline'
                    : `${report.change_pct > 0 ? '+' : ''}${report.change_pct.toFixed(1)}%`}
                  )
                </span>
              </div>
              <p className="mt-2 text-xs text-slate-500 break-all">
                {report.current_window.from} → {report.current_window.to} · UTC
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => downloadJson(selected || report, 'metricairn-investigation.json')}
            >
              <Download /> Export evidence
            </Button>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {report.segments.map((segment) => (
              <Card key={segment.dimension}>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="text-sm">
                    {
                      (
                        {
                          utm_source: 'Traffic source',
                          device: 'Device',
                          browser: 'Browser',
                          path: 'Page path',
                        } as Record<string, string>
                      )[segment.dimension]
                    }
                  </CardTitle>
                  <ExportButton
                    rows={segment.rows}
                    name={`metricairn-change-${segment.dimension}`}
                  />
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-xs text-slate-500">
                        <th className="pb-2 text-left font-normal">Segment</th>
                        <th className="pb-2 text-right font-normal">Previous</th>
                        <th className="pb-2 text-right font-normal">Current</th>
                        <th className="pb-2 text-right font-normal">Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {segment.rows.map((row) => (
                        <tr key={row.value} className="border-b last:border-0">
                          <td
                            className="max-w-48 truncate py-2 font-mono text-xs"
                            title={row.value}
                          >
                            {row.value}
                          </td>
                          <td className="text-right text-slate-500">{fmtNum(row.previous)}</td>
                          <td className="text-right">{fmtNum(row.current)}</td>
                          <td className="text-right font-medium">
                            {row.change > 0 ? '+' : ''}
                            {fmtNum(row.change)}
                          </td>
                        </tr>
                      ))}
                      {(segment.other.current > 0 || segment.other.previous > 0) && (
                        <tr>
                          <td className="pt-2 text-xs text-slate-500">Remaining segments</td>
                          <td className="pt-2 text-right">{fmtNum(segment.other.previous)}</td>
                          <td className="pt-2 text-right">{fmtNum(segment.other.current)}</td>
                          <td className="pt-2 text-right">{fmtNum(segment.other.change)}</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                  {!segment.rows.length && (
                    <p className="py-6 text-sm text-slate-500">No matching activity recorded.</p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Before interpreting the change</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-slate-600">
                {report.coverage.map((item) => (
                  <p key={item.period} className="capitalize">
                    {item.period}: {fmtNum(item.recorded_events)} customer events ·{' '}
                    {fmtPct(item.identified_share)} with visitor identity
                  </p>
                ))}
                {report.caveats.map((caveat) => (
                  <p key={caveat} className="text-xs leading-relaxed">
                    {caveat}
                  </p>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Next checks & timeline</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-slate-600">
                <ol className="list-decimal pl-4 space-y-2">
                  {report.next_checks.map((check) => (
                    <li key={check}>{check}</li>
                  ))}
                </ol>
                {report.notes.map((item, i) => (
                  <p key={i} className="border-l-2 pl-3 text-xs">
                    {item.at.slice(0, 10)} · {item.text}
                  </p>
                ))}
                {!report.notes.length && (
                  <p className="text-xs text-slate-400">
                    No timeline annotations in these windows.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                {selected ? 'Review the decision' : 'Keep this evidence'}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {!canManage && (
                <p className="text-sm text-slate-500">
                  You can inspect and export with read access. Enter a private management key in
                  Settings to save or review.
                </p>
              )}
              {selected ? (
                <form
                  className="space-y-3"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void action(
                      () => exploration.review(selected.id, status, note),
                      'Review saved. Evidence is unchanged.',
                    )
                  }}
                >
                  <Label htmlFor="review-status">Review status</Label>
                  <select
                    id="review-status"
                    value={status}
                    onChange={(e) => setStatus(e.target.value as SavedInvestigation['status'])}
                    className={selectClass + ' block'}
                  >
                    {['observed', 'investigating', 'resolved', 'dismissed'].map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                  <Label htmlFor="review-note">Decision and supporting context</Label>
                  <textarea
                    id="review-note"
                    maxLength={2000}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    className="block min-h-20 w-full rounded border border-slate-200 p-3 text-sm"
                  />
                  <Button disabled={!canManage || busy}>Save review</Button>
                </form>
              ) : (
                <form
                  className="flex flex-wrap gap-3"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void action(
                      () => exploration.save(title.trim(), report.plan),
                      'Evidence saved. This record will stay unchanged when new events arrive.',
                    )
                  }}
                >
                  <Label className="sr-only" htmlFor="investigation-title">
                    Investigation title
                  </Label>
                  <Input
                    id="investigation-title"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    required
                    maxLength={200}
                    className="max-w-sm"
                  />
                  <Button disabled={!canManage || busy}>
                    <Bookmark /> Save evidence
                  </Button>
                </form>
              )}
              <details className="text-xs text-slate-500">
                <summary className="cursor-pointer">Inspect query plan and evidence ID</summary>
                <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3">
                  {JSON.stringify(
                    {
                      metric_version: report.metric_version,
                      evidence_id: report.evidence_id,
                      generated_at: report.generated_at,
                      plan: report.plan,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </CardContent>
          </Card>
        </>
      )}
      <section>
        <h3 className="mb-3 text-sm font-semibold">Saved investigations</h3>
        <FetchError error={history.error} retry={history.reload} />
        <div className="space-y-2">
          {history.data?.map((item) => (
            <button
              key={item.id}
              disabled={busy}
              onClick={() => void action(() => exploration.investigation(item.id))}
              className="flex w-full items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm hover:bg-slate-50"
            >
              <span>
                {item.title}
                <span className="ml-2 text-xs text-slate-400">{item.created_at.slice(0, 10)}</span>
              </span>
              <span className="text-xs text-slate-500">{item.status}</span>
            </button>
          ))}
        </div>
        {!history.loading && !history.data?.length && (
          <p className="text-sm text-slate-500">Saved evidence and decisions will appear here.</p>
        )}
      </section>
    </div>
  )
}
