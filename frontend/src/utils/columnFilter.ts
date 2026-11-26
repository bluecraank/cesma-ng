import { vlanMatcher } from '@/utils/vlanFilter'

/** "!foo": everything that does NOT match "foo". */
function split(query: string): { negate: boolean; q: string } {
  const trimmed = query.trim()
  const negate = trimmed.startsWith('!')
  return { negate, q: (negate ? trimmed.slice(1) : trimmed).trim().toLowerCase() }
}

/** Filter for a text column: contains, case-insensitive; "!" in front excludes. */
export function textColumnMatcher(query: string): (...values: (string | null | undefined)[]) => boolean {
  const { negate, q } = split(query)
  if (!q) return () => true
  return (...values) => values.some((v) => v?.toLowerCase().includes(q)) !== negate
}

/**
 * Filter for a VLAN column (a port has one or more VLANs there):
 * "555" exactly VLAN 555, "10, 20-29" any of these, "drucker" by VLAN name,
 * "!555" ports without VLAN 555, "-" ports without any VLAN in this column.
 */
export function vlanColumnMatcher(query: string, nameOf: (vid: number) => string | undefined = () => undefined): (vids: number[]) => boolean {
  const { negate, q } = split(query)
  if (!q) return () => true
  if (q === '-') return (vids) => !vids.length !== negate
  const one = /^\d+$/.test(q) ? Number(q) : null
  const search = vlanMatcher(q)
  const matches = one !== null ? (vid: number) => vid === one : (vid: number) => search(vid, nameOf(vid))
  return (vids) => vids.some(matches) !== negate
}
