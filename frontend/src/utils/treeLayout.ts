/**
 * Deterministic layered layout for the topology view, built to avoid crossing lines
 * (the classic Sugiyama approach, without a layout library):
 *
 * 1. Layers: the root (core switch) at the top, every switch one LLDP hop further one layer
 *    lower. A switch that serves many switches of its own layer (e.g. a second core switch)
 *    moves those one layer down; links between similar switches of one layer stay horizontal.
 *    End devices are always one layer below their switch.
 * 2. Links over several layers get a bend point on every layer in between.
 * 3. Order within the layers: start from the spanning tree (no crossings at all), improve with
 *    barycenter sweeps and then by swapping neighbours while that removes crossings.
 * 4. Coordinates: keep the order, centre parents over their children.
 *
 * Same input → same picture, independent of the order the API returns nodes and edges in.
 * Further connected groups are placed to the right, switches without links in a row below.
 */

export interface Point {
  x: number
  y: number
}

export interface TreeLayoutOptions {
  /** preferred root (top); falls back to the best connected switch */
  root?: string | null
  /** vertical distance between layers */
  layerGap?: number
  /** horizontal room for one switch (its label) */
  spacing?: number
  /** end devices (e.g. other LLDP neighbours): never the root, always below their switch */
  leaves?: Iterable<string>
}

export interface TreeLayout {
  positions: Map<string, Point>
  /** bend points of links over several layers, key "a|b" (a < b), ordered from a to b */
  bends: Map<string, Point[]>
  roots: string[]
}

type Adjacency = Map<string, string[]>

export const edgeKey = (a: string, b: string): string => (a < b ? `${a}|${b}` : `${b}|${a}`)

function adjacency(nodes: string[], edges: [string, string][]): Adjacency {
  const adj: Adjacency = new Map([...new Set(nodes)].sort().map((n) => [n, []]))
  for (const [a, b] of edges) {
    if (a === b || !adj.has(a) || !adj.has(b)) continue
    if (!adj.get(a)!.includes(b)) adj.get(a)!.push(b)
    if (!adj.get(b)!.includes(a)) adj.get(b)!.push(a)
  }
  for (const list of adj.values()) list.sort()
  return adj
}

function components(adj: Adjacency): string[][] {
  const seen = new Set<string>()
  const result: string[][] = []
  for (const start of adj.keys()) {
    if (seen.has(start)) continue
    const group: string[] = []
    const queue = [start]
    seen.add(start)
    while (queue.length) {
      const n = queue.shift()!
      group.push(n)
      for (const m of adj.get(n)!) {
        if (seen.has(m)) continue
        seen.add(m)
        queue.push(m)
      }
    }
    result.push(group.sort())
  }
  return result
}

/** Sum of hop distances to all other nodes of the group (smaller = more central). */
function farness(start: string, adj: Adjacency): number {
  const depth = new Map([[start, 0]])
  const queue = [start]
  let sum = 0
  while (queue.length) {
    const n = queue.shift()!
    for (const m of adj.get(n)!) {
      if (depth.has(m)) continue
      depth.set(m, depth.get(n)! + 1)
      sum += depth.get(m)!
      queue.push(m)
    }
  }
  return sum
}

/** Links between switches only. */
function hubAdjacency(adj: Adjacency, leaves: Set<string>): Adjacency {
  return new Map([...adj].filter(([n]) => !leaves.has(n)).map(([n, list]) => [n, list.filter((m) => !leaves.has(m))]))
}

/** Best root: most switch links, then most central, then name, so the choice is stable. */
function pickRoot(group: string[], adj: Adjacency, leaves: Set<string>, preferred?: string | null): string {
  if (preferred && group.includes(preferred)) return preferred
  const hubs = group.filter((n) => !leaves.has(n))
  const candidates = hubs.length ? hubs : group
  const links = hubs.length ? hubAdjacency(adj, leaves) : adj
  const far = new Map(candidates.map((n) => [n, farness(n, links)]))
  return [...candidates].sort(
    (a, b) => links.get(b)!.length - links.get(a)!.length || far.get(a)! - far.get(b)! || a.localeCompare(b),
  )[0]!
}

