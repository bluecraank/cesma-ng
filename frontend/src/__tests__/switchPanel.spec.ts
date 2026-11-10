import { describe, expect, it } from "vitest";
import { panelLayout, portLabel } from "@/utils/switchPanel";

const ports = (names: string[]) =>
  names.map((name, i) => ({ name, if_index: i + 1 }));
const names = (col: [{ name: string } | null, { name: string } | null]) =>
  col.map((p) => p?.name ?? null);

describe("panelLayout", () => {
  it("puts odd ports on top and even ports below, 48 next to 47", () => {
    const [unit] = panelLayout(
      ports(Array.from({ length: 48 }, (_, i) => String(i + 1))),
    );
    const block = unit!.blocks[0]!;
    expect(block.columns).toHaveLength(24);
    expect(names(block.columns[0]!)).toEqual(["1", "2"]);
    expect(names(block.columns[23]!)).toEqual(["47", "48"]);
  });

  it("separates the uplink slots of a plain numbered switch", () => {
    const [unit] = panelLayout(
      ports(Array.from({ length: 52 }, (_, i) => String(i + 1))),
    );
    expect(unit!.blocks.map((b) => b.columns.length)).toEqual([24, 2]);
    expect(names(unit!.blocks[1]!.columns[0]!)).toEqual(["49", "50"]);
  });

  it("groups Dell interface names by type and stack unit", () => {
    const list = [
      ...Array.from({ length: 48 }, (_, i) => `Gi1/0/${i + 1}`),
      ...Array.from({ length: 4 }, (_, i) => `Te1/0/${i + 1}`),
      ...Array.from({ length: 48 }, (_, i) => `Gi2/0/${i + 1}`),
    ];
    const units = panelLayout(ports(list));
    expect(units.map((u) => u.unit)).toEqual(["1", "2"]);
    expect(units[0]!.blocks.map((b) => b.columns.length)).toEqual([24, 2]);
    expect(names(units[1]!.blocks[0]!.columns[1]!)).toEqual([
      "Gi2/0/3",
      "Gi2/0/4",
    ]);
  });

  it("leaves gaps for missing port numbers", () => {
    const [unit] = panelLayout(ports(["1", "2", "4"]));
    expect(unit!.blocks[0]!.columns.map(names)).toEqual([
      ["1", "2"],
      [null, "4"],
    ]);
  });

  it("places breakout ports at their physical position", () => {
    const [unit] = panelLayout(
      ports([
        "ethernet1/1/3",
        "ethernet1/1/4",
        "ethernet1/1/1:1",
        "ethernet1/1/2:1",
        "ethernet1/1/1:2",
      ]),
    );
    expect(unit!.blocks[0]!.columns.map(names)).toEqual([
      ["ethernet1/1/1:1", "ethernet1/1/2:1"],
      ["ethernet1/1/3", "ethernet1/1/4"],
    ]);
    expect(names(unit!.blocks[1]!.columns[0]!)).toEqual([
      "ethernet1/1/1:2",
      null,
    ]);
    expect([
      portLabel("ethernet1/1/1:1"),
      portLabel("ethernet1/1/1:2"),
      portLabel("Gi1/0/7"),
    ]).toEqual(["1", "1:2", "7"]);
  });
});
