import type { ReactNode } from 'react'
import {
  LayoutDashboard, Activity, MousePointerClick, DollarSign, Filter,
  Sparkles, Bell, Bot, Settings as SettingsIcon, LogOut, Calendar,
} from 'lucide-react'
import { useApp, type PageKey } from '@/lib/store'
import { clearReadKey } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const NAV: { key: PageKey; label: string; icon: typeof LayoutDashboard }[] = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'realtime', label: 'Realtime', icon: Activity },
  { key: 'events', label: 'Events', icon: MousePointerClick },
  { key: 'revenue', label: 'Revenue', icon: DollarSign },
  { key: 'funnels', label: 'Funnels', icon: Filter },
  { key: 'ask', label: 'Ask AI', icon: Sparkles },
  { key: 'alerts', label: 'Alerts', icon: Bell },
  { key: 'mcp', label: 'Agent usage', icon: Bot },
  { key: 'settings', label: 'Settings', icon: SettingsIcon },
]

export function Shell({ children }: { children: ReactNode }) {
  const { page, setPage, days, setDays, project, setProject } = useApp()

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white">
            <Bot className="h-4 w-4" />
          </div>
          <div>
            <div className="text-sm font-bold leading-none">AgentLens</div>
            <div className="mt-0.5 max-w-[140px] truncate text-[11px] text-slate-500">{project?.name}</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map((item) => (
            <button
              key={item.key}
              onClick={() => setPage(item.key)}
              className={cn(
                'flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors',
                page === item.key
                  ? 'bg-slate-900 font-medium text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </button>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-3">
          <button
            onClick={() => { clearReadKey(); setProject(null); }}
            className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-slate-500 hover:bg-slate-100"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <h1 className="text-lg font-semibold capitalize">{page === 'mcp' ? 'Agent usage' : page === 'ask' ? 'Ask AI' : page}</h1>
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-slate-400" />
            <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
              <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Last 7 days</SelectItem>
                <SelectItem value="30">Last 30 days</SelectItem>
                <SelectItem value="90">Last 90 days</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  )
}
