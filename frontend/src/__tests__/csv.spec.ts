import { beforeEach, describe, expect, it } from 'vitest'
import { useColumns } from '@/composables/useColumns'
import { csvDate, toCsv } from '@/utils/csv'

describe('toCsv', () => {
  it('separates with semicolons and ends every line', () => {
    expect(toCsv(['Port', 'MACs'], [['1/1/1', 3], ['1/1/2', null]])).toBe('Port;MACs\r\n1/1/1;3\r\n1/1/2;\r\n')
  })

  it('quotes separators, quotes and line breaks', () => {
    expect(toCsv(['a'], [['x;y'], ['say "hi"'], ['two\nlines']])).toBe('a\r\n"x;y"\r\n"say ""hi"""\r\n"two\nlines"\r\n')
  })

  it('defuses text that a spreadsheet would run as a formula', () => {
    expect(toCsv(['a'], [['=HYPERLINK("http://x")'], ['+1'], ['@cmd'], ['-uplink']])).toBe(
      'a\r\n"\'=HYPERLINK(""http://x"")"\r\n\'+1\r\n\'@cmd\r\n\'-uplink\r\n',
    )
  })

  it('leaves numbers alone, also negative ones', () => {
    expect(toCsv(['a'], [[-5], [true]])).toBe('a\r\n-5\r\ntrue\r\n')
  })
})

describe('csvDate', () => {
  it('formats local time and tolerates missing values', () => {
    expect(csvDate(new Date(2026, 10, 24, 9, 5).toISOString())).toBe('2026-11-24 09:05')
    expect(csvDate(null)).toBe('')
    expect(csvDate('nonsense')).toBe('')
  })
})

describe('useColumns', () => {
  beforeEach(() => localStorage.clear())

  it('shows everything by default and remembers hidden columns', () => {
    const cols = useColumns<'poe' | 'macs'>('test')
    expect(cols.shows('poe')).toBe(true)
    cols.toggle('poe')
    expect(cols.shows('poe')).toBe(false)
    expect(useColumns<'poe' | 'macs'>('test').shows('poe')).toBe(false)
    expect(useColumns<'poe' | 'macs'>('test').shows('macs')).toBe(true)
    cols.toggle('poe')
    expect(useColumns<'poe' | 'macs'>('test').shows('poe')).toBe(true)
  })

  it('applies the defaults only while nothing is stored', () => {
    expect(useColumns<'poe' | 'macs'>('other', ['macs']).shows('macs')).toBe(false)
  })
})
