import { KeyManagement } from '@/components/KeyManagement'
import { FetchError } from '@/components/FetchError'
import { useState } from 'react'
import { Copy, Check, Code2, Bot, StickyNote, Plus, ShieldCheck, Trash2 } from 'lucide-react'
import {
  api,
  BASE,
  getManagementKey,
  setManagementKey,
  type DataSummary,
  type IntegrationHealth,
} from '@/lib/api'
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
          {copied ? (
            <Check className="h-3.5 w-3.5 text-emerald-600" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
      <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">
        {code}
      </pre>
    </div>
  )
}

export function Settings() {
  const { project } = useApp()
  const notes = useFetch(
    () => (project ? api.notes(project.project_id) : Promise.resolve([])),
    [project?.project_id],
  )
  const health = useFetch<IntegrationHealth>(
    () =>
      project
        ? api.integrationHealth(project.project_id)
        : Promise.resolve(null as unknown as IntegrationHealth),
    [project?.project_id],
  )
  const [noteText, setNoteText] = useState('')

  const apiBase = BASE || window.location.origin
  const trackerKey = sessionStorage.getItem('metricairn_tracker_key') || 'alw_YOUR_TRACKING_KEY'
  const [adminKey, setAdminKey] = useState(getManagementKey() || '')
  const [adminError, setAdminError] = useState('')
  const [adminSaved, setAdminSaved] = useState(false)
  const [noteError, setNoteError] = useState('')
  const [noteBusy, setNoteBusy] = useState(false)

  const snippet = `<!-- Metricairn: browser-local random IDs; no cookies. -->
<script defer src="${apiBase}/static/metricairn.js"
  data-api="${apiBase}/api/v1/ingest"
  data-key="${trackerKey}"></script>
<!-- Fire custom events from application handlers after the script loads: -->
<!-- window.metricairn?.event('signup', { plan: 'pro' }); -->`

  const mcpConfig = `{
  "mcpServers": {
    "metricairn": {
      "command": "python",
      "args": ["-m", "metricairn_mcp"],
      "env": {
        "METRICAIRN_API_URL": "${apiBase}",
        "METRICAIRN_READ_KEY": "alr_YOUR_READ_KEY",
        "METRICAIRN_WRITE_KEY": "alw_YOUR_TRACKING_KEY"
      }
    }
  }
}`

  async function addNote() {
    if (!project || !noteText.trim()) return
    setNoteBusy(true)
    setNoteError('')
    try {
      await api.addNote(project.project_id, noteText.trim())
      setNoteText('')
      await notes.reload()
    } catch (e) {
      setNoteError(e instanceof Error ? e.message : 'Could not save note')
    } finally {
      setNoteBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Private management access</CardTitle>
          <CardDescription>
            Required for funnels, notes, notification settings, and data deletion. Never place this
            key in your website or tracker. Stored in this tab until sign-out.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              type="password"
              aria-label="Management key"
              placeholder="alm_…"
              value={adminKey}
              onChange={(e) => {
                setAdminKey(e.target.value)
                setAdminSaved(false)
              }}
            />
            <Button
              disabled={!adminKey.trim()}
              onClick={async () => {
                setAdminError('')
                try {
                  if (!project) return
                  await api.verifyManagement(project.project_id, adminKey.trim())
                  setManagementKey(adminKey.trim())
                  setAdminSaved(true)
                } catch (e) {
                  setAdminError(e instanceof Error ? e.message : 'Invalid key')
                }
              }}
            >
              Save
            </Button>
          </div>
          {adminError && (
            <p role="alert" className="mt-2 text-xs text-red-700">
              {adminError}
            </p>
          )}
          {adminSaved && (
            <p className="mt-2 text-xs text-emerald-700">Management access verified.</p>
          )}
          <KeyManagement revision={adminSaved} />
        </CardContent>
      </Card>
      <FetchError
        error={notes.error || health.error}
        retry={() => {
          void notes.reload()
          void health.reload()
        }}
      />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Code2 className="h-4 w-4" /> Installation
          </CardTitle>
          <CardDescription>
            Add the snippet for traffic. Send server payment events for revenue. The tracker uses
            localStorage IDs; omit personal data from properties.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {health.data && (
            <div className="mb-4">
              <p className="mb-2 text-xs font-medium text-slate-500">
                Integration health — is your instrumentation flowing?
              </p>
              <HealthChecklist checks={health.data.checks} />
            </div>
          )}
          <Tabs defaultValue="snippet">
            <TabsList>
              <TabsTrigger value="snippet">HTML snippet</TabsTrigger>
              <TabsTrigger value="server">Server events</TabsTrigger>
              <TabsTrigger value="proxy">First-party proxy</TabsTrigger>
            </TabsList>
            <TabsContent value="snippet">
              <CodeBlock label="Paste into <head>" code={snippet} />
            </TabsContent>
            <TabsContent value="server">
              <div className="space-y-3">
                <p className="text-xs text-slate-600">
                  Every revenue answer — anomaly alerts, attribution, the Monday digest — depends on
                  your app firing <code className="font-mono">revenue</code> events. Send from your
                  server after verifying payment. Include a stable payment ID to deduplicate retries
                  and pass visitor and campaign context from your checkout:
                </p>
                <CodeBlock
                  label="Python"
                  code={`import requests\nrequests.post("${apiBase}/api/v1/ingest/events",\n    headers={"X-Write-Key": "alw_YOUR_WRITE_KEY"},\n    json={"event_id": "payment_123", "name": "revenue",
          "revenue_amount": 49.00, "revenue_currency": "USD",\n          "props": {"plan": "pro", "billing": "monthly"}})`}
                />
                <CodeBlock
                  label="Node"
                  code={`await fetch("${apiBase}/api/v1/ingest/events", {\n  method: "POST",\n  headers: { "Content-Type": "application/json", "X-Write-Key": "alw_YOUR_WRITE_KEY" },\n  body: JSON.stringify({ event_id: "payment_123", name: "revenue",
    revenue_amount: 49.00, revenue_currency: "USD",\n    props: { plan: "pro", billing: "monthly" } }),\n});`}
                />
                <div className="rounded-lg border border-slate-200 p-3">
                  <p className="text-xs font-medium text-slate-700">
                    Zero-code option: Stripe webhook (opt-in)
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Point a Stripe webhook at{' '}
                    <code className="rounded bg-slate-100 px-1 font-mono">
                      {apiBase}/api/v1/integrations/stripe/webhook?key=alw_YOUR_WRITE_KEY
                    </code>{' '}
                    with events <code className="font-mono">checkout.session.completed</code> and{' '}
                    <code className="font-mono">invoice.paid</code> — paid one-time checkouts and
                    invoices become <code className="font-mono">revenue</code> events automatically
                    (signature-verified, idempotent, no customer PII stored). Requires{' '}
                    <code className="font-mono">STRIPE_WEBHOOK_SECRET</code> set on the API server.
                    Off by default — you hold the tap.
                  </p>
                </div>
              </div>
            </TabsContent>
            <TabsContent value="proxy">
              <CodeBlock
                label="Snippet (first-party paths)"
                code={`<script defer src="https://YOUR-DOMAIN/al/script.js"\n  data-api="https://YOUR-DOMAIN/al/ingest"\n  data-key="alw_YOUR_WRITE_KEY"></script>`}
              />
              <CodeBlock
                label="nginx"
                code={`location = /al/script.js {\n    proxy_pass ${apiBase}/static/metricairn.js;\n}\nlocation /al/ {\n    proxy_pass ${apiBase}/api/v1/;\n}`}
              />
              <p className="mt-2 text-xs text-slate-500">
                Serve the tracker through your own domain. This can improve collection reliability;
                respect visitors’ privacy preferences and do not promise complete coverage. Verify
                with{' '}
                <code className="rounded bg-slate-100 px-1 font-mono">
                  curl https://YOUR-DOMAIN/al/ingest/ping
                </code>{' '}
                (expect <code className="font-mono">{'{"ok":true}'}</code>). Full configs for Caddy,
                Next.js, Vercel, Cloudflare Workers:{' '}
                <code className="font-mono">docs/first-party-proxy.md</code>.
              </p>
            </TabsContent>
          </Tabs>
          <p className="mt-3 text-xs text-slate-500">
            Get your keys from the API:{' '}
            <code className="rounded bg-slate-100 px-1 font-mono">POST /api/v1/projects</code>{' '}
            returns a tracking key (<code className="font-mono">alw_…</code>) a read key (
            <code className="font-mono">alr_…</code>), and a private management key (
            <code className="font-mono">alm_…</code>). This dashboard uses your read key.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-4 w-4" /> Connect your AI agent (MCP)
          </CardTitle>
          <CardDescription>
            Query tools are read-only. Optional usage reporting needs the tracking key. Your agent
            queries live analytics from Claude Code, Cursor, or Claude Desktop.
          </CardDescription>
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
            Also install the{' '}
            <code className="rounded bg-slate-100 px-1 font-mono">metricairn-analytics</code> skill
            from <code className="font-mono">skills/metricairn-analytics/SKILL.md</code> so your
            agent knows the workflow.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" /> Data &amp; privacy
          </CardTitle>
          <CardDescription>
            Exactly what Metricairn holds for this project — and nothing else. We only ever see the
            events you send us: no database access, no Stripe OAuth.
          </CardDescription>
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
          <CardTitle className="flex items-center gap-2">
            <StickyNote className="h-4 w-4" /> Timeline notes
          </CardTitle>
          <CardDescription>
            Annotate launches and campaigns — notes appear on your charts.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="mb-2 text-[11px] text-slate-400">
            Tip: your AI agent can write these itself — set a private{' '}
            <code className="font-mono">METRICAIRN_MANAGEMENT_KEY</code> and enable{' '}
            <code className="font-mono">METRICAIRN_ENABLE_NOTE_WRITE=1</code> on the MCP server and
            it will log deploys as they ship.
          </p>
          <div className="flex gap-2">
            <Input
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Shipped v2 pricing page"
              onKeyDown={(e) => e.key === 'Enter' && addNote()}
            />
            <Button disabled={noteBusy || !noteText.trim()} onClick={addNote}>
              <Plus /> Add
            </Button>
          </div>
          {noteError && (
            <p role="alert" className="text-xs text-red-700">
              {noteError}
            </p>
          )}
          <div className="mt-3 space-y-1.5">
            {notes.loading ? (
              <Skeleton className="h-16" />
            ) : (
              (notes.data || []).map((n) => (
                <div
                  key={n.id}
                  className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-xs"
                >
                  <span>{n.text}</span>
                  <span className="text-slate-400">{new Date(n.at).toLocaleDateString()}</span>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function DataPrivacy({ projectId }: { projectId?: string }) {
  const [writeKey, setWk] = useState(getManagementKey() ?? '')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState<Record<string, number> | null>(null)
  const summary = useFetch<DataSummary>(
    () =>
      projectId ? api.dataSummary(projectId) : Promise.resolve(null as unknown as DataSummary),
    [projectId, done],
  )

  async function doDelete() {
    if (!projectId) return
    setBusy(true)
    setError('')
    try {
      setManagementKey(writeKey.trim())
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
      <FetchError error={summary.error} retry={summary.reload} />
      {summary.loading ? (
        <Skeleton className="h-20" />
      ) : (
        s && (
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
              {s.first_event_at ? (
                <>
                  Holding data from{' '}
                  <strong>{new Date(s.first_event_at).toLocaleDateString()}</strong> to{' '}
                  <strong>{new Date(s.last_event_at!).toLocaleDateString()}</strong>.
                </>
              ) : (
                'No events received yet.'
              )}
              {s.top_events?.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {s.top_events.map((e) => (
                    <span
                      key={e.name}
                      className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600"
                    >
                      {e.name} · {e.count.toLocaleString()}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      )}
      {done && (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
          Deleted:{' '}
          {Object.entries(done)
            .map(([k, v]) => `${v.toLocaleString()} ${k}`)
            .join(', ')}
          . Project and API keys kept.
        </p>
      )}
      <div className="rounded-lg border border-red-200 bg-red-50/50 p-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-red-900">Delete all my data</p>
            <p className="text-xs text-red-700/80">
              Removes every event, note, funnel, and alert record. Your project and keys survive.
              This cannot be undone.
            </p>
          </div>
          {!confirming && (
            <Button
              variant="outline"
              size="sm"
              className="border-red-300 text-red-700 hover:bg-red-100"
              onClick={() => setConfirming(true)}
            >
              <Trash2 className="h-3.5 w-3.5" /> Delete…
            </Button>
          )}
        </div>
        {confirming && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-medium text-red-900">
              This requires your private management key — a read key alone can never delete data.
            </p>
            <div className="flex gap-2">
              <Input
                type="password"
                value={writeKey}
                onChange={(e) => setWk(e.target.value)}
                placeholder="alm_… management key"
                className="font-mono text-xs"
              />
              <Button
                size="sm"
                variant="destructive"
                disabled={busy || !writeKey.trim()}
                onClick={doDelete}
              >
                {busy ? 'Deleting…' : 'Yes, delete everything'}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setConfirming(false)
                  setError('')
                }}
              >
                Cancel
              </Button>
            </div>
            {error && <p className="text-xs text-red-700">{error}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
