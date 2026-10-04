import { useState } from 'react'
import { Sparkles, Loader2, Send, Bookmark, X } from 'lucide-react'
import { api, type AskResult } from '@/lib/api'
import { useApp } from '@/lib/store'
import { Input, Label } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { TimeseriesChart, BarListChart } from '@/components/charts/charts'
import { ExportButton } from '@/components/ExportButton'
import { FetchError } from '@/components/FetchError'

const EXAMPLES = [
  'Where is revenue coming from?',
  'What were my top pages last week?',
  'Any anomalies in the last 30 days?',
  'Why did revenue dip recently?',
  'Which device converts best?',
]
export function Ask() {
  const { query, project } = useApp()
  const storageKey = `metricairn_questions_${project?.project_id}`
  const [saved, setSaved] = useState<string[]>(() => {
    try {
      const value = JSON.parse(localStorage.getItem(storageKey) || '[]')
      return Array.isArray(value) ? value.filter((q) => typeof q === 'string').slice(0, 10) : []
    } catch {
      return []
    }
  })
  const [question, setQuestion] = useState('')
  const [asked, setAsked] = useState('')
  const [result, setResult] = useState<AskResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  function save(items: string[]) {
    setSaved(items)
    localStorage.setItem(storageKey, JSON.stringify(items))
  }
  async function submit(q: string) {
    if (!q.trim() || loading) return
    setLoading(true)
    setError('')
    setResult(null)
    setAsked(q.trim())
    try {
      setResult(await api.ask(q.trim(), query))
      setQuestion('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ask failed')
    } finally {
      setLoading(false)
    }
  }
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" /> Ask your analytics
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Label htmlFor="question">Traffic, conversion, or revenue question</Label>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void submit(question)
            }}
            className="mt-2 flex gap-2"
          >
            <Input
              id="question"
              value={question}
              maxLength={500}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Where is revenue coming from?"
              className="flex-1"
            />
            <Button
              aria-label="Ask question"
              type="submit"
              disabled={loading || question.trim().length < 3}
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send />}
            </Button>
          </form>
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                disabled={loading}
                key={ex}
                onClick={() => void submit(ex)}
                className="rounded-full bg-slate-100 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200 disabled:opacity-50"
              >
                {ex}
              </button>
            ))}
          </div>
          {saved.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-xs text-slate-500">
                Saved questions · stored in this browser for this project
              </p>
              <div className="flex flex-wrap gap-2">
                {saved.map((q) => (
                  <span
                    key={q}
                    className="flex items-center gap-1 rounded border px-2 py-1 text-xs"
                  >
                    <button disabled={loading} onClick={() => void submit(q)}>
                      {q}
                    </button>
                    <button
                      aria-label={`Remove saved question ${q}`}
                      onClick={() => save(saved.filter((value) => value !== q))}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="mt-3">
            <FetchError error={error} retry={() => void submit(asked)} />
          </div>
        </CardContent>
      </Card>
      {result && (
        <Card>
          <CardContent className="space-y-4 pt-5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">
                {result.planner === 'agentic_sql' ? 'Validated SQL result' : 'Deterministic query'}
              </Badge>
              <span className="flex-1 text-sm font-medium">{asked}</span>
              <Button
                size="sm"
                variant="outline"
                disabled={saved.includes(asked) || saved.length >= 10}
                onClick={() => save([...saved, asked])}
              >
                <Bookmark className="h-3.5 w-3.5" /> Save question
              </Button>
              <ExportButton rows={result.data} name="metricairn-answer" />
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{result.answer}</p>
            {result.coverage_notes?.map((note, index) => (
              <p
                key={index}
                className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-800"
              >
                {note}
              </p>
            ))}
            {result.chart?.type === 'timeseries' && (
              <TimeseriesChart
                data={result.data as unknown as { t: string; value: number }[]}
                title={result.chart.title}
              />
            )}
            {result.chart?.type === 'bar' && (
              <BarListChart
                data={result.data}
                xKey={result.chart.x_key}
                yKey={result.chart.y_key}
                title={result.chart.title}
              />
            )}
            <details className="rounded-lg border border-slate-200 p-3">
              <summary className="cursor-pointer text-xs font-medium">
                Inspect evidence{result.data.length ? ` · ${result.data.length} rows` : ''}
              </summary>
              {result.sql_hint && (
                <>
                  <p className="mt-3 text-xs text-slate-500">
                    Generated query · the execution layer enforces project isolation independently
                  </p>
                  <pre className="mt-2 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
                    {result.sql_hint}
                  </pre>
                </>
              )}
              <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs">
                {JSON.stringify(result.data, null, 2)}
              </pre>
            </details>
            {result.based_on && (
              <p className="text-xs text-slate-500">
                Reference window: {result.based_on.events.toLocaleString()} customer events ·{' '}
                {result.based_on.event_names.join(', ') || 'none'} ·{' '}
                {result.based_on.date_range.from} → {result.based_on.date_range.to} UTC. SQL time
                filters are shown above. Detection scores are screening signals; explanations are
                hypotheses.
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
