import { describe, expect, it } from "vitest";
import { runZoneValidation, validationCounts } from "../validation.js";

const node = (id, raw = {}, extra = {}) => ({
  id: `z1:${id}`,
  data: { slug: id, label: id, raw, ...extra },
});

describe("runZoneValidation", () => {
  it("flags unknown entity templates in spawns", () => {
    const issues = runZoneValidation(
      [node("a", { entity_spawns: [{ template: "ghost" }] })],
      [],
      { zoneId: "z1", entityIds: ["stalker"] }
    );
    expect(issues.some((i) => i.msg.includes('Unknown entity template "ghost"'))).toBe(true);
  });

  it("accepts known templates and reports loot/prereq problems from ctx", () => {
    const issues = runZoneValidation(
      [node("a", { entity_spawns: [{ template: "stalker" }] })],
      [],
      {
        zoneId: "z1",
        entityIds: ["stalker"],
        itemIds: ["shard"],
        entityLoot: { stalker: ["shard", "phantom_item"] },
        glyphIds: ["fire"],
        glyphs: { fire: { prerequisites: ["missing_glyph"] } },
      }
    );
    const msgs = issues.map((i) => i.msg).join("\n");
    expect(msgs).not.toContain('Unknown entity template "stalker"');
    expect(msgs).toContain('unknown item "phantom_item"');
    expect(msgs).toContain("prerequisite unknown: missing_glyph");
  });

  it("validationCounts splits errors and warnings", () => {
    const counts = validationCounts([
      { level: "error", msg: "e" },
      { level: "warn", msg: "w" },
      { level: "warn", msg: "w2" },
    ]);
    expect(counts).toEqual({ err: 1, warn: 2 });
  });
});
