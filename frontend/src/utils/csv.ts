export type CsvCell = string | number | boolean | null | undefined

/**
 * Semicolon separated, as Excel expects it with German regional settings.
 * Text from switches and clients (descriptions, host names) is foreign input: a cell that would
 * start a formula is prefixed with an apostrophe so a spreadsheet shows it as text.
 */
function cell(value: CsvCell): string {
  if (value === null || value === undefined) return ''
  let text = String(value)
  if (typeof value === 'string' && /^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return /[";\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function toCsv(headers: string[], rows: CsvCell[][]): string {
  return [headers, ...rows].map((row) => row.map(cell).join(';')).join('\r\n') + '\r\n'
}

const pad = (n: number): string => String(n).padStart(2, '0')

/** Local time as "2026-11-24 09:30", which spreadsheets read as a date. */
export function csvDate(value: string | null | undefined): string {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Offers the rows as "<name>-<date>.csv" for download. */
export function downloadCsv(name: string, headers: string[], rows: CsvCell[][]): void {
  const now = new Date()
  const file = `${name.replace(/[^\w.-]+/g, '_')}-${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}.csv`
  // BOM: without it Excel reads umlauts wrongly
  const url = URL.createObjectURL(new Blob(['﻿', toCsv(headers, rows)], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = file
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