/** Hops from the root: along switch links first, end devices at their nearest switch. */
function hops(root: string, adj: Adjacency, leaves: Set<string>): { depth: Map<string, number>; parent: Map<string, string> } {
  const depth = new Map([[root, 0]])
  const parent = new Map<string, string>()
  let queue = [root]
  while (queue.length) {
    const n = queue.shift()!
    for (const m of adj.get(n)!) {
      if (depth.has(m) || leaves.has(m)) continue
      depth.set(m, depth.get(n)! + 1)
      parent.set(m, n)
      queue.push(m)
    }
  }
  queue = [...depth.keys()]
  while (queue.length) {
    const n = queue.shift()!
    for (const m of adj.get(n)!) {
      if (depth.has(m)) continue
      depth.set(m, depth.get(n)! + 1)
      parent.set(m, n)
      queue.push(m)
    }
  }
  return { depth, parent }
}

/** Crossings between the links of two neighbouring layers (only the order matters). */
/**
 * Crossings between the links of two neighbouring layers (only the order matters):
 * sort by the upper end, then count the pairs whose lower ends are the other way round.
 */
function crossingsBetween(links: [string, string][], pos: Map<string, number>): number {
  if (links.length < 2) return 0
  const pairs = links.map(([a, b]) => [pos.get(a)!, pos.get(b)!] as const).sort((x, y) => x[0] - y[0] || x[1] - y[1])
  // Fenwick tree over the lower positions: how many earlier links end further right
  const size = Math.max(...pairs.map((p) => p[1])) + 2
  const tree = new Array<number>(size + 1).fill(0)
  let seen = 0
  let count = 0
  for (const [, lower] of pairs) {
    let atMost = 0
    for (let i = lower + 1; i > 0; i -= i & -i) atMost += tree[i]!
    count += seen - atMost
    for (let i = lower + 1; i <= size; i += i & -i) tree[i]! += 1
    seen++
  }
  return count
}

