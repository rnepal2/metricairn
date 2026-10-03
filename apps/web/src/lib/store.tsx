import { createContext, useContext, useState, type ReactNode } from 'react'
import { rangeFor } from '@/lib/utils'

export type PageKey =
  | 'overview' | 'realtime' | 'events' | 'revenue' | 'funnels' | 'ask' | 'alerts' | 'mcp' | 'settings'

interface AppState {
  page: PageKey
  setPage: (p: PageKey) => void
  days: number
  setDays: (d: number) => void
  query: string // ?date_from=..&date_to=..
  project: { project_id: string; name: string; domain: string } | null
  setProject: (p: { project_id: string; name: string; domain: string } | null) => void
}

const Ctx = createContext<AppState | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<PageKey>('overview')
  const [days, setDays] = useState(30)
  const [project, setProject] = useState<AppState['project']>(null)
  const { date_from, date_to } = rangeFor(days)
  const query = `date_from=${encodeURIComponent(date_from)}&date_to=${encodeURIComponent(date_to)}`
  return (
    <Ctx.Provider value={{ page, setPage, days, setDays, query, project, setProject }}>
      {children}
    </Ctx.Provider>
  )
}

export function useApp(): AppState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useApp outside provider')
  return ctx
}
