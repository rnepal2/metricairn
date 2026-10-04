import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function FetchError({ error, retry }: { error: string; retry?: () => void }) {
  if (!error) return null
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span className="flex-1">{error}</span>
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  )
}