function layered(
  root: string,
  group: string[],
  adj: Adjacency,
  leaves: Set<string>,
  layerGap: number,
  spacing: number,
): { positions: Map<string, Point>; bends: Map<string, Point[]> } {
  const { depth, parent } = hops(root, adj, leaves)
  const hubLinks = (n: string): number => adj.get(n)!.filter((m) => !leaves.has(m)).length

  // --- 1. layers -------------------------------------------------------------------------
  // A link inside one hop level points from the clearly more central switch to the other one
  // (that one moves a layer down); between similar switches it stays a horizontal link.
  // total order: fewer hops first, then more switch links, then name
  const compare = (a: string, b: string): number =>
    depth.get(a)! - depth.get(b)! || hubLinks(b) - hubLinks(a) || a.localeCompare(b)
  const before = (a: string, b: string): boolean => compare(a, b) < 0
  const down = new Map<string, string[]>(group.map((n) => [n, []]))
  const horizontal: [string, string][] = []
  for (const a of group) {
    for (const b of adj.get(a)!) {
      if (a > b) continue
      const [u, v] = before(a, b) ? [a, b] : [b, a]
      const sameLevel = depth.get(u) === depth.get(v)
      const clearlyCentral = leaves.has(v) || hubLinks(u) >= 2 * hubLinks(v) + 1
      if (sameLevel && !clearlyCentral) horizontal.push([u, v])
      else down.get(u)!.push(v)
    }
  }
  const layer = new Map<string, number>()
  for (const n of [...group].sort(compare)) {
    const own = layer.get(n) ?? depth.get(n)!
    layer.set(n, own)
    for (const m of down.get(n)!) layer.set(m, Math.max(layer.get(m) ?? depth.get(m)!, own + 1))
  }
  // horizontal links whose ends ended up on different layers become normal links
  const flat: [string, string][] = []
  for (const [u, v] of horizontal) {
    if (layer.get(u) === layer.get(v)) flat.push([u, v])
    else down.get(layer.get(u)! < layer.get(v)! ? u : v)!.push(layer.get(u)! < layer.get(v)! ? v : u)
  }

  // --- 2. bend points for links over several layers -----------------------------------------
  // every link becomes a chain of segments between neighbouring layers
  const layerOf = new Map(layer)
  const chains = new Map<string, string[]>() // edgeKey -> nodes from the upper to the lower end
  const segments: [string, string][] = []
  for (const u of group) {
    for (const v of down.get(u)!) {
      const chain = [u]
      for (let l = layer.get(u)! + 1; l < layer.get(v)!; l++) {
        const dummy = `\u0000${edgeKey(u, v)}#${l}`
        layerOf.set(dummy, l)
        chain.push(dummy)
      }
      chain.push(v)
      for (let i = 0; i + 1 < chain.length; i++) segments.push([chain[i]!, chain[i + 1]!])
      chains.set(edgeKey(u, v), chain)
    }
  }
  const isDummy = (n: string): boolean => n.startsWith('\u0000')
  const width = (n: string): number => (isDummy(n) ? spacing * 0.2 : leaves.has(n) ? spacing * 0.5 : spacing)
  const gap = (a: string, b: string): number => (width(a) + width(b)) / 2
  const up = new Map<string, string[]>()
  const below = new Map<string, string[]>()
  for (const [a, b] of segments) {
    ;(below.get(a) ?? below.set(a, []).get(a)!).push(b)
    ;(up.get(b) ?? up.set(b, []).get(b)!).push(a)
  }

  // --- 3. order within the layers --------------------------------------------------------------
  // start: depth-first along the spanning tree, so a plain tree has no crossings
  const kids = new Map<string, string[]>()
  for (const [child, p] of parent) if (group.includes(child)) (kids.get(p) ?? kids.set(p, []).get(p)!).push(child)
  for (const list of kids.values()) list.sort((a, b) => Number(leaves.has(a)) - Number(leaves.has(b)) || a.localeCompare(b))
  const layerCount = Math.max(...layerOf.values()) + 1

  /** Layers in depth-first order of the spanning tree (with the current order of siblings). */
  const treeOrder = (): string[][] => {
    const index = new Map<string, number>()
    const visit = (n: string): void => {
      index.set(n, index.size)
      for (const k of kids.get(n) ?? []) visit(k)
    }
    visit(root)
    const key = (n: string): number => {
      if (!isDummy(n)) return index.get(n) ?? 0
      // a bend point sits where its link starts
      return (index.get(chains.get(n.slice(1, n.lastIndexOf('#')))![0]!) ?? 0) + 0.5
    }
    const result: string[][] = Array.from({ length: layerCount }, () => [])
    for (const n of layerOf.keys()) result[layerOf.get(n)!]!.push(n)
    return result.map((row) => row.sort((a, b) => key(a) - key(b) || a.localeCompare(b)))
  }

  const segmentsByLayer = Array.from({ length: layerCount }, (_, l) => segments.filter(([a]) => layerOf.get(a) === l))
  const flatByLayer = Array.from({ length: layerCount }, (_, l) => flat.filter(([a]) => layerOf.get(a) === l))

  const positionsOf = (o: string[][]): Map<string, number> => new Map(o.flatMap((l) => l.map((n, i) => [n, i] as const)))
  /** Crossings below layer l, plus nodes a horizontal link of layer l runs through. */
  const layerCost = (l: number, pos: Map<string, number>): number =>
    crossingsBetween(segmentsByLayer[l]!, pos) +
    flatByLayer[l]!.reduce((sum, [a, b]) => sum + Math.abs(pos.get(a)! - pos.get(b)!) - 1, 0)
  const totalCost = (o: string[][]): number => {
    const pos = positionsOf(o)
    let sum = 0
    for (let l = 0; l < layerCount; l++) sum += layerCost(l, pos)
    return sum
  }

  // Whole branches first ("sifting"): move every subtree (e.g. a distribution switch with all
  // its access switches) to the place among its siblings where the extra links cross least.
  // A fixed budget of tries keeps big sites fast and the result the same on every machine.
  let order = treeOrder()
  let cost = totalCost(order)
  let budget = 1500
  for (let pass = 0; pass < 4 && cost > 0 && budget > 0; pass++) {
    let improved = false
    for (const list of kids.values()) {
      if (list.length < 2) continue
      for (const moving of [...list]) {
        const rest = list.filter((k) => k !== moving)
        const from = list.indexOf(moving)
        let bestAt = from
        for (let at = 0; at <= rest.length && budget > 0; at++) {
          if (at === from) continue
          budget--
          list.splice(0, list.length, ...rest.slice(0, at), moving, ...rest.slice(at))
          const candidate = treeOrder()
          const c = totalCost(candidate)
          if (c < cost) {
            order = candidate
            cost = c
            bestAt = at
            improved = true
          }
        }
        list.splice(0, list.length, ...rest.slice(0, bestAt), moving, ...rest.slice(bestAt))
      }
    }
    if (!improved) break
  }

  let best = order.map((l) => [...l])
  let bestCost = totalCost(best)
  for (let sweep = 0; sweep < 16 && bestCost > 0; sweep++) {
    const downward = sweep % 2 === 0
    const layers = Array.from({ length: layerCount }, (_, i) => (downward ? i : layerCount - 1 - i)).slice(1)
    for (const l of layers) {
      const pos = positionsOf(order)
      const neighbours = downward ? up : below
      const key = new Map(
        order[l]!.map((n, i) => {
          const near = neighbours.get(n) ?? []
          return [n, near.length ? near.reduce((sum, m) => sum + pos.get(m)!, 0) / near.length : i] as const
        }),
      )
      const own = new Map(order[l]!.map((n, i) => [n, i]))
      order[l] = [...order[l]!].sort((a, b) => key.get(a)! - key.get(b)! || own.get(a)! - own.get(b)!)
    }
    const cost = totalCost(order)
    if (cost < bestCost) {
      best = order.map((l) => [...l])
      bestCost = cost
    }
  }
  order = best

  // Swap neighbours while that removes crossings. Swapping two neighbours only changes the
  // crossings between their own links, so only those are counted.
  const pos = positionsOf(order)
  const crossPair = (left: string, right: string, links: Map<string, string[]>): number => {
    let count = 0
    for (const a of links.get(left) ?? []) for (const b of links.get(right) ?? []) if (pos.get(a)! > pos.get(b)!) count++
    return count
  }
  const flatCost = (l: number): number => flatByLayer[l]!.reduce((sum, [a, b]) => sum + Math.abs(pos.get(a)! - pos.get(b)!) - 1, 0)
  for (let pass = 0; pass < 8; pass++) {
    let improved = false
    for (let l = 0; l < layerCount; l++) {
      const row = order[l]!
      for (let i = 0; i + 1 < row.length; i++) {
        const [u, v] = [row[i]!, row[i + 1]!]
        const flatBefore = flatCost(l)
        const now = crossPair(u, v, up) + crossPair(u, v, below)
        const swapped = crossPair(v, u, up) + crossPair(v, u, below)
        ;[row[i], row[i + 1]] = [v, u]
        pos.set(v, i)
        pos.set(u, i + 1)
        if (swapped + flatCost(l) < now + flatBefore) {
          improved = true
        } else {
          ;[row[i], row[i + 1]] = [u, v]
          pos.set(u, i)
          pos.set(v, i + 1)
        }
      }
    }
    if (!improved) break
  }

  // --- 4. coordinates -------------------------------------------------------------------------
  const at = new Map<string, Point>()
  order.forEach((row, l) => {
    let x = 0
    row.forEach((n, i) => {
      if (i) x += gap(row[i - 1]!, n)
      at.set(n, { x, y: l * layerGap })
    })
    for (const n of row) at.get(n)!.x -= x / 2
  })
  // closest positions to the middle of the neighbours that keep order and minimum distances
  const settle = (l: number, neighbours: Map<string, string[]>): void => {
    const row = order[l]!
    const want = row.map((n) => {
      const near = neighbours.get(n) ?? []
      return near.length ? near.reduce((sum, m) => sum + at.get(m)!.x, 0) / near.length : at.get(n)!.x
    })
    const left: number[] = []
    const right: number[] = []
    row.forEach((n, i) => (left[i] = i ? Math.max(want[i]!, left[i - 1]! + gap(row[i - 1]!, n)) : want[i]!))
    for (let i = row.length - 1; i >= 0; i--) {
      right[i] = i < row.length - 1 ? Math.min(want[i]!, right[i + 1]! - gap(row[i]!, row[i + 1]!)) : want[i]!
    }
    row.forEach((n, i) => (at.get(n)!.x = (left[i]! + right[i]!) / 2))
  }
  for (let round = 0; round < 6; round++) {
    for (let l = layerCount - 2; l >= 0; l--) settle(l, below) // parents over their children
    for (let l = 1; l < layerCount; l++) settle(l, up) // children under their parents
  }
  for (let l = layerCount - 2; l >= 0; l--) settle(l, below)

  const shift = at.get(root)!.x
  const point = (n: string): Point => ({ x: Math.round(at.get(n)!.x - shift), y: Math.round(at.get(n)!.y) })
  const positions = new Map(group.map((n) => [n, point(n)]))
  const bends = new Map<string, Point[]>()
  for (const [key, chain] of chains) {
    if (chain.length < 3) continue
    const inner = chain.slice(1, -1).map(point)
    bends.set(key, key.startsWith(`${chain[0]}|`) ? inner : inner.reverse())
  }
  return { positions, bends }
}

