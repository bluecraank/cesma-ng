import { describe, expect, it } from 'vitest'
import { textColumnMatcher, vlanColumnMatcher } from '@/utils/columnFilter'

const names: Record<number, string> = { 555: 'Drucker', 10: 'Clients' }
const nameOf = (vid: number): string | undefined => names[vid]

describe('vlanColumnMatcher', () => {
  it('matches a single VLAN exactly', () => {
    expect(vlanColumnMatcher('555')([555])).toBe(true)
    expect(vlanColumnMatcher('10')([100])).toBe(false)
    expect(vlanColumnMatcher('10')([10, 20])).toBe(true)
  })

  it('takes lists, ranges and names', () => {
    expect(vlanColumnMatcher('10, 20-29')([25])).toBe(true)
    expect(vlanColumnMatcher('10, 20-29')([30])).toBe(false)
    expect(vlanColumnMatcher('druck', nameOf)([555])).toBe(true)
  })

  it('negates with "!" and finds ports without VLAN with "-"', () => {
    expect(vlanColumnMatcher('!555')([555])).toBe(false)
    expect(vlanColumnMatcher('!555')([10])).toBe(true)
    expect(vlanColumnMatcher('-')([])).toBe(true)
    expect(vlanColumnMatcher('-')([10])).toBe(false)
  })
})

describe('textColumnMatcher', () => {
  it('contains, case-insensitive, "!" excludes', () => {
    expect(textColumnMatcher('ap')('AP-Flur')).toBe(true)
    expect(textColumnMatcher('!ap')('AP-Flur')).toBe(false)
    expect(textColumnMatcher('')(null)).toBe(true)
  })
})
