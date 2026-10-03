import { useState } from 'react'
import { Bot, KeyRound, ArrowRight, Loader2 } from 'lucide-react'
import { api, setReadKey } from '@/lib/api'
import { useApp } from '@/lib/store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export function Login() {
  const { setProject, setPage } = useApp()
  const [key, setKey] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      setReadKey(key.trim())
      const me = await api.me()
      setProject(me)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-900 text-white">
            <Bot className="h-6 w-6" />
          </div>
          <CardTitle className="text-xl">AgentLens</CardTitle>
          <CardDescription>Privacy-friendly analytics your AI agent can query. Paste your read API key to continue.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-3">
            <div className="relative">
              <KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="alr_..."
                className="pl-9 font-mono"
                autoFocus
              />
            </div>
            {error && <p className="text-xs text-red-600">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading || !key.trim()}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Continue <ArrowRight /></>}
            </Button>
          </form>
          <p className="mt-4 text-center text-xs text-slate-500">
            No project yet? Create one via the API — see the README quickstart.
          </p>
          <div className="mt-2 text-center">
            <button
              type="button"
              onClick={() => setPage('demo')}
              className="text-xs font-medium text-slate-900 underline underline-offset-2 hover:text-slate-600"
            >
              or explore the Billwise live demo →
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
