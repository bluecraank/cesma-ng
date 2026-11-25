/**
 * Filter for VLAN lists. A list of numbers selects exactly these VLANs ("10, 20, 100-199"),
 * anything else is a search in the VLAN id (from the start) and the given texts.
 */
export function vlanMatcher(query: string): (vid: number, ...texts: (string | null | undefined)[]) => boolean {
  const q = query.trim().toLowerCase()
  if (!q) return () => true

  if (/^[\d\s,;-]+$/.test(q) && /[,;-]/.test(q)) {
    const ranges = q
      .split(/[,;\s]+/)
      .filter(Boolean)
      .map((part) => {
        const [from, to] = part.split('-').map((n) => (n === '' ? NaN : Number(n)))
        return { from: from ?? NaN, to: to ?? from ?? NaN }
      })
      // "10-" while typing: from 10 upwards
      .map((r) => ({ from: Number.isNaN(r.from) ? 1 : r.from, to: Number.isNaN(r.to) ? 4094 : r.to }))
    return (vid) => ranges.some((r) => vid >= r.from && vid <= r.to)
  }

  return (vid, ...texts) => String(vid).startsWith(q) || texts.some((text) => text?.toLowerCase().includes(q))
}
