import { Check, AlertTriangle, XCircle } from 'lucide-react'
import type { HealthCheck } from '@/lib/api'

const ICON = {
  ok: <Check className="h-4 w-4 shrink-0 text-emerald-600" />,
  warning: <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />,
  missing: <XCircle className="h-4 w-4 shrink-0 text-red-500" />,
}

const ROW = {
  ok: 'border-slate-200',
  warning: 'border-amber-200 bg-amber-50/50',
  missing: 'border-red-200 bg-red-50/50',
}

/** Integration health checklist: is the customer's instrumentation flowing? */
export function HealthChecklist({ checks }: { checks: HealthCheck[] }) {
  return (
    <div className="space-y-1.5">
      {checks.map((c) => (
        <div
          key={c.key}
          className={`flex items-start gap-2.5 rounded-lg border px-3 py-2 ${ROW[c.status]}`}
        >
          <span className="mt-0.5">{ICON[c.status]}</span>
          <div>
            <p className="text-xs font-medium text-slate-800">{c.label}</p>
            <p className="text-[11px] leading-relaxed text-slate-500">{c.detail}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
