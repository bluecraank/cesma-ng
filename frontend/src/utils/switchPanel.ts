/**
 * Arrange ports like on the front of a switch: odd numbers in the top row, even numbers below,
 * so port 48 sits at the right end next to 47 instead of wrapping under port 8.
 *
 * Ports are grouped by the text before their number ("Gi1/0/", "Te1/0/", "ethernet1/1/", "")
 * and by stack unit. Extra uplink slots after a multiple of eight (1–48 + 49–52) become a
 * separate block, like the SFP cage on the real device. Breakout names ("ethernet1/1/5:1") sit
 * at the position of their physical port; further lanes of the same port are listed at the end.
 */

export interface PanelPortLike {
  name: string;
  if_index: number;
}

/** One column of the panel: top and bottom port (either may be missing). */
export type PanelColumn<P> = [P | null, P | null];

export interface PanelBlock<P> {
  key: string;
  columns: PanelColumn<P>[];
}

export interface PanelUnit<P> {
  unit: string;
  blocks: PanelBlock<P>[];
}

interface Parsed<P> {
  port: P;
  prefix: string;
  number: number;
  lane: number;
}

const NUMBERED = /^(.*?)(\d+)(?::(\d+))?$/;
const UNIT = /(\d+)\//;

function columns<P>(ports: Parsed<P>[]): PanelColumn<P>[] {
  const byNumber = new Map(ports.map((p) => [p.number, p.port]));
  const numbers = ports.map((p) => p.number);
  // start on an odd number so pairs are (1,2), (3,4), … like the labels on the device
  let first = Math.min(...numbers);
  if (first % 2 === 0) first -= 1;
  const last = Math.max(...numbers);
  const result: PanelColumn<P>[] = [];
  for (let n = first; n <= last; n += 2)
    result.push([byNumber.get(n) ?? null, byNumber.get(n + 1) ?? null]);
  return result;
}

/** Split 1–52 into 1–48 and 49–52. */
function splitExtras<P>(ports: Parsed<P>[]): Parsed<P>[][] {
  const max = Math.max(...ports.map((p) => p.number));
  const main = Math.floor(max / 8) * 8;
  if (max <= 8 || max % 8 === 0) return [ports];
  return [
    ports.filter((p) => p.number <= main),
    ports.filter((p) => p.number > main),
  ].filter((g) => g.length);
}

export function panelLayout<P extends PanelPortLike>(
  ports: P[],
): PanelUnit<P>[] {
  const groups = new Map<string, Parsed<P>[]>();
  const loose: P[] = [];
  for (const port of ports) {
    const match = NUMBERED.exec(port.name.trim());
    if (!match) {
      loose.push(port);
      continue;
    }
    const prefix = match[1]!;
    const list = groups.get(prefix) ?? [];
    list.push({
      port,
      prefix,
      number: Number(match[2]),
      lane: Number(match[3] ?? 0),
    });
    groups.set(prefix, list);
  }
  // one port per front panel position: the lowest breakout lane stays, the others go to the end
  for (const [prefix, list] of groups) {
    const kept = new Map<number, Parsed<P>>();
    for (const p of [...list].sort((a, b) => a.lane - b.lane)) {
      if (kept.has(p.number)) loose.push(p.port);
      else kept.set(p.number, p);
    }
    groups.set(prefix, [...kept.values()]);
  }

  const units = new Map<string, { order: number; blocks: PanelBlock<P>[] }>();
  const sorted = [...groups.entries()].sort(
    ([, a], [, b]) =>
      Math.min(...a.map((p) => p.port.if_index)) -
      Math.min(...b.map((p) => p.port.if_index)),
  );
  for (const [prefix, list] of sorted) {
    const unit = UNIT.exec(prefix)?.[1] ?? "1";
    const entry = units.get(unit) ?? { order: units.size, blocks: [] };
    splitExtras(list).forEach((part, i) =>
      entry.blocks.push({ key: `${prefix}#${i}`, columns: columns(part) }),
    );
    units.set(unit, entry);
  }
  if (loose.length) {
    const sortedLoose = [...loose].sort((a, b) => a.if_index - b.if_index);
    const cols: PanelColumn<P>[] = [];
    for (let i = 0; i < sortedLoose.length; i += 2)
      cols.push([sortedLoose[i] ?? null, sortedLoose[i + 1] ?? null]);
    const entry = units.get("1") ?? { order: units.size, blocks: [] };
    entry.blocks.push({ key: "other", columns: cols });
    units.set("1", entry);
  }
  return [...units.entries()]
    .sort(([, a], [, b]) => a.order - b.order)
    .map(([unit, { blocks }]) => ({ unit, blocks }));
}

/** Short label for the port square: the port number, with the lane for breakouts beyond the first. */
export function portLabel(name: string): string {
  const match = NUMBERED.exec(name.trim());
  if (!match) return name;
  return match[3] && match[3] !== "1" ? `${match[2]}:${match[3]}` : match[2]!;
}
