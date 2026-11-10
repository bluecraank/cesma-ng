/**
 * Deterministic star (radial tree) layout for the topology view.
 *
 * The root (core switch) sits in the centre, its neighbours on the first ring, their
 * neighbours further out, each subtree in its own angular wedge sized by its number of leaves.
 * Same input → same picture, independent of the order the API returns nodes and edges in.
 * Further connected groups and isolated switches are placed in a row below the main star.
 */

export interface Point {
  x: number
  y: number
}

export interface StarLayoutOptions {
  /** preferred centre; falls back to the best connected node */
  root?: string | null
  /** minimum distance between rings */
  ringStep?: number
  /** minimum distance between neighbouring nodes on a ring */
  spacing?: number
  /** end devices (e.g. other LLDP neighbours): never the centre, always at the outside */
  leaves?: Iterable<string>
}

type Adjacency = Map<string, string[]>

function adjacency(nodes: string[], edges: [string, string][]): Adjacency {
  const adj: Adjacency = new Map(nodes.map((n) => [n, []]))
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
  for (const start of [...adj.keys()].sort()) {
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
    result.push(group)
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

/** Links between hubs only (switches), leaving out end devices. */
function hubAdjacency(adj: Adjacency, leaves: Set<string>): Adjacency {
  return new Map([...adj].filter(([n]) => !leaves.has(n)).map(([n, list]) => [n, list.filter((m) => !leaves.has(m))]))
}

/** Best centre: most switch links, then most central, then name, so the choice is stable. */
function pickRoot(group: string[], adj: Adjacency, leaves: Set<string>, preferred?: string | null): string {
  if (preferred && group.includes(preferred)) return preferred
  const hubs = group.filter((n) => !leaves.has(n))
  if (hubs.length) {
    adj = hubAdjacency(adj, leaves)
    group = hubs
  }
  const far = new Map(group.map((n) => [n, farness(n, adj)]))
  return [...group].sort((a, b) => adj.get(b)!.length - adj.get(a)!.length || far.get(a)! - far.get(b)! || a.localeCompare(b))[0]!
}

interface Tree {
  children: Map<string, string[]>
  depth: Map<string, number>
}

/** Spanning tree: switches along switch links first, end devices hung off their nearest switch. */
function bfsTree(root: string, adj: Adjacency, leaves: Set<string>): Tree {
  const children = new Map<string, string[]>()
  const depth = new Map([[root, 0]])
  const add = (parent: string, child: string): void => {
    depth.set(child, depth.get(parent)! + 1)
    children.set(parent, [...(children.get(parent) ?? []), child])
  }
  // 1. switches, along switch-to-switch links
  let queue = [root]
  while (queue.length) {
    const n = queue.shift()!
    if (leaves.has(n)) continue
    for (const m of adj.get(n)!) {
      if (depth.has(m) || leaves.has(m)) continue
      add(n, m)
      queue.push(m)
    }
  }
  // 2. end devices at the nearest placed switch (and whatever is only reachable through them)
  queue = [...depth.keys()]
  while (queue.length) {
    const n = queue.shift()!
    for (const m of adj.get(n)!) {
      if (depth.has(m)) continue
      add(n, m)
      queue.push(m)
    }
  }
  return { children, depth }
}

/** Angular weight of a subtree: its outermost switches, plus a little room for end devices. */
function weight(node: string, tree: Tree, leaves: Set<string>, cache: Map<string, number>): number {
  const cached = cache.get(node)
  if (cached !== undefined) return cached
  const kids = tree.children.get(node) ?? []
  const hubs = kids.filter((k) => !leaves.has(k))
  const ends = kids.length - hubs.length
  const value = Math.max(1, hubs.reduce((sum, k) => sum + weight(k, tree, leaves, cache), 0) + ends / 4)
  cache.set(node, value)
  return value
}

/** End devices fan out around their switch, pointing away from the centre. */
function fan(at: Point, outward: number | null, ends: string[], spacing: number): Map<string, Point> {
  const result = new Map<string, Point>()
  if (!ends.length) return result
  const arc = outward === null ? 2 * Math.PI : Math.min((5 * Math.PI) / 3, Math.max(Math.PI / 2, ends.length * 0.35))
  const gap = spacing * 0.45
  const radius = Math.max(spacing * 0.7, (ends.length * gap) / arc)
  const start = (outward ?? -Math.PI / 2) - (outward === null ? 0 : arc / 2)
  const slot = outward === null ? arc / ends.length : ends.length > 1 ? arc / (ends.length - 1) : 0
  ends.forEach((n, i) => {
    const angle = outward !== null && ends.length === 1 ? outward : start + i * slot
    result.set(n, { x: Math.round(at.x + radius * Math.cos(angle)), y: Math.round(at.y + radius * Math.sin(angle)) })
  })
  return result
}

function radial(root: string, tree: Tree, leaves: Set<string>, ringStep: number, spacing: number): Map<string, Point> {
  const isHub = (n: string): boolean => !leaves.has(n)
  // rings must be wide enough for the switches on them
  const perDepth = new Map<number, number>()
  for (const [n, d] of tree.depth) if (isHub(n)) perDepth.set(d, (perDepth.get(d) ?? 0) + 1)
  let step = ringStep
  for (const [d, n] of perDepth) if (d > 0) step = Math.max(step, (n * spacing) / (2 * Math.PI * d))

  const cache = new Map<string, number>()
  const positions = new Map<string, Point>([[root, { x: 0, y: 0 }]])
  // start at the top (-90°) and go clockwise
  const place = (node: string, from: number, to: number, outward: number | null): void => {
    const kids = tree.children.get(node) ?? []
    const hubs = kids.filter(isHub)
    const total = hubs.reduce((sum, k) => sum + weight(k, tree, leaves, cache), 0)
    let start = from
    for (const child of hubs) {
      const share = ((to - from) * weight(child, tree, leaves, cache)) / total
      const angle = start + share / 2
      const r = tree.depth.get(child)! * step
      positions.set(child, { x: Math.round(r * Math.cos(angle)), y: Math.round(r * Math.sin(angle)) })
      place(child, start, start + share, angle)
      start += share
    }
    const ends = kids.filter((k) => !isHub(k))
    // around the centre: use the gaps between the switch wedges (or the full circle without switches)
    for (const [n, p] of fan(positions.get(node)!, outward, ends, spacing)) {
      positions.set(n, p)
      place(n, 0, 0, outward) // anything only reachable through an end device
    }
  }
  place(root, -Math.PI / 2, (3 * Math.PI) / 2, null)
  return positions
}

function bounds(points: Iterable<Point>): {
  minX: number
  maxX: number
  minY: number
  maxY: number
} {
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

export function starLayout(
  nodes: string[],
  edges: [string, string][],
  { root = null, ringStep = 260, spacing = 140, leaves: leafIds = [] }: StarLayoutOptions = {},
): { positions: Map<string, Point>; roots: string[] } {
  const adj = adjacency(nodes, edges)
  const leaves = new Set(leafIds)
  // biggest group first (the main star), then by name
  const groups = components(adj).sort((a, b) => b.length - a.length || a[0]!.localeCompare(b[0]!))
  const positions = new Map<string, Point>()
  const roots: string[] = []
  if (!groups.length) return { positions, roots }

  const [main, ...rest] = groups
  const mainRoot = pickRoot(main!, adj, leaves, root)
  roots.push(mainRoot)
  for (const [n, p] of radial(mainRoot, bfsTree(mainRoot, adj, leaves), leaves, ringStep, spacing)) positions.set(n, p)

  // smaller groups and single switches: side by side in a row below the main star
  let y = bounds(positions.values()).maxY + ringStep
  let x = bounds(positions.values()).minX
  const singles = rest.filter((g) => g.length === 1).map((g) => g[0]!)
  for (const group of rest.filter((g) => g.length > 1)) {
    const r = pickRoot(group, adj, leaves, root)
    roots.push(r)
    const local = radial(r, bfsTree(r, adj, leaves), leaves, ringStep * 0.75, spacing)
    const b = bounds(local.values())
    for (const [n, p] of local) positions.set(n, { x: x - b.minX + p.x, y: y - b.minY + p.y })
    x += b.maxX - b.minX + spacing * 1.5
  }
  if (singles.length) {
    if (rest.some((g) => g.length > 1)) y = bounds(positions.values()).maxY + ringStep * 0.75
    x = bounds(positions.values()).minX
    singles.forEach((n, i) => positions.set(n, { x: x + i * spacing, y }))
  }
  return { positions, roots }
}
