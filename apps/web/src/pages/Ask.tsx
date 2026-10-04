import { useState } from 'react'
import { Sparkles, Send, Loader2, Lightbulb, AlertTriangle } from 'lucide-react'
import { api, type AskResult } from '@/lib/api'
import { useApp } from '@/lib/store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { TimeseriesChart, BarListChart } from '@/components/charts/charts'

const EXAMPLES = [
  'What were my top pages last week?',
  'Where is revenue coming from?',
  'How many visitors did we have in the last 7 days?',
  'Any anomalies in the last 30 days?',
  'What is happening right now?',
]

export function Ask() {
  const { query } = useApp()
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<AskResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function submit(q: string) {
    const text = q.trim()
    if (!text || loading) return
    setLoading(true)
    setError('')
    try {
      const r = await api.ask(text, query)
      setResult(r)
      setQuestion('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ask failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4" /> Ask your analytics</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => { e.preventDefault(); submit(question) }} className="flex gap-2">
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. Where is revenue coming from this month?"
              className="flex-1"
            />
            <Button type="submit" disabled={loading || !question.trim()}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send />}
            </Button>
          </form>
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button key={ex} onClick={() => submit(ex)} className="flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-slate-200">
                <Lightbulb className="h-3 w-3" /> {ex}
              </button>
            ))}
          </div>
          {error && <p className="mt-3 text-xs text-red-600">{error}</p>}
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardContent className="pt-5">
            <div className="flex items-start gap-2">
              <Badge variant="info" className="mt-0.5 shrink-0">Answer</Badge>
              <p className="text-sm leading-relaxed">{result.answer}</p>
            </div>
            {result.coverage_notes && result.coverage_notes.length > 0 && (
              <div className="mt-3 space-y-1.5">
                {result.coverage_notes.map((n, i) => (
                  <p key={i} className="flex gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-800">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {n}
                  </p>
                ))}
              </div>
            )}
            {result.chart?.type === 'timeseries' && (
              <div className="mt-4"><TimeseriesChart data={result.data as unknown as { t: string; value: number }[]} title={result.chart.title} /></div>
            )}
            {result.chart?.type === 'bar' && (
              <div className="mt-4"><BarListChart data={result.data} xKey={result.chart.x_key} yKey={result.chart.y_key} title={result.chart.title} /></div>
            )}
            <p className="mt-4 text-[11px] text-slate-400">
              The same questions work from your AI agent via the AgentLens MCP server — see Settings.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
