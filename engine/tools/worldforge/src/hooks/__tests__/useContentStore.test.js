import { describe, expect, it } from "vitest";
import { reducer } from "../useContentStore.js";

const initialState = {
  contentRoot: null,
  worldRoot: null,
  zones: {},
  zoneIds: [],
  entities: {},
  entityIds: [],
  items: {},
  itemIds: [],
  worldSchema: null,
  loading: false,
  loadError: null,
  dirtyPaths: {},
  pendingScaffold: null,
};

describe("useContentStore reducer", () => {
  it("UPDATE_ENTITY adds a new id to entityIds (sorted) and stores the data", () => {
    const state = { ...initialState, entityIds: ["b_entity"], entities: { b_entity: { id: "b_entity" } } };
    const next = reducer(state, { type: "UPDATE_ENTITY", id: "a_entity", data: { id: "a_entity", name: "A" } });
    expect(next.entityIds).toEqual(["a_entity", "b_entity"]);
    expect(next.entities.a_entity).toEqual({ id: "a_entity", name: "A" });
  });

  it("UPDATE_ENTITY updates data for an existing id without duplicating it in entityIds", () => {
    const state = { ...initialState, entityIds: ["a_entity"], entities: { a_entity: { id: "a_entity", name: "old" } } };
    const next = reducer(state, { type: "UPDATE_ENTITY", id: "a_entity", data: { id: "a_entity", name: "new" } });
    expect(next.entityIds).toEqual(["a_entity"]);
    expect(next.entities.a_entity).toEqual({ id: "a_entity", name: "new" });
  });

  it("UPDATE_ITEM adds a new id to itemIds and updates data for an existing one", () => {
    const state = { ...initialState, itemIds: ["potion"], items: { potion: { id: "potion", value: 1 } } };
    let next = reducer(state, { type: "UPDATE_ITEM", id: "sword", data: { id: "sword", value: 10 } });
    expect(next.itemIds).toEqual(["potion", "sword"]);
    expect(next.items.sword).toEqual({ id: "sword", value: 10 });

    next = reducer(next, { type: "UPDATE_ITEM", id: "potion", data: { id: "potion", value: 2 } });
    expect(next.itemIds).toEqual(["potion", "sword"]);
    expect(next.items.potion).toEqual({ id: "potion", value: 2 });
  });

  it("DELETE_ZONE removes the zone from zones and zoneIds", () => {
    const state = {
      ...initialState,
      zoneIds: ["zone_a", "zone_b"],
      zones: { zone_a: { rooms: {} }, zone_b: { rooms: { r1: {} } } },
    };
    const next = reducer(state, { type: "DELETE_ZONE", id: "zone_a" });
    expect(next.zoneIds).toEqual(["zone_b"]);
    expect(next.zones).toEqual({ zone_b: { rooms: { r1: {} } } });
  });

  it("SOFT_LOAD_DONE replaces content maps without touching the loading flag", () => {
    const state = { ...initialState, loading: true, entityIds: ["stale"] };
    const payload = {
      zones: { z1: { rooms: {} } },
      zoneIds: ["z1"],
      entities: { e1: { id: "e1" } },
      entityIds: ["e1"],
      items: {},
      itemIds: [],
      worldSchema: { content: { room_types: ["street"] } },
      contentRoot: "/picked",
      worldRoot: "/picked/content/world",
    };
    const next = reducer(state, { type: "SOFT_LOAD_DONE", payload });
    expect(next.worldSchema).toEqual({ content: { room_types: ["street"] } });
    expect(next.zones).toEqual({ z1: { rooms: {} } });
    expect(next.entityIds).toEqual(["e1"]);
    expect(next.contentRoot).toBe("/picked");
    expect(next.worldRoot).toBe("/picked/content/world");
    expect(next.loading).toBe(true);
  });

  it("SCAFFOLD_NEEDED sets pendingScaffold", () => {
    const next = reducer(initialState, {
      type: "SCAFFOLD_NEEDED",
      payload: { contentRoot: "/picked", worldRoot: "/picked/content/world", reason: "empty" },
    });
    expect(next.pendingScaffold).toEqual({
      contentRoot: "/picked",
      worldRoot: "/picked/content/world",
      reason: "empty",
    });
    expect(next.loading).toBe(false);
  });
});
