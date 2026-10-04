import { useId } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  Cell,
} from 'recharts'
import { fmtDate } from '@/lib/utils'

const COLORS = [
  '#0f172a',
  '#334155',
  '#64748b',
  '#94a3b8',
  '#cbd5e1',
  '#0ea5e9',
  '#8b5cf6',
  '#10b981',
  '#f59e0b',
  '#ef4444',
]

export function TimeseriesChart({
  data,
  title,
}: {
  data: { t: string; value: number }[]
  title?: string
}) {
  const fillId = useId().replaceAll(':', '')
  const formatted = data.map((d) => ({ ...d, label: fmtDate(d.t) }))
  return (
    <div className="h-64 w-full">
      {title && <div className="mb-2 text-sm font-medium text-slate-700">{title}</div>}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={formatted} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#0f172a" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#0f172a" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: '#64748b' }}
            tickLine={false}
            axisLine={false}
            minTickGap={32}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#64748b' }}
            tickLine={false}
            axisLine={false}
            width={48}
          />
          <Tooltip
            contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
            labelFormatter={(_, payload) =>
              payload?.[0]?.payload?.t
                ? new Date(payload[0].payload.t).toLocaleDateString('en-US', {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                  })
                : ''
            }
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#0f172a"
            strokeWidth={2}
            fill={`url(#${fillId})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export function BarListChart({
  data,
  xKey,
  yKey,
  title,
}: {
  data: Record<string, unknown>[]
  xKey: string
  yKey: string
  title?: string
}) {
  const formatted = data.slice(0, 10).map((d) => ({
    name: String(d[xKey] ?? ''),
    value: Number(d[yKey] ?? 0),
  }))
  return (
    <div className="h-64 w-full">
      {title && <div className="mb-2 text-sm font-medium text-slate-700">{title}</div>}
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={formatted}
          layout="vertical"
          margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 11, fill: '#64748b' }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            tickFormatter={(value) => String(value).slice(0, 28)}
            tick={{ fontSize: 11, fill: '#475569' }}
            tickLine={false}
            axisLine={false}
            width={140}
          />
          <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
          <Bar isAnimationActive={false} dataKey="value" radius={[0, 4, 4, 0]}>
            {formatted.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
