import { useState } from 'react'
import { TrendingUp, TrendingDown, Bell, Plus, Trash2, Send, Play } from 'lucide-react'
import { api, getWriteKey, setWriteKey, type Anomaly, type AlertChannel, type AlertRule, type AlertDelivery } from '@/lib/api'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtNum } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Skeleton, Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function Alerts() {
  const { query } = useApp()
  const an = useFetch<Anomaly[]>(() => api.anomalies(query), [query])

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Bell className="h-4 w-4" /> Anomaly alerts</CardTitle>
        </CardHeader>
        <CardContent>
          {an.loading ? <Skeleton className="h-48" /> : (an.data || []).length === 0 ? (
            <div className="py-10 text-center">
              <p className="text-sm font-medium">All quiet.</p>
              <p className="mt-1 text-xs text-slate-500">No statistically significant spikes or dips in pageviews or revenue for this period. AgentLens checks daily with z-score detection.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {(an.data || []).map((a, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border border-slate-200 p-3">
                  <div className="flex items-center gap-3">
                    {a.direction === 'spike' ? <TrendingUp className="h-4 w-4 text-emerald-600" /> : <TrendingDown className="h-4 w-4 text-red-600" />}
                    <div>
                      <div className="text-sm font-medium capitalize">{a.metric} {a.direction} — {a.date}</div>
                      <div className="text-xs text-slate-500">
                        {fmtNum(a.value)} observed vs ~{fmtNum(a.expected)} expected (z = {a.z_score})
                      </div>
                    </div>
                  </div>
                  <Badge variant={a.direction === 'spike' ? 'success' : 'danger'}>{a.direction}</Badge>
                </div>
              ))}
            </div>
          )}
          <p className="mt-4 text-[11px] text-slate-400">
            Tip: ask your AI agent "any anomalies this month?" — the MCP server exposes the same detection.
          </p>
        </CardContent>
      </Card>
      <Notifications />
    </div>
  )
}

