import { useState } from 'react'
import { Plus, Trash2, ArrowDown } from 'lucide-react'
import { api, type FunnelReport } from '@/lib/api'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtPct, fmtNum } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton, Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input, Label } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'

interface Step { kind: 'page' | 'event'; value: string }

const SEGMENT_DIMS = ['device', 'browser', 'os', 'country', 'utm_source', 'utm_medium', 'utm_campaign']

export function Funnels() {
  const { query } = useApp()
  const list = useFetch(() => api.funnels(), [])
  const [selected, setSelected] = useState<string | null>(null)
  const [segmentBy, setSegmentBy] = useState<string>('')
  const report = useFetch<FunnelReport>(
    () => (selected ? api.funnelReport(selected, query, segmentBy || undefined) : Promise.resolve(null as never)),
    [selected, query, segmentBy]
  )

  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [steps, setSteps] = useState<Step[]>([{ kind: 'page', value: '/pricing' }])
  const [saving, setSaving] = useState(false)

  async function save() {
    if (!name.trim() || steps.some((s) => !s.value.trim())) return
    setSaving(true)
    try {
      const f = await api.createFunnel(name.trim(), steps)
      setOpen(false)
      setName('')
      setSteps([{ kind: 'page', value: '/pricing' }])
      await list.reload()
      setSelected(f.id)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-1">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Funnels</CardTitle>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm"><Plus /> New</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>New funnel</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div><Label>Funnel name</Label><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Signup flow" /></div>
                {steps.map((s, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="w-6 text-xs text-slate-400">{i + 1}.</span>
                    <Select value={s.kind} onValueChange={(v) => setSteps(steps.map((x, j) => (j === i ? { ...x, kind: v as Step['kind'] } : x)))}>
                      <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="page">Page</SelectItem>
                        <SelectItem value="event">Event</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input value={s.value} onChange={(e) => setSteps(steps.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} placeholder={s.kind === 'page' ? '/pricing' : 'signup'} className="font-mono" />
                    <Button variant="ghost" size="icon" onClick={() => setSteps(steps.filter((_, j) => j !== i))} disabled={steps.length <= 1}>
                      <Trash2 />
                    </Button>
                  </div>
                ))}
                <Button variant="outline" size="sm" onClick={() => setSteps([...steps, { kind: 'event', value: '' }])}>
                  <Plus /> Add step
                </Button>
                <Button className="w-full" onClick={save} disabled={saving}>Create funnel</Button>
              </div>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent>
          {list.loading ? <Skeleton className="h-32" /> : (
            <div className="space-y-1">
              {(list.data || []).map((f) => (
                <button
                  key={f.id}
                  onClick={() => setSelected(f.id)}
                  className={`w-full rounded-md px-3 py-2 text-left text-sm ${selected === f.id ? 'bg-slate-900 text-white' : 'hover:bg-slate-100'}`}
                >
                  {f.name}
                </button>
              ))}
              {(list.data || []).length === 0 && <p className="text-xs text-slate-400">No funnels yet — create one to track signup or checkout flows.</p>}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader><CardTitle>Conversion report</CardTitle></CardHeader>
        <CardContent>
          {!selected ? (
            <p className="text-sm text-slate-400">Select a funnel to see its conversion report.</p>
          ) : report.loading ? (
            <Skeleton className="h-64" />
          ) : report.data ? (
            <div className="space-y-1">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{report.data.name}</span>
                <Badge variant="info">overall {fmtPct(report.data.overall_conversion)}</Badge>
                <span className="ml-auto flex items-center gap-1.5 text-xs text-slate-500">
                  Segment by
                  <Select value={segmentBy || 'none'} onValueChange={(v) => setSegmentBy(v === 'none' ? '' : v)}>
                    <SelectTrigger className="h-7 w-36"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Off</SelectItem>
                      {SEGMENT_DIMS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </span>
              </div>
              {report.data.segments && report.data.segments.length > 0 && (
                <div className="mb-4 rounded-lg border border-slate-200 p-3">
                  <p className="mb-2 text-xs font-medium text-slate-500">Conversion by {report.data.segment_by} (visitor's entry {report.data.segment_by})</p>
                  <div className="space-y-1.5">
                    {report.data.segments.map((seg) => (
                      <div key={seg.value} className="flex items-center gap-2 text-xs">
                        <span className="w-28 truncate font-medium">{seg.value}</span>
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full rounded-full bg-emerald-600" style={{ width: `${Math.max(2, seg.overall_conversion * 100)}%` }} />
                        </div>
                        <span className="w-12 text-right font-semibold">{fmtPct(seg.overall_conversion)}</span>
                        <span className="w-16 text-right text-slate-400">{fmtNum(seg.visitors)} in</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {report.data.steps.map((s, i) => (
                <div key={i}>
                  {i > 0 && <div className="flex justify-center py-0.5"><ArrowDown className="h-3.5 w-3.5 text-slate-300" /></div>}
                  <div className="rounded-lg border border-slate-200 p-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-mono text-xs">{s.step.kind === 'page' ? '📄' : '⚡'} {s.step.value}</span>
                      <span className="font-semibold">{fmtNum(s.visitors)}</span>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-slate-900" style={{ width: `${Math.max(2, s.conversion_from_start * 100)}%` }} />
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500">
                      {fmtPct(s.conversion_from_start)} of start · {fmtPct(s.conversion_from_prev)} of previous step
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
