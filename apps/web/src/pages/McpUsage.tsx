import { Bot, MessageSquare } from 'lucide-react'
import { api } from '@/lib/api'
import { useApp } from '@/lib/store'
import { useFetch } from '@/lib/useFetch'
import { fmtNum, fmtPct } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Skeleton, Badge } from '@/components/ui/badge'
import { BarListChart } from '@/components/charts/charts'

/** Direction-2 analytics: how AI agents are using this project's MCP server. */
export function McpUsage() {
  const { query } = useApp()
  const u = useFetch(() => api.mcpUsage(query), [query])

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Bot className="h-4 w-4" /> Agent usage</CardTitle>
          <CardDescription>
            AgentLens observes its own MCP server: which tools your agents call, how often they fail,
            and what they ask. Analytics for your agents, by your agents.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {u.loading ? <Skeleton className="h-24" /> : u.data ? (
            <div className="grid grid-cols-2 gap-4">
              <div><div className="text-xs text-slate-500">MCP tool calls</div><div className="text-2xl font-bold">{fmtNum(u.data.total_tool_calls)}</div></div>
              <div><div className="text-xs text-slate-500">Questions asked</div><div className="text-2xl font-bold">{fmtNum(u.data.questions_asked)}</div></div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Tool calls</CardTitle></CardHeader>
          <CardContent>
            {u.loading ? <Skeleton className="h-64" /> : (
              <BarListChart data={(u.data?.by_tool || []) as unknown as Record<string, unknown>[]} xKey="tool" yKey="calls" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Tool health</CardTitle></CardHeader>
          <CardContent>
            {u.loading ? <Skeleton className="h-40" /> : (
              <div className="space-y-2">
                {(u.data?.by_tool || []).map((t) => (
                  <div key={t.tool} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-xs">{t.tool}</span>
                    <span className="flex items-center gap-2 text-xs text-slate-500">
                      {t.avg_ms}ms avg
                      <Badge variant={t.error_rate > 0.05 ? 'danger' : 'success'}>{fmtPct(t.error_rate)} errors</Badge>
                    </span>
                  </div>
                ))}
                {(u.data?.by_tool || []).length === 0 && <p className="text-xs text-slate-400">No MCP tool calls yet — connect the server in Settings.</p>}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><MessageSquare className="h-4 w-4" /> Recent agent questions</CardTitle></CardHeader>
        <CardContent>
          {u.loading ? <Skeleton className="h-32" /> : (
            <div className="space-y-1.5">
              {(u.data?.recent_questions || []).map((q, i) => (
                <div key={i} className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">"{q}"</div>
              ))}
              {(u.data?.recent_questions || []).length === 0 && <p className="text-xs text-slate-400">No questions asked yet.</p>}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
