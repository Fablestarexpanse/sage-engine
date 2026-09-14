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

  it("accepts known templates and reports loot problems from ctx", () => {
    const issues = runZoneValidation(
      [node("a", { entity_spawns: [{ template: "stalker" }] })],
      [],
      {
        zoneId: "z1",
        entityIds: ["stalker"],
        itemIds: ["shard"],
        entityLoot: { stalker: ["shard", "phantom_item", { template: "shard", chance: 0.5 }, { template: "ghost_item" }] },
      }
    );
    const msgs = issues.map((i) => i.msg).join("\n");
    expect(msgs).not.toContain('Unknown entity template "stalker"');
    expect(msgs).toContain('unknown item "phantom_item"');
    expect(msgs).toContain('unknown item "ghost_item"');
    expect(msgs).not.toContain("[object Object]");
  });

  it("errors on room types and exit directions the world does not declare", () => {
    const issues = runZoneValidation(
      [node("a", { type: "airlock", exits: { northeast: { destination: "z1:b" } } }), node("b", { type: "street" })],
      [],
      { zoneId: "z1", roomTypes: ["street"], exitDirs: ["north", "south"] }
    );
    const errors = issues.filter((i) => i.level === "error").map((i) => i.msg);
    expect(errors).toContain(`Room type "airlock" is not one of this world's: a`);
    expect(errors).toContain(`Exit direction "northeast" is not one of this world's: a`);
    const unchecked = runZoneValidation([node("a", { type: "airlock" })], [], { zoneId: "z1" });
    expect(unchecked.some((i) => i.msg.includes("not one of this world"))).toBe(false);
  });

  it("warns on low feature density and reports it as info when healthy", () => {
    const empty = runZoneValidation([node("a"), node("b"), node("c")], [], { zoneId: "z1" });
    expect(empty.some((i) => i.level === "warn" && i.msg.includes("Low feature density"))).toBe(true);

    const rich = runZoneValidation(
      [
        node("a", { features: [{ name: "crates", description: "d" }], entity_spawns: [] }),
        node("b", { hazards: [{ id: "h", type: "radiation", severity: 1, description: "d" }] }),
      ],
      [],
      { zoneId: "z1" }
    );
    expect(rich.some((i) => i.level === "info" && i.msg.includes("Feature density 1.00"))).toBe(true);
    expect(rich.some((i) => i.msg.includes("Low feature density"))).toBe(false);
  });

  it("counts an ambient block as one draw", () => {
    const issues = runZoneValidation(
      [node("a", { ambient: { lines: ["x"] } }), node("b", { ambient: { lines: [] } })],
      [],
      { zoneId: "z1" }
    );
    const density = issues.find((i) => i.msg.includes("density"));
    expect(density.msg).toContain("(1 draws / 2 rooms");
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
