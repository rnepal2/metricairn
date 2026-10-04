import { useState } from 'react'
import { exploration } from '@/lib/exploration'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtNum, fmtPct } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input, Label } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { FetchError } from '@/components/FetchError'
import { ExportButton } from '@/components/ExportButton'
export function Retention() {
  const { query } = useApp()
  const [event, setEvent] = useState('')
  const [applied, setApplied] = useState('')
  const report = useFetch(() => exploration.retention(query, applied), [query, applied])
  const rows =
    report.data?.cohorts.flatMap((cohort) =>
      cohort.weeks.map((week) => ({ cohort: cohort.cohort, cohort_size: cohort.size, ...week })),
    ) || []
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Do visitors come back?</h2>
        <p className="mt-2 max-w-3xl text-sm text-slate-500">
          Weekly cohorts based on each visitor’s first recorded activity. Incomplete weeks stay
          blank so they aren’t mistaken for churn.
        </p>
      </div>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          setApplied(event.trim())
        }}
      >
        <div>
          <Label htmlFor="retention-event">Return event (optional)</Label>
          <Input
            id="retention-event"
            maxLength={200}
            value={event}
            onChange={(e) => setEvent(e.target.value)}
            placeholder="All customer activity"
            className="mt-1 w-60"
          />
        </div>
        <Button disabled={report.loading}>Update retention</Button>
        <ExportButton rows={rows} name="metricairn-retention" />
      </form>
      <FetchError error={report.error} retry={report.reload} />
      {report.loading && (
        <p role="status" className="text-sm text-slate-500">
          Building first-observed cohorts…
        </p>
      )}
      {report.data && (
        <Card>
          <CardContent className="overflow-x-auto pt-5">
            <table className="w-full min-w-[850px] text-sm">
              <caption className="sr-only">
                Weekly visitor retention. A dash marks an incomplete week.
              </caption>
              <thead>
                <tr>
                  <th className="p-2 text-left">First seen</th>
                  <th className="p-2 text-right">Visitors</th>
                  {Array.from({ length: 13 }, (_, week) => (
                    <th key={week} className="p-2 text-right font-normal text-xs text-slate-500">
                      W{week}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.data.cohorts.map((cohort) => (
                  <tr key={cohort.cohort}>
                    <th
                      scope="row"
                      className="whitespace-nowrap border-t p-2 text-left font-normal"
                    >
                      {cohort.cohort}
                    </th>
                    <td className="border-t p-2 text-right text-slate-500">
                      {fmtNum(cohort.size)}
                    </td>
                    {cohort.weeks.map((cell) => (
                      <td
                        key={cell.week}
                        className="border border-white p-2 text-right text-xs tabular-nums"
                        style={{
                          backgroundColor:
                            cell.rate == null
                              ? '#f8fafc'
                              : `rgba(13, 148, 136, ${0.06 + cell.rate * 0.45})`,
                        }}
                        title={
                          cell.visitors == null
                            ? 'Incomplete week'
                            : `${cell.visitors} of ${cohort.size} visitors active`
                        }
                      >
                        {fmtPct(cell.rate)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {!report.data.cohorts.length && (
              <p className="py-8 text-center text-sm text-slate-500">
                No visitors first observed in this window. A longer range may include earlier
                cohorts.
              </p>
            )}
          </CardContent>
        </Card>
      )}
      {report.data?.notes.map((note) => (
        <p key={note} className="text-xs text-slate-500">
          {note}
        </p>
      ))}
    </div>
  )
}