function bounds(points: Iterable<Point>): { minX: number; maxX: number; minY: number; maxY: number } {
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const p of points) {
    minX = Math.min(minX, p.x)
    maxX = Math.max(maxX, p.x)
    minY = Math.min(minY, p.y)
    maxY = Math.max(maxY, p.y)
  }
  return { minX, maxX, minY, maxY }
}

export function treeLayout(
  nodes: string[],
  edges: [string, string][],
  { root = null, layerGap = 170, spacing = 150, leaves: leafIds = [] }: TreeLayoutOptions = {},
): TreeLayout {
  const adj = adjacency(nodes, edges)
  const leaves = new Set(leafIds)
  // biggest group first (the main tree), then by name
  const groups = components(adj).sort((a, b) => b.length - a.length || a[0]!.localeCompare(b[0]!))
  const positions = new Map<string, Point>()
  const bends = new Map<string, Point[]>()
  const roots: string[] = []

  let x = 0
  for (const group of groups.filter((g) => g.length > 1)) {
    const r = pickRoot(group, adj, leaves, root)
    roots.push(r)
    const local = layered(r, group, adj, leaves, layerGap, spacing)
    const b = bounds([...local.positions.values(), ...[...local.bends.values()].flat()])
    const offset = positions.size ? x - b.minX : 0
    const move = (p: Point): Point => ({ x: p.x + offset, y: p.y })
    for (const [n, p] of local.positions) positions.set(n, move(p))
    for (const [k, list] of local.bends) bends.set(k, list.map(move))
    x = Math.max(bounds(positions.values()).maxX, ...[...bends.values()].flat().map((p) => p.x)) + spacing * 1.5
  }

  // switches without any link: in a row below everything else
  const singles = groups.filter((g) => g.length === 1).map((g) => g[0]!)
  if (singles.length) {
    const b = positions.size ? bounds(positions.values()) : { minX: 0, maxY: -layerGap }
    singles.forEach((n, i) => positions.set(n, { x: b.minX + i * spacing, y: b.maxY + layerGap }))
  }
  return { positions, bends, roots }
}

