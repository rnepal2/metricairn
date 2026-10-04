import { useState, type ReactNode } from 'react'
import { Search, ArrowRight, Copy, Download, RefreshCw } from 'lucide-react'
import { api, setReadKey } from '@/lib/api'
import { downloadJson } from '@/lib/exploration'
import { useApp, type PageKey } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import {
  DEMO_READ_KEY,
  DEMO_PROMPT,
  DEMO_STEPS,
  loadDemoStep,
  type DemoStep,
  type DemoResult,
} from '@/lib/demo'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FetchError } from '@/components/FetchError'
import { fmtNum, fmtPct } from '@/lib/utils'

function CopyButton({ text, label }: { text: string; label: string }) {
  const [status, setStatus] = useState('')
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setStatus('Copied')
    } catch {
      setStatus('Select the text below to copy it.')
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => void copy()}>
        <Copy />
        {label}
      </Button>
      <span role="status" className="text-xs text-slate-500">
        {status}
      </span>
    </div>
  )
}
function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-relaxed text-slate-100">
      <code>{JSON.stringify(value, null, 2)}</code>
    </pre>
  )
}
function ResultTable({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            {headers.map((header) => (
              <th
                key={header}
                className="border-b border-slate-200 py-2 pr-4 text-left text-xs font-medium text-slate-500"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, column) => (
                <td
                  key={column}
                  className="whitespace-nowrap border-b border-slate-100 py-2 pr-4 tabular-nums"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
function Evidence({ data }: { data: DemoResult }) {
  const investigation = data.investigation
  const campaigns = data.campaigns
  const goal = data.goal
  const retention = data.retention
  const sources = investigation?.segments.find((segment) => segment.dimension === 'utm_source')
  return (
    <div className="space-y-4">
      {investigation && (
        <>
          <p className="text-3xl font-semibold">
            {fmtNum(investigation.current)}{' '}
            <span className="text-base font-normal text-slate-500">
              pageviews vs {fmtNum(investigation.previous)} in the preceding seven days
            </span>
          </p>
          <ResultTable
            headers={['Source', 'Current', 'Previous', 'Change']}
            rows={[
              ...(sources?.rows || []),
              ...(sources && (sources.other.current || sources.other.previous)
                ? [{ value: 'Other sources', ...sources.other }]
                : []),
            ].map((row) => [
              row.value,
              fmtNum(row.current),
              fmtNum(row.previous),
              `${row.change > 0 ? '+' : ''}${fmtNum(row.change)}`,
            ])}
          />
          <p className="text-sm text-slate-600">
            Use changed sources to choose the next check. Segment contributions and the remaining
            tail reconcile to the total; they do not establish cause.
          </p>
          {investigation.coverage.map((item) => (
            <p key={item.period} className="text-xs text-slate-500">
              {item.period}: {fmtNum(item.recorded_events)} recorded events · identified share{' '}
              {fmtPct(item.identified_share)} · last event {item.last_event_at || 'none'}
            </p>
          ))}
          <details className="text-sm">
            <summary className="cursor-pointer font-medium">Caveats and next checks</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-600">
              {[...investigation.caveats, ...investigation.next_checks].map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          </details>
        </>
      )}
      {campaigns && (
        <>
          <p className="text-3xl font-semibold">
            {fmtNum(campaigns.total)}{' '}
            <span className="text-base font-normal text-slate-500">
              signup occurrences in 60 days
            </span>
          </p>
          <ResultTable
            headers={['Campaign tag', 'Signup occurrences']}
            rows={campaigns.rows.map((row) => [row.value, fmtNum(row.count)])}
          />
          {!campaigns.rows.length && <p>No signup events were recorded in this window.</p>}
          <p className="text-sm text-slate-600">
            Maya can inspect campaigns associated with signups. These are event occurrences,
            including repeats. Missing tags are shown as “(not set)”; this is not causal attribution
            or a conversion rate.
          </p>
          {campaigns.truncated && (
            <p className="text-xs text-slate-500">
              Only the top ten campaigns are displayed; the total includes the remaining campaigns.
            </p>
          )}
        </>
      )}
      {goal && (
        <>
          <p className="text-3xl font-semibold">
            {fmtPct(goal.conversion_rate)}{' '}
            <span className="text-base font-normal text-slate-500">Account signup conversion</span>
          </p>
          <ResultTable
            headers={['Returned evidence', 'Count']}
            rows={[
              ['Visitors with a pageview', fmtNum(goal.eligible_visitors)],
              ['Visitors with a subsequent signup', fmtNum(goal.converted_visitors)],
              ['Signup occurrences (including repeats)', fmtNum(goal.occurrences)],
              ['Occurrences without visitor identity', fmtNum(goal.unidentified_occurrences)],
            ]}
          />
          <p className="text-sm text-slate-600">{goal.definition}</p>
          <p className="text-sm text-slate-600">
            Maya gets an explicit denominator and can distinguish conversion from a count of signup
            events. This report measures period conversion, not lifetime conversion.
          </p>
        </>
      )}
      {retention && (
        <>
          <p className="text-3xl font-semibold">
            {fmtNum(retention.cohorts.length)}{' '}
            <span className="text-base font-normal text-slate-500">
              weekly first-observed visitor cohorts
            </span>
          </p>
          <ResultTable
            headers={['First seen (UTC)', 'Visitors', 'Week 1', 'Week 2', 'Week 3']}
            rows={retention.cohorts.map((cohort) => [
              cohort.cohort,
              fmtNum(cohort.size),
              ...[1, 2, 3].map((week) =>
                fmtPct(cohort.weeks.find((cell) => cell.week === week)?.rate),
              ),
            ])}
          />
          {!retention.cohorts.length && <p>No first-observed visitors in this window.</p>}
          <p className="text-sm text-slate-600">
            Maya sees whether traffic includes returning visitors. A dash marks an incomplete week,
            not zero retention. “First seen” means first recorded activity; anonymous identities are
            not verified accounts.
          </p>
          {retention.notes.map((note) => (
            <p key={note} className="text-xs text-slate-500">
              {note}
            </p>
          ))}
          <p className="text-xs text-slate-500">
            Preview shows weeks 1–3. Full output includes weeks 0–12.
          </p>
        </>
      )}
    </div>
  )
}

export function Demo() {
  const { setPage, setProject } = useApp()
  const [step, setStep] = useState<DemoStep>(0)
  const [entering, setEntering] = useState(false)
  const [error, setError] = useState('')
  const demo = useFetch(() => loadDemoStep(step), [step])
  const config = {
    mcpServers: {
      metricairn: {
        command: '/ABSOLUTE/REPO/.venv/bin/python',
        args: ['-m', 'metricairn_mcp'],
        env: { METRICAIRN_API_URL: 'http://localhost:8000', METRICAIRN_READ_KEY: DEMO_READ_KEY },
      },
    },
  }
  async function open(target: PageKey = 'investigations') {
    setEntering(true)
    setError('')
    try {
      const project = await api.me(DEMO_READ_KEY)
      setReadKey(DEMO_READ_KEY)
      setProject(project)
      setPage(target)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Demo unavailable')
    } finally {
      setEntering(false)
    }
  }
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <span className="flex items-center gap-2 font-bold">
            <Search />
            Metricairn{' '}
            <span className="text-xs font-normal text-slate-500">MCP worked example</span>
          </span>
          <Button variant="outline" onClick={() => setPage('overview')}>
            Back to your project
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl space-y-6 px-6 py-10">
        <div className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-teal-700">
            Maya Chen · Billwise · fictional founder scenario
          </p>
          <h1 className="max-w-3xl text-4xl font-bold leading-tight">
            How Maya investigates growth at Billwise.
          </h1>
          <p className="max-w-3xl text-lg text-slate-600">
            Ask a question. Inspect the tool call. Get evidence you can use. Maya runs an invoicing
            app for freelancers and wants to understand traffic, signups, and returning visitors.
          </p>
          <p className="max-w-3xl text-sm text-slate-500">
            This browser previews the same API results used by our MCP tools, using 60 days of
            simulated events. It does not run an AI agent or MCP session. Connect your agent below
            to run the actual tools; core analytics requires no AI key.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void open()} disabled={entering}>
              Explore dashboard <ArrowRight />
            </Button>
            <Button variant="outline" onClick={() => void demo.reload()} disabled={demo.loading}>
              <RefreshCw />
              Refresh evidence
            </Button>
          </div>
          <FetchError error={error} />
        </div>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Try this prompt in your connected agent
            </p>
            <p className="text-sm leading-relaxed">{DEMO_PROMPT}</p>
            <CopyButton text={DEMO_PROMPT} label="Copy prompt" />
            <details className="border-t border-slate-200 pt-3">
              <summary className="cursor-pointer text-sm font-medium">
                Connect Metricairn to your MCP client
              </summary>
              <div className="mt-3 space-y-3">
                <p className="text-sm text-slate-600">
                  After make setup, replace /ABSOLUTE/REPO with your checkout path. Keep the API
                  running on port 8000 and seed Billwise. This shared read key is for fictional data
                  only.
                </p>
                <CopyButton text={JSON.stringify(config, null, 2)} label="Copy MCP configuration" />
                <JsonBlock value={config} />
                <p className="text-sm text-slate-600">
                  To verify actual MCP calls without an AI client:{' '}
                  <code className="break-all">uv run python scripts/demo_mcp.py</code>. The script
                  prints tool arguments and returned JSON through a real stdio MCP session.
                </p>
              </div>
            </details>
          </CardContent>
        </Card>
        <nav aria-label="MCP example steps" className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {DEMO_STEPS.map((label, index) => (
            <Button
              key={label}
              className="h-auto min-h-12 whitespace-normal text-left"
              variant={step === index ? 'default' : 'outline'}
              aria-pressed={step === index}
              onClick={() => setStep(index as DemoStep)}
            >
              {index + 1}. {label}
            </Button>
          ))}
        </nav>
        <FetchError error={demo.error} retry={demo.reload} />
        {demo.loading && (
          <p role="status" className="text-sm text-slate-500">
            Loading {DEMO_STEPS[step].toLowerCase()} from the simulated dataset…
          </p>
        )}
        {demo.data && (
          <Card>
            <CardHeader>
              <CardTitle>{DEMO_STEPS[step]}</CardTitle>
              <p className="break-all text-xs text-slate-500">
                Exact UTC window: {demo.data.window.date_from} → {demo.data.window.date_to}. Refresh
                computes a new window.
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
                <div className="min-w-0 space-y-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-teal-700">
                    MCP tool inputs
                  </p>
                  {demo.data.calls.map((call) => (
                    <div key={call.name} className="space-y-2">
                      <h3 className="font-mono text-sm font-semibold">{call.name}</h3>
                      <CopyButton
                        label={`Copy ${call.name} call`}
                        text={JSON.stringify(
                          { name: call.name, arguments: call.arguments },
                          null,
                          2,
                        )}
                      />
                      <JsonBlock value={call.arguments} />
                      {call.name === 'list_goals' && (
                        <p className="text-xs text-slate-500">
                          Discover the goal ID first. The next call uses the returned signup goal
                          ID.
                        </p>
                      )}
                    </div>
                  ))}
                </div>
                <div className="min-w-0 space-y-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-teal-700">
                    Returned evidence · API preview
                  </p>
                  <Evidence data={demo.data} />
                </div>
              </div>
              <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-4">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    demo.data &&
                    downloadJson(
                      {
                        preview: 'API-backed MCP example; not an MCP session',
                        dataset: 'fictional Billwise',
                        window: demo.data.window,
                        calls: demo.data.calls,
                      },
                      'metricairn-billwise-evidence.json',
                    )
                  }
                >
                  <Download />
                  Export calls and evidence
                </Button>
                {step === 2 && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={entering}
                    onClick={() => void open('goals')}
                  >
                    Inspect signup goal
                  </Button>
                )}
                {step === 3 && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={entering}
                    onClick={() => void open('retention')}
                  >
                    Inspect retention
                  </Button>
                )}
              </div>
              <details>
                <summary className="cursor-pointer text-sm font-medium">
                  Inspect full returned JSON
                </summary>
                <div className="mt-3 space-y-3">
                  {demo.data.calls.map((call) => (
                    <div key={call.name}>
                      <p className="mb-2 font-mono text-xs">{call.name}</p>
                      <JsonBlock value={call.result} />
                    </div>
                  ))}
                </div>
              </details>
            </CardContent>
          </Card>
        )}
        <p className="text-xs leading-relaxed text-slate-500">
          Maya Chen and Billwise are fictional. This demonstrates the workflow, not verified
          customer savings or causal impact. Results reflect seeded events and move as the date
          window advances. An agent can explain this evidence; validate a hypothesis before taking
          action.
        </p>
      </main>
    </div>
  )
}
