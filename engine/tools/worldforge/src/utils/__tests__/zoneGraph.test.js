import { describe, expect, it } from "vitest";
import {
  dedupeMutualBidirectionalEdges,
  oppositeDir,
  resolveExitDestination,
} from "../zoneGraph.js";

describe("oppositeDir", () => {
  it("maps all cardinal and vertical directions", () => {
    expect(oppositeDir("north")).toBe("south");
    expect(oppositeDir("SOUTH")).toBe("north");
    expect(oppositeDir("northeast")).toBe("southwest");
    expect(oppositeDir("up")).toBe("down");
  });

  it("returns null for unknown directions instead of inventing one", () => {
    expect(oppositeDir("portal")).toBeNull();
    expect(oppositeDir("")).toBeNull();
  });
});

describe("resolveExitDestination", () => {
  const known = new Set(["z1:room_a", "z1:room_b"]);
  it("resolves bare slugs within the zone", () => {
    expect(resolveExitDestination("z1", "room_a", known)).toBe("z1:room_a");
  });
  it("accepts fully-qualified known ids and rejects unknown ones", () => {
    expect(resolveExitDestination("z1", "z1:room_b", known)).toBe("z1:room_b");
    expect(resolveExitDestination("z1", "z2:elsewhere", known)).toBeNull();
    expect(resolveExitDestination("z1", "missing", known)).toBeNull();
  });
});

describe("dedupeMutualBidirectionalEdges", () => {
  it("collapses mutual A<->B edges to one and keeps one-way edges", () => {
    const edges = [
      { id: "a|north|b", source: "a", target: "b", data: { direction: "north" } },
      { id: "b|south|a", source: "b", target: "a", data: { direction: "south" } },
      { id: "a|east|c", source: "a", target: "c", data: { direction: "east" } },
    ];
    const out = dedupeMutualBidirectionalEdges(edges);
    const pairs = out.map((e) => [e.source, e.target].sort().join("-"));
    expect(pairs.filter((p) => p === "a-b")).toHaveLength(1);
    expect(pairs).toContain("a-c");
  });
});
