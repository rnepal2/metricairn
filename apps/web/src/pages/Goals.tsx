import { useState } from 'react'
import { Target } from 'lucide-react'
import { getManagementKey } from '@/lib/api'
import { exploration, type Goal } from '@/lib/exploration'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtNum, fmtPct } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input, Label } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FetchError } from '@/components/FetchError'
import { ExportButton } from '@/components/ExportButton'

function GoalCard({
  goal,
  query,
  remove,
}: {
  goal: Goal
  query: string
  remove: () => Promise<void>
}) {
  const result = useFetch(() => exploration.goalReport(goal.id, query), [goal.id, query])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const report = result.data
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{goal.name}</CardTitle>
        <code className="text-xs text-slate-500">{goal.event_name}</code>
      </CardHeader>
      <CardContent className="space-y-4">
        <FetchError error={error || result.error} retry={result.reload} />
        {result.loading && (
          <p role="status" className="text-sm text-slate-500">
            Measuring conversion…
          </p>
        )}
        {report && (
          <>
            <div className="text-3xl font-semibold">{fmtPct(report.conversion_rate)}</div>
            <p className="text-sm text-slate-600">
              {fmtNum(report.converted_visitors)} converted / {fmtNum(report.eligible_visitors)}{' '}
              visitors with a pageview
            </p>
            <p className="text-xs text-slate-500">
              {fmtNum(report.occurrences)} occurrences · {fmtNum(report.unidentified_occurrences)}{' '}
              without visitor identity
            </p>
            <p className="text-xs leading-relaxed text-slate-500">{report.definition}</p>
            <ExportButton rows={[report]} name={`metricairn-goal-${goal.id}`} />
          </>
        )}
        {getManagementKey() && (
          <div className="border-t pt-3">
            {confirming ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs">Remove goal? Tracked events stay.</span>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    try {
                      await remove()
                    } catch (e) {
                      setError(e instanceof Error ? e.message : 'Could not remove goal')
                      setBusy(false)
                    }
                  }}
                >
                  Remove goal
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
                Remove
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
export function Goals() {
  const { query } = useApp()
  const goals = useFetch(exploration.goals, [])
  const [name, setName] = useState('')
  const [event, setEvent] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Define the actions that matter</h2>
        <p className="mt-2 text-sm text-slate-500">
          Measure signup, activation, or any custom event. Conversion uses distinct visitors and an
          explicit denominator.
        </p>
      </div>
      <FetchError error={error || goals.error} retry={goals.reload} />
      <Card>
        <CardContent className="pt-5">
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy(true)
              setError('')
              try {
                await exploration.createGoal(name.trim(), event.trim())
                setName('')
                setEvent('')
                await goals.reload()
              } catch (e) {
                setError(e instanceof Error ? e.message : 'Could not create goal')
              } finally {
                setBusy(false)
              }
            }}
          >
            <div>
              <Label htmlFor="goal-name">Goal name</Label>
              <Input
                id="goal-name"
                required
                maxLength={200}
                placeholder="Account activated"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="goal-event">Tracked event name</Label>
              <Input
                id="goal-event"
                required
                maxLength={200}
                placeholder="activation"
                value={event}
                onChange={(e) => setEvent(e.target.value)}
                className="mt-1"
              />
            </div>
            <Button disabled={busy || !getManagementKey()}>
              <Target /> Create goal
            </Button>
          </form>
          {!getManagementKey() && (
            <p className="mt-3 text-xs text-slate-500">
              Add your private management key in Settings to create goals.
            </p>
          )}
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        {goals.data?.map((goal) => (
          <GoalCard
            key={goal.id}
            goal={goal}
            query={query}
            remove={async () => {
              await exploration.deleteGoal(goal.id)
              await goals.reload()
            }}
          />
        ))}
      </div>
      {!goals.loading && !goals.data?.length && (
        <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          Create a goal for an event you already track, then see its conversion rate here.
        </p>
      )}
    </div>
  )
}
