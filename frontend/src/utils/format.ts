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

const RELATIVE_STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
]

/**
 * "vor 5 Min." / "in 3 Std." for times up to a week away; older ones as date and time.
 * ``now`` is passed in so a ticking clock can re-render it.
 */
export function formatRelative(value: string | null | undefined, locale: string, now: number = Date.now()): string {
  if (!value) return '—'
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return '—'
  let amount = (time - now) / 1000
  if (Math.abs(amount) < 45) return locale.startsWith('de') ? 'gerade eben' : 'just now'
  const format = new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'short' })
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(amount) < size) return format.format(Math.round(amount), unit)
    amount /= size
  }
  return formatDateTime(value, locale)
}
