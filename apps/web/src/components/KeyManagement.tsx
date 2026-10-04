import { useState } from 'react'
import { api, getManagementKey } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { Button } from '@/components/ui/button'
import { Input, Label } from '@/components/ui/input'
import { FetchError } from '@/components/FetchError'

export function KeyManagement({ revision }: { revision: boolean }) {
  const keys = useFetch(
    () => (getManagementKey() ? api.listKeys() : Promise.resolve([])),
    [revision],
  )
  const [name, setName] = useState('')
  const [kind, setKind] = useState<'read' | 'tracking' | 'management'>('read')
  const [issued, setIssued] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState('')
  async function issue() {
    setBusy(true)
    setError('')
    try {
      const result = await api.issueKey(name.trim(), kind)
      setIssued(result.key)
      setName('')
      await keys.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not issue key')
    } finally {
      setBusy(false)
    }
  }
  async function revoke(id: string) {
    setBusy(true)
    setError('')
    try {
      await api.revokeKey(id)
      setConfirm('')
      await keys.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not revoke key')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mt-5 space-y-3 border-t pt-4">
      <p className="text-sm font-medium">Rotate access keys</p>
      <p className="text-xs text-slate-500">
        Issue a replacement, update its consumers, then revoke the old key. A key is displayed only
        when issued.
      </p>
      <FetchError error={keys.error || error} />
      <div className="flex flex-wrap gap-2">
        <Input
          className="min-w-40 flex-1"
          aria-label="Key name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Production agent"
          maxLength={200}
        />
        <select
          aria-label="Key type"
          className="rounded border bg-white p-2 text-sm"
          value={kind}
          onChange={(e) => setKind(e.target.value as typeof kind)}
        >
          <option value="read">Read</option>
          <option value="tracking">Tracking</option>
          <option value="management">Management</option>
        </select>
        <Button disabled={busy || !name.trim() || !getManagementKey()} onClick={issue}>
          Issue key
        </Button>
      </div>
      {issued && (
        <div>
          <Label>New key · save privately before leaving</Label>
          <Input
            readOnly
            value={issued}
            className="font-mono text-xs"
            onFocus={(e) => e.target.select()}
          />
          <Button variant="ghost" size="sm" onClick={() => setIssued('')}>
            Hide
          </Button>
        </div>
      )}
      {(keys.data || []).map((key) => (
        <div
          key={key.id}
          className="flex flex-wrap items-center justify-between gap-2 rounded bg-slate-50 p-2 text-xs"
        >
          <span>
            {key.name} · {key.prefix}… · {key.scopes} {key.revoked ? '· revoked' : ''}
          </span>
          {!key.revoked && (
            <div className="flex gap-1">
              {confirm === key.id ? (
                <>
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={busy}
                    onClick={() => revoke(key.id)}
                  >
                    Confirm revocation
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirm('')}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button variant="outline" size="sm" onClick={() => setConfirm(key.id)}>
                  Revoke
                </Button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
