import { useState } from 'react'
import { Copy, Check, Code2, Bot, StickyNote, Plus, ShieldCheck, Trash2 } from 'lucide-react'
import { api, getWriteKey, setWriteKey, type DataSummary, type IntegrationHealth } from '@/lib/api'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { HealthChecklist } from '@/components/HealthChecklist'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

function CodeBlock({ code, label }: { code: string; label: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500">{label}</span>
        <Button variant="ghost" size="sm" onClick={copy}>
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
      <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">{code}</pre>
    </div>
  )
}

export function Settings() {
  const { project } = useApp()
  const notes = useFetch(() => (project ? api.notes(project.project_id) : Promise.resolve([])), [project?.project_id])
  const health = useFetch<IntegrationHealth>(() => (project ? api.integrationHealth(project.project_id) : Promise.resolve(null as unknown as IntegrationHealth)), [project?.project_id])
  const [noteText, setNoteText] = useState('')

  const apiBase = typeof window !== 'undefined' ? window.location.origin.replace(':5173', ':8000') : 'http://localhost:8000'

  const snippet = `<!-- AgentLens — privacy-friendly, cookieless, <4KB -->
<script defer src="${apiBase}/static/agentlens.js"
  data-api="${apiBase}/api/v1/ingest"
  data-key="alw_YOUR_WRITE_KEY"></script>
<script>
  // Custom events
  agentlens.event('signup', { plan: 'pro' });
  // Revenue
  agentlens.revenue(49, { currency: 'USD' });
</script>`

  const mcpConfig = `{
  "mcpServers": {
    "agentlens": {
      "command": "python",
      "args": ["-m", "agentlens_mcp"],
      "env": {
        "AGENTLENS_API_URL": "${apiBase}",
        "AGENTLENS_READ_KEY": "alr_YOUR_READ_KEY",
        "AGENTLENS_WRITE_KEY": "alw_YOUR_WRITE_KEY"
      }
    }
  }
}`

  async function addNote() {
    if (!project || !noteText.trim()) return
    await api.addNote(project.project_id, noteText.trim())
    setNoteText('')
    notes.reload()
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Code2 className="h-4 w-4" /> Installation</CardTitle>
          <CardDescription>Add one snippet to start tracking. No cookies, no personal data.</CardDescription>
        </CardHeader>
        <CardContent>
          {health.data && (
            <div className="mb-4">
              <p className="mb-2 text-xs font-medium text-slate-500">Integration health — is your instrumentation flowing?</p>
              <HealthChecklist checks={health.data.checks} />
            </div>
          )}
          <Tabs defaultValue="snippet">
            <TabsList>
              <TabsTrigger value="snippet">HTML snippet</TabsTrigger>
              <TabsTrigger value="npm">npm package</TabsTrigger>
              <TabsTrigger value="proxy">First-party proxy</TabsTrigger>
            </TabsList>
            <TabsContent value="snippet">
              <CodeBlock label="Paste into <head>" code={snippet} />
            </TabsContent>
            <TabsContent value="npm">
              <CodeBlock label="Install the tracker package" code={`npm install @agentlens/tracker\n\nimport { agentlens, configure } from '@agentlens/tracker';\nconfigure({ api: '${apiBase}/api/v1/ingest', key: 'alw_YOUR_WRITE_KEY' });\nagentlens.event('signup');`} />
            </TabsContent>
            <TabsContent value="proxy">
              <CodeBlock label="Snippet (first-party paths)" code={`<script defer src="https://YOUR-DOMAIN/al/script.js"\n  data-api="https://YOUR-DOMAIN/al/ingest"\n  data-key="alw_YOUR_WRITE_KEY"></script>`} />
              <CodeBlock label="nginx" code={`location = /al/script.js {\n    proxy_pass ${apiBase}/static/agentlens.js;\n}\nlocation /al/ {\n    proxy_pass ${apiBase}/api/v1/;\n}`} />
              <p className="mt-2 text-xs text-slate-500">
                Serve the tracker from your own domain so ad-blockers can't tell it apart from your API — recovers the 20–50% of events blockers eat.
                Verify with <code className="rounded bg-slate-100 px-1 font-mono">curl https://YOUR-DOMAIN/al/ingest/ping</code> (expect <code className="font-mono">{'{"ok":true}'}</code>).
                Full configs for Caddy, Next.js, Vercel, Cloudflare Workers: <code className="font-mono">docs/first-party-proxy.md</code>.
              </p>
            </TabsContent>
          </Tabs>
          <p className="mt-3 text-xs text-slate-500">
            Get your keys from the API: <code className="rounded bg-slate-100 px-1 font-mono">POST /api/v1/projects</code> returns a write key (<code className="font-mono">alw_…</code>) and read key (<code className="font-mono">alr_…</code>). This dashboard uses your read key.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Bot className="h-4 w-4" /> Connect your AI agent (MCP)</CardTitle>
          <CardDescription>Read-only by design. Your agent queries live analytics from Claude Code, Cursor, or Claude Desktop.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <CodeBlock label="Claude Code / Claude Desktop config" code={mcpConfig} />
          <div className="text-xs text-slate-600">
            <p className="font-medium">Then ask things like:</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-slate-500">
              <li>"Why did revenue dip last Tuesday?"</li>
              <li>"Which landing page converts best from Google traffic?"</li>
              <li>"Any anomalies in the last 30 days?"</li>
            </ul>
          </div>
          <p className="text-xs text-slate-500">
            Also install the <code className="rounded bg-slate-100 px-1 font-mono">agentlens-analytics</code> skill from <code className="font-mono">skills/agentlens-analytics/SKILL.md</code> so your agent knows the workflow.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Data &amp; privacy</CardTitle>
          <CardDescription>Exactly what AgentLens holds for this project — and nothing else. We only ever see the events you send us: no database access, no Stripe OAuth.</CardDescription>
        </CardHeader>
        <CardContent>
          <DataPrivacy projectId={project?.project_id} />
          <p className="mt-3 text-xs text-slate-500">
            Full story: <code className="font-mono">docs/trust-and-data.md</code> — what we collect,
            what we never see, and the revenue-events dependency behind every revenue answer.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><StickyNote className="h-4 w-4" /> Timeline notes</CardTitle>
          <CardDescription>Annotate launches and campaigns — notes appear on your charts.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="mb-2 text-[11px] text-slate-400">Tip: your AI agent can write these itself — enable <code className="font-mono">AGENTLENS_ENABLE_NOTE_WRITE=1</code> on the MCP server and it will log deploys as they ship.</p>
          <div className="flex gap-2">
            <Input value={noteText} onChange={(e) => setNoteText(e.target.value)} placeholder="Shipped v2 pricing page" onKeyDown={(e) => e.key === 'Enter' && addNote()} />
            <Button onClick={addNote}><Plus /> Add</Button>
          </div>
          <div className="mt-3 space-y-1.5">
            {notes.loading ? <Skeleton className="h-16" /> : (notes.data || []).map((n) => (
              <div key={n.id} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-xs">
                <span>{n.text}</span>
                <span className="text-slate-400">{new Date(n.at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function DataPrivacy({ projectId }: { projectId?: string }) {
  const [writeKey, setWk] = useState(getWriteKey() ?? '')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState<Record<string, number> | null>(null)
  const summary = useFetch<DataSummary>(
    () => (projectId ? api.dataSummary(projectId) : Promise.resolve(null as unknown as DataSummary)),
    [projectId, done],
  )

  async function doDelete() {
    if (!projectId) return
    setBusy(true); setError('')
    try {
      setWriteKey(writeKey.trim())
      const r = await api.deleteAllData(projectId)
      setDone(r.deleted)
      setConfirming(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const s = summary.data
  return (
    <div className="space-y-3">
      {summary.loading ? <Skeleton className="h-20" /> : s && (
        <div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ['Events', (s.events ?? 0).toLocaleString()],
              ['Revenue events', (s.revenue_events ?? 0).toLocaleString()],
              ['Notes', (s.notes ?? 0).toLocaleString()],
              ['Funnels', (s.funnels ?? 0).toLocaleString()],
            ].map(([label, v]) => (
              <div key={label} className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-lg font-bold">{v}</div>
                <div className="text-[11px] text-slate-500">{label}</div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-xs text-slate-500">
            {s.first_event_at
              ? <>Holding data from <strong>{new Date(s.first_event_at).toLocaleDateString()}</strong> to <strong>{new Date(s.last_event_at!).toLocaleDateString()}</strong>.</>
              : 'No events received yet.'}
            {s.top_events?.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {s.top_events.map((e) => (
                  <span key={e.name} className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600">
                    {e.name} · {e.count.toLocaleString()}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      {done && (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
          Deleted: {Object.entries(done).map(([k, v]) => `${v.toLocaleString()} ${k}`).join(', ')}.
          Project and API keys kept.
        </p>
      )}
      <div className="rounded-lg border border-red-200 bg-red-50/50 p-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-red-900">Delete all my data</p>
            <p className="text-xs text-red-700/80">Removes every event, note, funnel, and alert record. Your project and keys survive. This cannot be undone.</p>
          </div>
          {!confirming && (
            <Button variant="outline" size="sm" className="border-red-300 text-red-700 hover:bg-red-100" onClick={() => setConfirming(true)}>
              <Trash2 className="h-3.5 w-3.5" /> Delete…
            </Button>
          )}
        </div>
        {confirming && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-medium text-red-900">This requires your write key — a read key alone can never delete data.</p>
            <div className="flex gap-2">
              <Input
                type="password"
                value={writeKey}
                onChange={(e) => setWk(e.target.value)}
                placeholder="alw_… write key"
                className="font-mono text-xs"
              />
              <Button size="sm" variant="destructive" disabled={busy || !writeKey.trim()} onClick={doDelete}>
                {busy ? 'Deleting…' : 'Yes, delete everything'}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setConfirming(false); setError('') }}>Cancel</Button>
            </div>
            {error && <p className="text-xs text-red-700">{error}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
