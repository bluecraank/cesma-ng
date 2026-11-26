import { describe, expect, it } from 'vitest'
import { countCrossings, layoutLines, treeLayout } from '@/utils/treeLayout'

const crossings = (nodes: string[], edges: [string, string][], options = {}): number =>
  countCrossings(layoutLines(treeLayout(nodes, edges, options), edges))

describe('treeLayout', () => {
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

  it('puts the best connected switch at the top and every hop one layer lower', () => {
    const { positions, roots } = treeLayout(nodes, edges)
    expect(roots[0]).toBe('core')
    expect(positions.get('core')).toEqual({ x: 0, y: 0 })
    const first = ['a', 'b', 'c', 'd'].map((n) => positions.get(n)!.y)
    expect(new Set(first).size).toBe(1)
    expect(first[0]).toBeGreaterThan(0)
    expect(positions.get('a1')!.y).toBeGreaterThan(first[0]!)
  })

  it('is the same on every call, whatever the input order', () => {
    const one = treeLayout(nodes, edges).positions
    const two = treeLayout([...nodes].reverse(), [...edges].reverse()).positions
    expect([...two.entries()].sort()).toEqual([...one.entries()].sort())
  })

  it('honours a chosen top switch', () => {
    const { positions, roots } = treeLayout(nodes, edges, { root: 'a' })
    expect(roots[0]).toBe('a')
    expect(positions.get('a')).toEqual({ x: 0, y: 0 })
  })

  it('places switches without links below everything else', () => {
    const { positions } = treeLayout(nodes, edges)
    const maxY = Math.max(...['core', 'a', 'b', 'c', 'd', 'a1', 'a2'].map((n) => positions.get(n)!.y))
    expect(positions.get('lonely')!.y).toBeGreaterThan(maxY)
  })

  it('keeps switches on one layer apart', () => {
    const many = Array.from({ length: 40 }, (_, i) => `s${String(i).padStart(2, '0')}`)
    const { positions } = treeLayout(['core', ...many], many.map((n) => ['core', n] as [string, string]), { spacing: 140 })
    const xs = many.map((n) => positions.get(n)!.x).sort((a, b) => a - b)
    for (let i = 1; i < xs.length; i++) expect(xs[i]! - xs[i - 1]!).toBeGreaterThanOrEqual(139)
  })

  it('never puts end devices at the top, always below their switch', () => {
    const phones = Array.from({ length: 10 }, (_, i) => `ext${i}`)
    const { positions, roots } = treeLayout([...nodes, ...phones], [...edges, ...phones.map((p) => ['b', p] as [string, string])], {
      leaves: phones,
    })
    expect(roots[0]).toBe('core')
    expect(positions.get('ext0')!.y).toBeGreaterThan(positions.get('b')!.y)
  })

  it('draws a tree without crossings', () => {
    const n = ['core']
    const e: [string, string][] = []
    for (let i = 0; i < 4; i++) {
      n.push(`d${i}`)
      e.push(['core', `d${i}`])
      for (let j = 0; j < 5; j++) {
        n.push(`a${i}${j}`)
        e.push([`d${i}`, `a${i}${j}`])
      }
    }
    expect(crossings(n, e)).toBe(0)
  })

  it('orders branches so that extra links do not cross', () => {
    // every distribution switch also feeds one access switch of the branch three further on
    const n = ['core']
    const e: [string, string][] = []
    for (let i = 0; i < 8; i++) {
      n.push(`d${i}`)
      e.push(['core', `d${i}`])
      for (let j = 0; j < 6; j++) {
        const a = `a${i}_${j}`
        n.push(a)
        e.push([`d${i}`, a])
        if ((i * 6 + j) % 5 === 0) e.push([`d${(i + 3) % 8}`, a])
      }
    }
    expect(crossings(n, e)).toBe(0)
  })

  it('puts a second core switch between the core and the switches below both', () => {
    const n = ['c1', 'c2']
    const e: [string, string][] = [['c1', 'c2']]
    for (let i = 0; i < 6; i++) {
      n.push(`a${i}`)
      e.push(['c1', `a${i}`], ['c2', `a${i}`])
    }
    const layout = treeLayout(n, e)
    expect(layout.positions.get('c2')!.y).toBeGreaterThan(layout.positions.get('c1')!.y)
    expect(layout.positions.get('a0')!.y).toBeGreaterThan(layout.positions.get('c2')!.y)
    // links from the top switch to the bottom row bend on the layer in between
    expect(layout.bends.get('a0|c1')).toHaveLength(1)
  })
})
