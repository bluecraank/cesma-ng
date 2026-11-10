/**
 * Readable manufacturer names from the IEEE OUI list:
 * "KONICA MINOLTA HOLDINGS, INC." → "Konica Minolta", "Mitel Networks Corporation" → "Mitel Networks".
 */

const LEGAL = /[\s,]+(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|l\.l\.c|gmbh|ag|kg|s\.?a|b\.?v|plc|pte|pty|oy|ab|holdings?|group)\.?$/i
const AND_CO = /[\s,]+(&|and)\s*co\.?$/i

function titleCase(word: string): string {
  // keep short acronyms and words with digits as they are (HP, AVM, D-Link, 3Com)
  if (word.length <= 3 || /\d/.test(word)) return word
  return word
    .split('-')
    .map((part) => (part.length <= 2 ? part : part[0] + part.slice(1).toLowerCase()))
    .join('-')
}

export function shortVendor(name: string | null | undefined): string {
  if (!name) return ''
  let result = name.trim()
  for (let i = 0; i < 4; i++) {
    const next = result.replace(AND_CO, '').replace(LEGAL, '').trim()
    if (next === result || !next) break
    result = next
  }
  result = result.replace(/[,.\s]+$/, '')
  // all upper case (as in the IEEE list): Title Case
  if (result === result.toUpperCase() && /[A-Z]{4}/.test(result)) result = result.split(/\s+/).map(titleCase).join(' ')
  return result || name
}

export interface ConnectedLike {
  mac_address: string
  vendor?: string | null
  ip_address?: string | null
  hostname?: string | null
}

/** Main label and detail line for a connected device: best name first, the rest as detail. */
export function deviceLabel(c: ConnectedLike): { title: string; detail: string } {
  const vendor = shortVendor(c.vendor)
  if (c.hostname) return { title: c.hostname, detail: [c.ip_address, c.mac_address, vendor].filter(Boolean).join(' · ') }
  if (c.ip_address) return { title: c.ip_address, detail: [c.mac_address, vendor].filter(Boolean).join(' · ') }
  if (vendor) return { title: vendor, detail: c.mac_address }
  return { title: c.mac_address, detail: '' }
}
