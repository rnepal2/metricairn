import type { ReactNode } from 'react'
import {
  LayoutDashboard,
  Activity,
  MousePointerClick,
  DollarSign,
  Filter,
  Sparkles,
  Bell,
  Bot,
  Settings as SettingsIcon,
  LogOut,
  Calendar,
  RefreshCw,
  Search,
  Target,
  Repeat,
} from 'lucide-react'
import { useApp, type PageKey } from '@/lib/store'
import { clearReadKey } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const NAV: { key: PageKey; label: string; icon: typeof LayoutDashboard }[] = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'investigations', label: 'Investigations', icon: Search },
  { key: 'goals', label: 'Goals', icon: Target },
  { key: 'retention', label: 'Retention', icon: Repeat },
  { key: 'realtime', label: 'Realtime', icon: Activity },
  { key: 'events', label: 'Events', icon: MousePointerClick },
  { key: 'funnels', label: 'Funnels', icon: Filter },
  { key: 'ask', label: 'Ask AI', icon: Sparkles },
  { key: 'alerts', label: 'Alerts', icon: Bell },
  { key: 'mcp', label: 'Agent usage', icon: Bot },
  { key: 'revenue', label: 'Revenue', icon: DollarSign },
  { key: 'settings', label: 'Settings', icon: SettingsIcon },
]

export function Shell({ children }: { children: ReactNode }) {
  const { page, setPage, days, setDays, refresh, project, setProject } = useApp()

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <a href="#main" className="sr-only focus:not-sr-only">
        Skip to content
      </a>
      <aside className="flex w-full shrink-0 flex-col md:w-60 border-r border-slate-200 bg-white">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white">
            <img src="/mark.svg" alt="" className="h-8 w-8" />
          </div>
          <div>
            <div className="text-sm font-bold leading-none">Metricairn</div>
            <div className="mt-0.5 max-w-[140px] truncate text-[11px] text-slate-500">
              {project?.name}
            </div>
          </div>
        </div>
        <nav
          aria-label="Main navigation"
          className="flex gap-1 overflow-x-auto px-3 pb-3 md:block md:flex-1 md:space-y-0.5 md:pb-0"
        >
          {NAV.map((item) => (
            <button
              key={item.key}
              aria-current={page === item.key ? 'page' : undefined}
              onClick={() => setPage(item.key)}
              className={cn(
                'flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors md:w-full',
                page === item.key
                  ? 'bg-slate-900 font-medium text-white'
                  : 'text-slate-600 hover:bg-slate-100',
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </button>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-3">
          <button
            onClick={() => {
              clearReadKey()
              setProject(null)
            }}
            className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-slate-500 hover:bg-slate-100"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap gap-3 items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:px-6">
          <h1 className="text-lg font-semibold capitalize">
            {page === 'mcp' ? 'Agent usage' : page === 'ask' ? 'Ask AI' : page}
          </h1>
          <div className="flex items-center gap-2">
            <button
              aria-label="Refresh analytics"
              onClick={refresh}
              className="rounded p-2 hover:bg-slate-100"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
            <Calendar className="h-4 w-4 text-slate-400" />
            <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Last 7 days</SelectItem>
                <SelectItem value="30">Last 30 days</SelectItem>
                <SelectItem value="90">Last 90 days</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </header>
        <main id="main" className="flex-1 p-4 md:p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
