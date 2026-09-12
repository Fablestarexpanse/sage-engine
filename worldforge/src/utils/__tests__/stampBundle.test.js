import { describe, expect, it } from "vitest";
import {
  STAMP_ZONE_ID,
  buildLogicalSlugMap,
  buildStampRoomYaml,
} from "../stampBundle.js";

const PRESERVE_ALL = { descriptions: true, gameplay: true, internalExits: true, layoutExtras: true };

describe("buildLogicalSlugMap", () => {
  it("assigns stable r0..rN keys in sorted slug order, deduped", () => {
    const { logicalKeys, slugToLogical } = buildLogicalSlugMap(["beta", "alpha", "beta", null]);
    expect(logicalKeys).toEqual(["r0", "r1"]);
    expect(slugToLogical).toEqual({ alpha: "r0", beta: "r1" });
  });
});

describe("buildStampRoomYaml", () => {
  const map = { entry: "r0", hall: "r1" };
  const room = {
    id: "z1:entry",
    zone: "z1",
    description: { base: "A doorway." },
    entity_spawns: [{ template: "stalker" }],
    tags: ["lit"],
    exits: {
      north: { destination: "z1:hall", description: "To the hall." },
      south: { destination: "other_zone:elsewhere" },
      east: { destination: "z1:unknown_room" },
    },
  };

  it("rewrites identity to the stamp zone and remaps internal exits only", () => {
    const out = buildStampRoomYaml(room, "z1", "r0", map, PRESERVE_ALL);
    expect(out.id).toBe(`${STAMP_ZONE_ID}:r0`);
    expect(out.zone).toBe(STAMP_ZONE_ID);
    expect(out.exits.north.destination).toBe("r1");
    // cross-zone and unknown-slug exits are dropped, never leaked
    expect(out.exits.south).toBeUndefined();
    expect(out.exits.east).toBeUndefined();
  });

  it("strips gameplay and descriptions when preserve flags are off", () => {
    const out = buildStampRoomYaml(room, "z1", "r0", map, {
      descriptions: false,
      gameplay: false,
      internalExits: true,
      layoutExtras: false,
    });
    expect(out.description).toEqual({ base: "" });
    expect(out.entity_spawns).toEqual([]);
    expect(out.tags).toEqual([]);
    expect(out.exits.north.destination).toBe("r1");
    expect(out.exits.north.description).toBeUndefined();
  });

  it("does not mutate the source room", () => {
    const before = JSON.stringify(room);
    buildStampRoomYaml(room, "z1", "r0", map, PRESERVE_ALL);
    expect(JSON.stringify(room)).toBe(before);
  });
});
