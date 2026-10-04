import { useState } from 'react'
import { Bot, ArrowRight, Loader2 } from 'lucide-react'
import { api, setReadKey, setManagementKey, type ProjectCreated } from '@/lib/api'
import { useApp } from '@/lib/store'
import { Button } from '@/components/ui/button'
import { Input, Label } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { FetchError } from '@/components/FetchError'

export function Login({ initialError = '' }: { initialError?: string }) {
  const { setProject, setPage } = useApp()
  const [creating, setCreating] = useState(false)
  const [key, setKey] = useState('')
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('')
  const [token, setToken] = useState('')
  const [created, setCreated] = useState<ProjectCreated | null>(null)
  const [error, setError] = useState(initialError)
  const [loading, setLoading] = useState(false)
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (creating) {
        setCreated(await api.createProject(name.trim(), domain.trim(), token))
      } else {
        const project = await api.me(key.trim())
        setReadKey(key.trim())
        setProject(project)
        setPage('overview')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection failed')
    } finally {
      setLoading(false)
    }
  }
  function enter() {
    if (!created) return
    setReadKey(created.read_key)
    setManagementKey(created.management_key)
    sessionStorage.setItem('metricairn_tracker_key', created.write_key)
    setProject({ project_id: created.id, name: created.name, domain: created.domain })
    setPage('settings')
  }
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-900 text-white">
            <Bot />
          </div>
          <CardTitle className="text-2xl">Metricairn</CardTitle>
          <CardDescription>
            Free, self-hosted product analytics. Investigate traffic and conversion with the same
            evidence in your dashboard and AI agent.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {created ? (
            <div className="space-y-3">
              <p className="font-medium">Save your keys before continuing</p>
              <p className="text-xs text-slate-500">
                Keys cannot be recovered from the server. The tracking key is public; keep the read
                and management keys private.
              </p>
              {[
                ['Tracking key', created.write_key],
                ['Read key', created.read_key],
                ['Management key', created.management_key],
              ].map(([label, value]) => (
                <div key={label}>
                  <Label>{label}</Label>
                  <Input
                    readOnly
                    value={value}
                    className="font-mono text-xs"
                    onFocus={(e) => e.target.select()}
                  />
                </div>
              ))}
              <Button onClick={enter} className="w-full">
                Continue to installation <ArrowRight />
              </Button>
            </div>
          ) : (
            <>
              <div className="flex gap-2">
                <Button
                  variant={creating ? 'outline' : 'default'}
                  onClick={() => {
                    setCreating(false)
                    setError('')
                  }}
                >
                  Connect project
                </Button>
                <Button
                  variant={creating ? 'default' : 'outline'}
                  onClick={() => {
                    setCreating(true)
                    setError('')
                  }}
                >
                  Create project
                </Button>
              </div>
              <form onSubmit={submit} className="space-y-3">
                {creating ? (
                  <>
                    <div>
                      <Label htmlFor="name">Project name</Label>
                      <Input
                        id="name"
                        required
                        maxLength={200}
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="My SaaS"
                      />
                    </div>
                    <div>
                      <Label htmlFor="domain">Website domain</Label>
                      <Input
                        id="domain"
                        maxLength={300}
                        value={domain}
                        onChange={(e) => setDomain(e.target.value)}
                        placeholder="example.com"
                      />
                    </div>
                    <div>
                      <Label htmlFor="token">Provisioning token (if required by your server)</Label>
                      <Input
                        id="token"
                        type="password"
                        value={token}
                        onChange={(e) => setToken(e.target.value)}
                        autoComplete="off"
                      />
                    </div>
                  </>
                ) : (
                  <div>
                    <Label htmlFor="key">Private read key</Label>
                    <Input
                      id="key"
                      type="password"
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                      placeholder="alr_…"
                      className="font-mono"
                      autoComplete="off"
                    />
                  </div>
                )}
                <FetchError error={error} />
                <Button
                  type="submit"
                  className="w-full"
                  disabled={loading || !(creating ? name.trim() : key.trim())}
                >
                  {loading ? (
                    <Loader2 className="animate-spin" />
                  ) : creating ? (
                    'Create project'
                  ) : (
                    'Connect'
                  )}{' '}
                  <ArrowRight />
                </Button>
              </form>
              <button
                onClick={() => setPage('demo')}
                className="text-sm font-medium underline underline-offset-4"
              >
                Explore the simulated Billwise demo →
              </button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
