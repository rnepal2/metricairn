import { useState } from 'react'
import { Plus, Trash2, ArrowDown } from 'lucide-react'
import { api } from '@/lib/api'
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

export function Funnels() {
  const { query } = useApp()
  const list = useFetch(() => api.funnels(), [])
  const [selected, setSelected] = useState<string | null>(null)
  const report = useFetch(
    () => (selected ? api.funnelReport(selected, query) : Promise.resolve(null as never)),
    [selected, query]
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
              <div className="mb-3 flex items-center gap-2">
                <span className="text-sm font-medium">{report.data.name}</span>
                <Badge variant="info">overall {fmtPct(report.data.overall_conversion)}</Badge>
              </div>
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
