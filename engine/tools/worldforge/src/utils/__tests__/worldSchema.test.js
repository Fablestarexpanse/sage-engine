import { describe, expect, it } from "vitest";
import { ALL_DIRECTIONS, loadWorldSchema, pickRoomType, schemaPathFor, worldLists } from "../worldSchema.js";

describe("world schema", () => {
  it("finds content.schema.json beside world.toml for a content/world root", () => {
    expect(schemaPathFor("/repo/worlds/rivermoot/content/world")).toBe("/repo/worlds/rivermoot/content.schema.json");
    expect(schemaPathFor(String.raw`F:\repo\worlds\rivermoot\content\world`)).toBe(
      String.raw`F:\repo\worlds\rivermoot\content.schema.json`
    );
    expect(schemaPathFor("")).toBe(null);
  });

  it("loads the file, or null when absent or broken", async () => {
    const files = { "/w/rivermoot/content.schema.json": '{"content": {"room_types": ["inn"]}}', "/w/bad/content.schema.json": "{" };
    const fs = { pathExists: async (p) => p in files, readText: async (p) => files[p] };
    expect(await loadWorldSchema(fs, "/w/rivermoot/content/world")).toEqual({ content: { room_types: ["inn"] } });
    expect(await loadWorldSchema(fs, "/w/bad/content/world")).toBe(null);
    expect(await loadWorldSchema(fs, "/w/none/content/world")).toBe(null);
  });

  it("offers the world's lists, or what the content already uses", () => {
    const schema = { content: { room_types: ["street", "inn"], exit_dirs: ["north", "south"], equipment_slots: ["hand"] } };
    expect(worldLists(schema, {})).toEqual({ roomTypes: ["street", "inn"], exitDirs: ["north", "south"], slots: ["hand"], declared: true });
    const zones = { town: { rooms: { a: { type: "square" }, b: { type: "hut" }, c: { type: "square" } } } };
    expect(worldLists(null, zones)).toEqual({ roomTypes: ["hut", "square"], exitDirs: ALL_DIRECTIONS, slots: [], declared: false });
  });

  it("keeps a preferred room type only when the world allows it", () => {
    expect(pickRoomType("chamber", ["street", "inn"])).toBe("street");
    expect(pickRoomType("inn", ["street", "inn"])).toBe("inn");
    expect(pickRoomType("chamber", [])).toBe("chamber");
  });
});
