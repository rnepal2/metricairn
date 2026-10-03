import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function fmtNum(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '—'
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(n)
}

export function fmtPct(r: number | undefined | null): string {
  if (r == null || Number.isNaN(r)) return '—'
  return `${(r * 100).toFixed(1)}%`
}

export function fmtMoney(n: number | undefined | null, currency = 'USD'): string {
  if (n == null || Number.isNaN(n)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n)
}

export function fmtDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function rangeFor(days: number): { date_from: string; date_to: string } {
  const to = new Date()
  const from = new Date(to.getTime() - days * 24 * 3600 * 1000)
  return { date_from: from.toISOString(), date_to: to.toISOString() }
}
