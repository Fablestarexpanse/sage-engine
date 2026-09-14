import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { defaultFor, extensionsFor, parseNumber, resolveSchema } from "../schemaForm.js";

const here = dirname(fileURLToPath(import.meta.url));
const rivermoot = JSON.parse(
  readFileSync(resolve(here, "../../../../../../worlds/rivermoot/content.schema.json"), "utf8")
);

describe("schema forms", () => {
  it("lists a kind's plugin fields from the exported schema", () => {
    expect(extensionsFor(rivermoot, "room").map((e) => e.name)).toEqual(["ambient", "hazards", "lodging", "shop"]);
    expect(extensionsFor(rivermoot, "feature").map((e) => `${e.name}:${e.owner}`)).toEqual(["search:search"]);
    expect(extensionsFor(rivermoot, "item").map((e) => e.name)).toContain("slot");
    expect(extensionsFor(null, "room")).toEqual([]);
  });

  it("starts new blocks from defaults, minimums and empty containers", () => {
    const shop = extensionsFor(rivermoot, "room").find((e) => e.name === "shop").schema;
    expect(defaultFor(shop, shop)).toMatchObject({ name: "the shop", sells: [], buys: false, buy_rate: 0.5 });
    const lodging = extensionsFor(rivermoot, "room").find((e) => e.name === "lodging").schema;
    expect(defaultFor(lodging, lodging)).toMatchObject({ rooms: [], price: 15, lease_minutes: 80 });
    const hazards = extensionsFor(rivermoot, "room").find((e) => e.name === "hazards").schema;
    expect(defaultFor(hazards, hazards)).toEqual([]);
    const row = resolveSchema(hazards.items, hazards);
    expect(defaultFor(row, hazards)).toEqual({ id: "", type: "", severity: 0, description: "" });
    const heal = extensionsFor(rivermoot, "item").find((e) => e.name === "heal").schema;
    expect(defaultFor(heal, heal)).toBe(0);
  });

  it("follows $defs references and parses numbers by type", () => {
    const shop = extensionsFor(rivermoot, "room").find((e) => e.name === "shop").schema;
    expect(resolveSchema(shop.properties.sells.items, shop).required).toEqual(["template", "price"]);
    expect(parseNumber("2.7", "integer")).toBe(2);
    expect(parseNumber("2.7", "number")).toBe(2.7);
    expect(parseNumber("", "integer")).toBe(undefined);
  });
});
