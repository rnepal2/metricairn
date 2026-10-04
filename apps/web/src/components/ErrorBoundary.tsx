import { Component, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main className="mx-auto max-w-lg space-y-4 p-8">
        <h1 className="text-xl font-semibold">This view couldn’t load</h1>
        <p className="text-sm text-slate-500">
          Reload to reconnect. If the problem persists, include your version and reproduction steps
          in a bug report.
        </p>
        <Button onClick={() => window.location.reload()}>Reload dashboard</Button>
      </main>
    )
  }
}
