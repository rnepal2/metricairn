import { AppProvider, useApp } from '@/lib/store'
import { Shell } from '@/components/layout/Shell'
import { Login } from '@/pages/Login'
import { Overview } from '@/pages/Overview'
import { Realtime } from '@/pages/Realtime'
import { Events } from '@/pages/Events'
import { Revenue } from '@/pages/Revenue'
import { Funnels } from '@/pages/Funnels'
import { Ask } from '@/pages/Ask'
import { Alerts } from '@/pages/Alerts'
import { McpUsage } from '@/pages/McpUsage'
import { Settings } from '@/pages/Settings'

function Router() {
  const { project, page } = useApp()
  if (!project) return <Login />
  return (
    <Shell>
      {page === 'overview' && <Overview />}
      {page === 'realtime' && <Realtime />}
      {page === 'events' && <Events />}
      {page === 'revenue' && <Revenue />}
      {page === 'funnels' && <Funnels />}
      {page === 'ask' && <Ask />}
      {page === 'alerts' && <Alerts />}
      {page === 'mcp' && <McpUsage />}
      {page === 'settings' && <Settings />}
    </Shell>
  )
}

export default function App() {
  return (
    <AppProvider>
      <Router />
    </AppProvider>
  )
}
