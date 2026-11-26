import { describe, expect, it } from 'vitest'
import { formatRelative } from '@/utils/format'

const NOW = Date.parse('2026-11-26T12:00:00Z')
const ago = (seconds: number): string => new Date(NOW - seconds * 1000).toISOString()

describe('formatRelative', () => {
  it('says "just now" for the last seconds', () => {
    expect(formatRelative(ago(10), 'de', NOW)).toBe('gerade eben')
    expect(formatRelative(ago(10), 'en', NOW)).toBe('just now')
  })

  it('uses the largest fitting unit', () => {
    expect(formatRelative(ago(5 * 60), 'en', NOW)).toMatch(/5 min/)
    expect(formatRelative(ago(3 * 3600), 'en', NOW)).toMatch(/3 h/)
    expect(formatRelative(ago(2 * 86400), 'en', NOW)).toMatch(/2 days/)
  })

  it('works for the future', () => {
    expect(formatRelative(new Date(NOW + 10 * 60 * 1000).toISOString(), 'en', NOW)).toMatch(/in 10 min/)
  })

  it('shows the date for anything older than a week', () => {
    expect(formatRelative(ago(30 * 86400), 'de', NOW)).toMatch(/\d{2}\.\d{2}\.\d{2}/)
  })

  it('handles missing values', () => {
    expect(formatRelative(null, 'de', NOW)).toBe('—')
    expect(formatRelative('kaputt', 'de', NOW)).toBe('—')
  })
})
