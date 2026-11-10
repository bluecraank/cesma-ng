import { describe, expect, it } from 'vitest'
import { deviceLabel, shortVendor } from '@/utils/vendor'

describe('shortVendor', () => {
  it.each([
    ['KONICA MINOLTA HOLDINGS, INC.', 'Konica Minolta'],
    ['MITEL CORPORATION', 'Mitel'],
    ['Mitel Networks Corporation', 'Mitel Networks'],
    ['Hewlett Packard Enterprise', 'Hewlett Packard Enterprise'],
    ['AVM Audiovisuelles Marketing und Computersysteme GmbH', 'AVM Audiovisuelles Marketing und Computersysteme'],
    ['Dell Inc.', 'Dell'],
    ['TP-LINK TECHNOLOGIES CO.,LTD.', 'TP-Link Technologies'],
    ['Private', 'Private'],
  ])('%s → %s', (raw, short) => expect(shortVendor(raw)).toBe(short))

  it('handles missing values', () => expect(shortVendor(null)).toBe(''))
})

describe('deviceLabel', () => {
  it('prefers hostname, then IP, then manufacturer', () => {
    const mac = '00:20:6b:86:84:56'
    expect(deviceLabel({ mac_address: mac, vendor: 'KONICA MINOLTA HOLDINGS, INC.' })).toEqual({ title: 'Konica Minolta', detail: mac })
    expect(deviceLabel({ mac_address: mac, ip_address: '10.0.0.5', vendor: 'Dell Inc.' })).toEqual({ title: '10.0.0.5', detail: `${mac} · Dell` })
    expect(deviceLabel({ mac_address: mac, hostname: 'pc-01', ip_address: '10.0.0.5' }).title).toBe('pc-01')
  })
})
