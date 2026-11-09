export function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

export function formatDateTime(value: string | null | undefined, locale: string): string {
  if (!value) return '—'
  return new Date(value).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' })
}