/** Number of pairs of straight lines that cross (lines sharing an end point do not count). */
export function countCrossings(lines: [Point, Point][]): number {
  const orient = (p: Point, q: Point, r: Point): number => Math.sign((q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x))
  const same = (p: Point, q: Point): boolean => p.x === q.x && p.y === q.y
  let crossings = 0
  for (let i = 0; i < lines.length; i++) {
    const [p1, p2] = lines[i]!
    for (let j = i + 1; j < lines.length; j++) {
      const [q1, q2] = lines[j]!
      if (same(p1, q1) || same(p1, q2) || same(p2, q1) || same(p2, q2)) continue
      if (orient(p1, p2, q1) * orient(p1, p2, q2) < 0 && orient(q1, q2, p1) * orient(q1, q2, p2) < 0) crossings++
    }
  }
  return crossings
}

/** The drawn lines of a layout: every link with its bend points, as straight pieces. */
export function layoutLines(layout: TreeLayout, edges: [string, string][]): [Point, Point][] {
  const lines: [Point, Point][] = []
  for (const key of new Set(edges.map(([a, b]) => edgeKey(a, b)))) {
    const [a, b] = key.split('|') as [string, string]
    const pts = [layout.positions.get(a)!, ...(layout.bends.get(key) ?? []), layout.positions.get(b)!]
    for (let i = 0; i + 1 < pts.length; i++) lines.push([pts[i]!, pts[i + 1]!])
  }
  return lines
}
