import { describe, expect, it } from 'vitest'
import { vlanMatcher } from '@/utils/vlanFilter'

describe('vlanMatcher', () => {
  it('matches everything without a query', () => {
    expect(vlanMatcher('  ')(10, 'Clients')).toBe(true)
  })

  it('searches the id from the start and the texts anywhere', () => {
    const m = vlanMatcher('10')
    expect(m(10, 'Clients')).toBe(true)
    expect(m(100, 'Server')).toBe(true)
    expect(m(210, 'Voice')).toBe(false)
    expect(m(5, 'Lab 10')).toBe(true)
    expect(vlanMatcher('VOI')(210, 'Voice', null)).toBe(true)
  })

  it('selects exactly the listed VLANs and ranges', () => {
    const m = vlanMatcher('10, 20-29;300')
    expect([10, 20, 25, 29, 300].every((vid) => m(vid))).toBe(true)
    expect([1, 19, 30, 100, 3000].some((vid) => m(vid, '10'))).toBe(false)
  })

  it('treats an open range as "from here upwards"', () => {
    const m = vlanMatcher('100-')
    expect(m(99)).toBe(false)
    expect(m(4000)).toBe(true)
  })
})
