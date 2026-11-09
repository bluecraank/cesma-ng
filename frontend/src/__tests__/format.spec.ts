import { describe, expect, it } from 'vitest'
import { formatUptime } from '@/utils/format'

describe('formatUptime', () => {
  it('handles missing values', () => expect(formatUptime(null)).toBe('—'))
  it('formats minutes', () => expect(formatUptime(125)).toBe('2m'))
  it('formats hours', () => expect(formatUptime(3 * 3600 + 60)).toBe('3h 1m'))
  it('formats days', () => expect(formatUptime(2 * 86400 + 5 * 3600)).toBe('2d 5h'))
})
