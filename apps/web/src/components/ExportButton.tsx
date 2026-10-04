import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function ExportButton({ rows, name }: { rows: object[]; name: string }) {
  function download() {
    const fields = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
    function cell(value: unknown) {
      const raw =
        value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)
      // Protect spreadsheet users from formula injection in customer-controlled fields.
      const safe =
        typeof value === 'string' && (/^[=+\-@]/.test(raw.trimStart()) || /^[\t\r\n]/.test(raw))
          ? `'${raw}`
          : raw
      return `"${safe.replaceAll('"', '""')}"`
    }
    const csv = [
      fields.map(cell).join(','),
      ...rows.map((row) =>
        fields.map((field) => cell((row as Record<string, unknown>)[field])).join(','),
      ),
    ].join('\r\n')
    const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${name}.csv`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <Button variant="outline" size="sm" disabled={!rows.length} onClick={download}>
      <Download className="h-3.5 w-3.5" /> Export CSV
    </Button>
  )
}
