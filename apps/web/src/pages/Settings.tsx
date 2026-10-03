import { useState } from 'react'
import { Copy, Check, Code2, Bot, StickyNote, Plus } from 'lucide-react'
import { api } from '@/lib/api'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
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
          <Tabs defaultValue="snippet">
            <TabsList>
              <TabsTrigger value="snippet">HTML snippet</TabsTrigger>
              <TabsTrigger value="npm">npm package</TabsTrigger>
            </TabsList>
            <TabsContent value="snippet">
              <CodeBlock label="Paste into <head>" code={snippet} />
            </TabsContent>
            <TabsContent value="npm">
              <CodeBlock label="Install the tracker package" code={`npm install @agentlens/tracker\n\nimport { agentlens, configure } from '@agentlens/tracker';\nconfigure({ api: '${apiBase}/api/v1/ingest', key: 'alw_YOUR_WRITE_KEY' });\nagentlens.event('signup');`} />
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
          <CardTitle className="flex items-center gap-2"><StickyNote className="h-4 w-4" /> Timeline notes</CardTitle>
          <CardDescription>Annotate launches and campaigns — notes appear on your charts.</CardDescription>
        </CardHeader>
        <CardContent>
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
