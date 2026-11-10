import { describe, expect, it } from 'vitest'
import { starLayout } from '@/utils/starLayout'

const dist = (p: { x: number; y: number }) => Math.round(Math.hypot(p.x, p.y))

describe('starLayout', () => {
  const nodes = ['core', 'a', 'b', 'c', 'd', 'a1', 'a2', 'lonely']
  const edges: [string, string][] = [
    ['core', 'a'],
    ['core', 'b'],
    ['c', 'core'],
    ['core', 'd'],
    ['a', 'a1'],
    ['a', 'a2'],
    ['a', 'core'], // second link (e.g. LAG member) must not change anything
  ]

  it('puts the best connected switch in the centre and its neighbours on the first ring', () => {
    const { positions, roots } = starLayout(nodes, edges)
    expect(roots[0]).toBe('core')
    expect(positions.get('core')).toEqual({ x: 0, y: 0 })
    const ring = ['a', 'b', 'c', 'd'].map((n) => dist(positions.get(n)!))
    expect(new Set(ring).size).toBe(1)
    expect(dist(positions.get('a1')!)).toBeGreaterThan(ring[0]!)
  })

  it('is the same on every call, whatever the input order', () => {
    const one = starLayout(nodes, edges).positions
    const two = starLayout([...nodes].reverse(), [...edges].reverse()).positions
    expect([...two.entries()].sort()).toEqual([...one.entries()].sort())
  })

  it('honours a chosen centre', () => {
    const { positions, roots } = starLayout(nodes, edges, { root: 'a' })
    expect(roots[0]).toBe('a')
    expect(positions.get('a')).toEqual({ x: 0, y: 0 })
  })

  it('places switches without links below the star', () => {
    const { positions } = starLayout(nodes, edges)
    const maxY = Math.max(...['core', 'a', 'b', 'c', 'd', 'a1', 'a2'].map((n) => positions.get(n)!.y))
    expect(positions.get('lonely')!.y).toBeGreaterThan(maxY)
  })

  it('widens the ring when many switches hang off the core', () => {
    const many = Array.from({ length: 40 }, (_, i) => `s${String(i).padStart(2, '0')}`)
    const { positions } = starLayout(
      ['core', ...many],
      many.map((n) => ['core', n] as [string, string]),
      { spacing: 140 },
    )
    const a = positions.get('s00')!
    const b = positions.get('s01')!
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThanOrEqual(135)
  })

  it('never puts end devices in the centre, even when one switch has many of them', () => {
    const phones = Array.from({ length: 10 }, (_, i) => `ext${i}`)
    const { positions, roots } = starLayout([...nodes, ...phones], [...edges, ...phones.map((p) => ['b', p] as [string, string])], {
      leaves: phones,
    })
    expect(roots[0]).toBe('core')
    expect(dist(positions.get('ext0')!)).toBeGreaterThan(dist(positions.get('b')!))
  })
})
