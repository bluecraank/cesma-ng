import { describe, expect, it } from 'vitest'
import { useTableSort } from '@/composables/useTableSort'

const rows = [
  { name: '1/1/10', ip: '10.0.0.10', macs: 3 },
  { name: '1/1/9', ip: '10.0.0.9', macs: null },
  { name: '1/1/2', ip: null, macs: 12 },
]
const columns = { name: (r: (typeof rows)[number]) => r.name, ip: (r: (typeof rows)[number]) => r.ip, macs: (r: (typeof rows)[number]) => r.macs }

describe('useTableSort', () => {
  it('keeps the given order until a column is chosen', () => {
    const { sorted } = useTableSort(() => rows, columns)
    expect(sorted.value.map((r) => r.name)).toEqual(['1/1/10', '1/1/9', '1/1/2'])
  })

  it('sorts text naturally and toggles the direction', () => {
    const { sort, sorted } = useTableSort(() => rows, columns, 'name')
    expect(sorted.value.map((r) => r.name)).toEqual(['1/1/2', '1/1/9', '1/1/10'])
    sort.toggle('name')
    expect(sorted.value.map((r) => r.name)).toEqual(['1/1/10', '1/1/9', '1/1/2'])
  })

  it('keeps empty values at the bottom in both directions', () => {
    const { sort, sorted } = useTableSort(() => rows, columns, 'macs')
    expect(sorted.value.map((r) => r.macs)).toEqual([3, 12, null])
    sort.toggle('macs')
    expect(sorted.value.map((r) => r.macs)).toEqual([12, 3, null])
    sort.toggle('ip')
    expect(sorted.value.map((r) => r.ip)).toEqual(['10.0.0.9', '10.0.0.10', null])
  })
})