function Notifications() {
  const [hasWriteKey, setHasWriteKey] = useState(!!getWriteKey())
  const [writeKeyInput, setWriteKeyInput] = useState('')
  const channels = useFetch<AlertChannel[]>(() => api.alertChannels(), [hasWriteKey])
  const rules = useFetch<AlertRule[]>(() => api.alertRules(), [hasWriteKey])
  const deliveries = useFetch<AlertDelivery[]>(() => api.alertDeliveries(), [hasWriteKey])
  const [kind, setKind] = useState('email')
  const [target, setTarget] = useState('')
  const [ruleName, setRuleName] = useState('')
  const [ruleMetric, setRuleMetric] = useState('any')
  const [ruleDir, setRuleDir] = useState('any')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')

  const refresh = () => { channels.reload(); rules.reload(); deliveries.reload() }

  async function saveWriteKey() {
    setWriteKey(writeKeyInput.trim())
    setWriteKeyInput('')
    setHasWriteKey(true)
  }

  async function addChannel() {
    setBusy('add-channel'); setMsg('')
    try {
      await api.addAlertChannel(kind, target.trim())
      setTarget(''); refresh()
    } catch (e) { setMsg(e instanceof Error ? e.message : 'Failed') }
    finally { setBusy('') }
  }

  async function addRule() {
    setBusy('add-rule'); setMsg('')
    try {
      await api.addAlertRule({ name: ruleName.trim() || 'Custom rule', metric: ruleMetric, direction: ruleDir, min_z: 2.5, cooldown_hours: 24 })
      setRuleName(''); refresh()
    } catch (e) { setMsg(e instanceof Error ? e.message : 'Failed') }
    finally { setBusy('') }
  }

  async function act(label: string, fn: () => Promise<unknown>, done?: string) {
    setBusy(label); setMsg('')
    try { await fn(); if (done) setMsg(done); refresh() }
    catch (e) { setMsg(e instanceof Error ? e.message : 'Failed') }
    finally { setBusy('') }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Send className="h-4 w-4" /> Notifications</CardTitle>
        <CardDescription>Get anomalies delivered to email or Slack. The scheduler checks every 30 minutes.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!hasWriteKey ? (
          <div className="rounded-lg border border-dashed border-slate-300 p-4">
            <p className="text-sm font-medium">Write key required</p>
            <p className="mt-1 text-xs text-slate-500">Managing notifications needs your write key (<code className="font-mono">alw_…</code>). It stays in this browser only.</p>
            <div className="mt-2 flex gap-2">
              <Input type="password" value={writeKeyInput} onChange={(e) => setWriteKeyInput(e.target.value)} placeholder="alw_…" />
              <Button onClick={saveWriteKey} disabled={!writeKeyInput.trim()}>Save</Button>
            </div>
          </div>
        ) : (
          <>
            <div>
              <p className="mb-2 text-sm font-medium">Channels</p>
              <div className="flex gap-2">
                <select value={kind} onChange={(e) => setKind(e.target.value)} className="rounded-md border border-slate-200 bg-white px-2 text-sm">
                  <option value="email">Email</option>
                  <option value="slack">Slack</option>
                </select>
                <Input value={target} onChange={(e) => setTarget(e.target.value)} placeholder={kind === 'email' ? 'you@example.com' : 'https://hooks.slack.com/services/…'} />
                <Button onClick={addChannel} disabled={busy === 'add-channel' || !target.trim()}><Plus /> Add</Button>
              </div>
              <div className="mt-2 space-y-1.5">
                {(channels.data || []).map((c) => (
                  <div key={c.id} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-xs">
                    <span><Badge>{c.kind}</Badge> <span className="ml-2 font-mono">{c.target}</span></span>
                    <span className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => act(`test-${c.id}`, () => api.testAlertChannel(c.id), 'Test sent — check your inbox.')} disabled={busy === `test-${c.id}`}>Test</Button>
                      <Button variant="ghost" size="sm" onClick={() => act(`del-${c.id}`, () => api.deleteAlertChannel(c.id))} disabled={busy === `del-${c.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                    </span>
                  </div>
                ))}
                {channels.data?.length === 0 && <p className="text-xs text-slate-400">No channels yet. Without a custom rule, any anomaly with |z| ≥ 3 notifies all channels.</p>}
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">Rules <span className="font-normal text-slate-400">(optional)</span></p>
              <div className="flex flex-wrap gap-2">
                <Input value={ruleName} onChange={(e) => setRuleName(e.target.value)} placeholder="Revenue dips" className="w-40" />
                <select value={ruleMetric} onChange={(e) => setRuleMetric(e.target.value)} className="rounded-md border border-slate-200 bg-white px-2 text-sm">
                  <option value="any">any metric</option>
                  <option value="revenue">revenue</option>
                  <option value="pageviews">pageviews</option>
                </select>
                <select value={ruleDir} onChange={(e) => setRuleDir(e.target.value)} className="rounded-md border border-slate-200 bg-white px-2 text-sm">
                  <option value="any">dip or spike</option>
                  <option value="dip">dip</option>
                  <option value="spike">spike</option>
                </select>
                <Button onClick={addRule} disabled={busy === 'add-rule'}><Plus /> Add rule</Button>
              </div>
              <div className="mt-2 space-y-1.5">
                {(rules.data || []).map((r) => (
                  <div key={r.id} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-xs">
                    <span>{r.name || 'Rule'} · <span className="text-slate-500">{r.metric} · {r.direction} · |z| ≥ {r.min_z} · {r.cooldown_hours}h cooldown</span></span>
                    <Button variant="ghost" size="sm" onClick={() => act(`rdel-${r.id}`, () => api.deleteAlertRule(r.id))} disabled={busy === `rdel-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => act('check', () => api.runAlertCheck(), 'Check complete.')} disabled={busy === 'check'}>
                <Play className="h-3.5 w-3.5" /> Run check now
              </Button>
              {msg && <span className="text-xs text-slate-500">{msg}</span>}
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">Delivery log</p>
              <div className="space-y-1.5">
                {(deliveries.data || []).slice(0, 10).map((d) => (
                  <div key={d.id} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-xs">
                    <span className="font-mono">{d.anomaly_key || '(test)'}</span>
                    <span className="flex items-center gap-2">
                      <span className="text-slate-400">{new Date(d.created_at).toLocaleString()}</span>
                      <Badge variant={d.status === 'sent' ? 'success' : d.status === 'failed' ? 'danger' : 'default'}>{d.status}</Badge>
                    </span>
                  </div>
                ))}
                {deliveries.data?.length === 0 && <p className="text-xs text-slate-400">Nothing sent yet.</p>}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
