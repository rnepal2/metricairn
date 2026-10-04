import { lazy, Suspense, useEffect, useState } from 'react'
import { api, getReadKey } from '@/lib/api'
import { AppProvider, useApp } from '@/lib/store'
import { Shell } from '@/components/layout/Shell'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Login } from '@/pages/Login'
const Overview = lazy(() =>
  import('@/pages/Overview').then((module) => ({ default: module.Overview })),
)
const Realtime = lazy(() =>
  import('@/pages/Realtime').then((module) => ({ default: module.Realtime })),
)
const Events = lazy(() => import('@/pages/Events').then((module) => ({ default: module.Events })))
const Revenue = lazy(() =>
  import('@/pages/Revenue').then((module) => ({ default: module.Revenue })),
)
const Funnels = lazy(() =>
  import('@/pages/Funnels').then((module) => ({ default: module.Funnels })),
)
const Ask = lazy(() => import('@/pages/Ask').then((module) => ({ default: module.Ask })))
const Alerts = lazy(() => import('@/pages/Alerts').then((module) => ({ default: module.Alerts })))
const McpUsage = lazy(() =>
  import('@/pages/McpUsage').then((module) => ({ default: module.McpUsage })),
)
const Settings = lazy(() =>
  import('@/pages/Settings').then((module) => ({ default: module.Settings })),
)
const Demo = lazy(() => import('@/pages/Demo').then((module) => ({ default: module.Demo })))
const Goals = lazy(() => import('@/pages/Goals').then((module) => ({ default: module.Goals })))
const Retention = lazy(() =>
  import('@/pages/Retention').then((module) => ({ default: module.Retention })),
)
const Investigations = lazy(() =>
  import('@/pages/Investigations').then((module) => ({ default: module.Investigations })),
)

function Router() {
  const { project, page, setProject } = useApp()
  const [restoreError, setRestoreError] = useState('')
  const [restoring, setRestoring] = useState(!!getReadKey())
  useEffect(() => {
    let active = true
    if (getReadKey())
      api
        .me()
        .then((value) => {
          if (active) setProject(value)
        })
        .catch((error) => {
          if (active)
            setRestoreError(error instanceof Error ? error.message : 'Could not restore project')
        })
        .finally(() => {
          if (active) setRestoring(false)
        })
    else setRestoring(false)
    return () => {
      active = false
    }
  }, [])
  if (restoring)
    return (
      <p className="p-8 text-sm text-slate-500" role="status">
        Connecting to your project…
      </p>
    )
  if (page === 'demo')
    return (
      <Suspense fallback={<p className="p-8">Loading demo…</p>}>
        <Demo />
      </Suspense>
    )
  if (!project) return <Login initialError={restoreError} />
  return (
    <Shell>
      <Suspense
        fallback={
          <p role="status" className="p-4 text-sm text-slate-500">
            Loading view…
          </p>
        }
      >
        {page === 'overview' && <Overview />}
        {page === 'goals' && <Goals />}
        {page === 'retention' && <Retention />}
        {page === 'investigations' && <Investigations />}
        {page === 'realtime' && <Realtime />}
        {page === 'events' && <Events />}
        {page === 'revenue' && <Revenue />}
        {page === 'funnels' && <Funnels />}
        {page === 'ask' && <Ask />}
        {page === 'alerts' && <Alerts />}
        {page === 'mcp' && <McpUsage />}
        {page === 'settings' && <Settings />}
      </Suspense>
    </Shell>
  )
}

export default function App() {
  return (
    <AppProvider>
      <ErrorBoundary>
        <Router />
      </ErrorBoundary>
    </AppProvider>
  )
}
