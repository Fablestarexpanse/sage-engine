import { createContext, createElement, useCallback, useContext, useMemo, useReducer } from "react";
import { joinPaths } from "../utils/paths.js";
import { hasAnyWorldContent } from "../utils/worldScaffold.js";
import * as fs from "./useFileSystem.js";

const ContentContext = createContext(null);

const initialState = {
  contentRoot: null,
  worldRoot: null,
  zones: {},
  zoneIds: [],
  entities: {},
  entityIds: [],
  items: {},
  itemIds: [],
  systems: {},
  systemIds: [],
  ships: {},
  shipIds: [],
  glyphs: {},
  glyphIds: [],
  galaxy: null,
  loading: false,
  loadError: null,
  dirtyPaths: {},
  /** When set, user picked a repo but world is missing or empty — ask to scaffold. */
  pendingScaffold: null,
};

function sortIds(ids) {
  return [...ids].sort((a, b) => a.localeCompare(b));
}

function reducer(state, action) {
  switch (action.type) {
    case "RESET":
      return { ...initialState };
    case "BEGIN_LOAD":
      return { ...initialState, loading: true };
    case "SCAFFOLD_NEEDED":
      return {
        ...initialState,
        loading: false,
        pendingScaffold: {
          contentRoot: action.payload.contentRoot,
          worldRoot: action.payload.worldRoot,
          reason: action.payload.reason,
        },
      };
    case "CLEAR_PENDING_SCAFFOLD":
      return { ...initialState, loading: false };
    case "SET_LOADING":
      return { ...state, loading: action.value, loadError: action.value ? null : state.loadError };
    case "LOAD_ALL_DONE":
    // SOFT_LOAD_DONE is identical but never came from a BEGIN_LOAD, so we
    // don't touch the `loading` flag — avoids the full-screen "Loading…" flash
    // when polling for live changes.
    case "SOFT_LOAD_DONE": {
      const {
        zones,
        zoneIds,
        entities,
        entityIds,
        items,
        itemIds,
        systems,
        systemIds,
        ships,
        shipIds,
        glyphs,
        glyphIds,
        galaxy,
        contentRoot,
        worldRoot,
      } = action.payload;
      return {
        ...state,
        contentRoot,
        worldRoot,
        zones,
        zoneIds,
        entities,
        entityIds,
        items,
        itemIds,
        systems,
        systemIds,
        ships,
        shipIds,
        glyphs,
        glyphIds,
        galaxy,
        loading: action.type === "LOAD_ALL_DONE" ? false : state.loading,
        loadError: action.type === "LOAD_ALL_DONE" ? null : state.loadError,
        dirtyPaths: {},
        pendingScaffold: null,
      };
    }
    case "LOAD_ERROR":
      return { ...state, loading: false, loadError: action.message };
    case "UPDATE_ZONE_ROOM": {
      const { zoneId, slug, data } = action;
      const z = state.zones[zoneId] || { rooms: {} };
      return {
        ...state,
        zones: {
          ...state.zones,
          [zoneId]: {
            ...z,
            rooms: { ...z.rooms, [slug]: data },
          },
        },
      };
    }
    case "DELETE_ZONE_ROOM": {
      const { zoneId, slug } = action;
      const z = state.zones[zoneId];
      if (!z?.rooms) return state;
      const { [slug]: _, ...rest } = z.rooms;
      return {
        ...state,
        zones: {
          ...state.zones,
          [zoneId]: { ...z, rooms: rest },
        },
      };
    }
    case "UPDATE_ENTITY": {
      const { id, data } = action;
      return {
        ...state,
        entities: { ...state.entities, [id]: data },
      };
    }
    case "DELETE_ENTITY": {
      const { id } = action;
      const { [id]: _, ...rest } = state.entities;
      return { ...state, entities: rest, entityIds: state.entityIds.filter((x) => x !== id) };
    }
    case "UPDATE_ITEM": {
      const { id, data } = action;
      return { ...state, items: { ...state.items, [id]: data } };
    }
    case "DELETE_ITEM": {
      const { id } = action;
      const { [id]: _, ...rest } = state.items;
      return { ...state, items: rest, itemIds: state.itemIds.filter((x) => x !== id) };
    }
    case "UPDATE_SYSTEM": {
      const { id, data } = action;
      return { ...state, systems: { ...state.systems, [id]: data } };
    }
    case "UPDATE_SHIP_DOC": {
      const { id, doc } = action;
      return { ...state, ships: { ...state.ships, [id]: doc } };
    }
    case "UPDATE_GLYPH": {
      const { id, data } = action;
      return { ...state, glyphs: { ...state.glyphs, [id]: data } };
    }
    case "DELETE_GLYPH": {
      const { id } = action;
      const { [id]: _, ...rest } = state.glyphs;
      return { ...state, glyphs: rest, glyphIds: state.glyphIds.filter((x) => x !== id) };
    }
    case "SET_GALAXY":
      return { ...state, galaxy: action.galaxy };
    case "MARK_DIRTY": {
      const p = action.path;
      return { ...state, dirtyPaths: { ...state.dirtyPaths, [p]: true } };
    }
    case "MARK_CLEAN": {
      const p = action.path;
      const { [p]: _, ...rest } = state.dirtyPaths;
      return { ...state, dirtyPaths: rest };
    }
    case "MARK_ALL_CLEAN":
      return { ...state, dirtyPaths: {} };
    case "ADD_ENTITY_ID":
      if (state.entityIds.includes(action.id)) return state;
      return { ...state, entityIds: sortIds([...state.entityIds, action.id]) };
    case "ADD_ITEM_ID":
      if (state.itemIds.includes(action.id)) return state;
      return { ...state, itemIds: sortIds([...state.itemIds, action.id]) };
    case "ADD_GLYPH_ID":
      if (state.glyphIds.includes(action.id)) return state;
      return { ...state, glyphIds: sortIds([...state.glyphIds, action.id]) };
    case "ADD_ZONE_ID":
      if (state.zoneIds.includes(action.id)) return state;
      return {
        ...state,
        zoneIds: sortIds([...state.zoneIds, action.id]),
        zones: { ...state.zones, [action.id]: { rooms: {} } },
      };
    case "DELETE_ZONE": {
      const { id } = action;
      const { [id]: _, ...restZones } = state.zones;
      return {
        ...state,
        zoneIds: state.zoneIds.filter((z) => z !== id),
        zones: restZones,
      };
    }
    default:
      return state;
  }
}

async function loadYamlDir(worldRoot, subdir) {
  const base = joinPaths(worldRoot, subdir);
  if (!(await fs.pathExists(base))) return { map: {}, ids: [] };
  const entries = await fs.listDir(base);
  const map = {};
  const ids = [];
  for (const e of entries) {
    if (e.is_dir || !e.name.endsWith(".yaml")) continue;
    const id = e.name.replace(/\.yaml$/i, "");
    try {
      map[id] = await fs.readYaml(e.path);
    } catch {
      map[id] = { id, _parseError: true };
    }
    ids.push(id);
  }
  return { map, ids: sortIds(ids) };
}

/**
 * Resolve the actual world root from whatever folder the user picked.
 * Tries several common layouts so it doesn't matter which level they click:
 *   picked/content/world/zones  → project root  (FableStarExpanseMUD/)
 *   picked/world/zones          → content root   (content/)
 *   picked/zones                → world root     (content/world/)
 * Returns null if none found.
 */
async function resolveWorldRoot(picked) {
  const candidates = [
    joinPaths(picked, "content", "world"),
    joinPaths(picked, "world"),
    picked,
  ];
  for (const candidate of candidates) {
    if (await fs.pathExists(joinPaths(candidate, "zones"))) return candidate;
    // Also accept if the directory itself exists but is just empty/new
    if (await fs.pathExists(joinPaths(candidate, "entities"))) return candidate;
    if (await fs.pathExists(joinPaths(candidate, "galaxy.yaml"))) return candidate;
  }
  // Fall back to the conventional path so scaffold prompt triggers correctly
  return joinPaths(picked, "content", "world");
}

/** Shared scanning logic used by both loadAll and softRefresh. */
async function scanWorldContent(contentRoot, worldRoot) {
  const zonesRoot = joinPaths(worldRoot, "zones");
  const zoneIds = [];
  const zones = {};
  if (await fs.pathExists(zonesRoot)) {
    const zdirs = await fs.listDir(zonesRoot);
    for (const d of zdirs) {
      if (!d.is_dir) continue;
      const zoneId = d.name;
      if (!/^[a-zA-Z0-9_-]+$/.test(zoneId)) continue;
      const roomsDir = joinPaths(d.path, "rooms");
      const rooms = {};
      if (await fs.pathExists(roomsDir)) {
        const rfiles = await fs.listDir(roomsDir);
        for (const f of rfiles) {
          if (f.is_dir || !f.name.endsWith(".yaml")) continue;
          const slug = f.name.replace(/\.yaml$/i, "");
          try {
            rooms[slug] = await fs.readYaml(f.path);
          } catch {
            rooms[slug] = { id: `${zoneId}:${slug}`, zone: zoneId, _parseError: true };
          }
        }
      }
      zones[zoneId] = { rooms };
      zoneIds.push(zoneId);
    }
  }

  const ent = await loadYamlDir(worldRoot, "entities");
  const it = await loadYamlDir(worldRoot, "items");
  const sys = await loadYamlDir(worldRoot, "systems");
  const glyphs = await loadYamlDir(worldRoot, "glyphs");

  const shipsRoot = joinPaths(worldRoot, "ships");
  const shipIds = [];
  const ships = {};
  if (await fs.pathExists(shipsRoot)) {
    const sfiles = await fs.listDir(shipsRoot);
    for (const f of sfiles) {
      if (f.is_dir || !f.name.endsWith(".yaml")) continue;
      const sid = f.name.replace(/\.yaml$/i, "");
      try {
        ships[sid] = await fs.readYaml(f.path);
      } catch {
        ships[sid] = { ship: { id: sid, rooms: [] }, _parseError: true };
      }
      shipIds.push(sid);
    }
  }

  let galaxy = null;
  const galPath = joinPaths(worldRoot, "galaxy.yaml");
  if (await fs.pathExists(galPath)) {
    try {
      galaxy = await fs.readYaml(galPath);
    } catch {
      galaxy = null;
    }
  }

  return {
    contentRoot,
    worldRoot,
    zones,
    zoneIds: sortIds(zoneIds),
    entities: ent.map,
    entityIds: ent.ids,
    items: it.map,
    itemIds: it.ids,
    systems: sys.map,
    systemIds: sys.ids,
    ships,
    shipIds: sortIds(shipIds),
    glyphs: glyphs.map,
    glyphIds: glyphs.ids,
    galaxy,
  };
}

export function ContentProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const loadAll = useCallback(
    async (contentRoot) => {
      dispatch({ type: "BEGIN_LOAD" });
      const worldRoot = await resolveWorldRoot(contentRoot);
      const worldExists = await fs.pathExists(worldRoot);

      if (!worldExists) {
        dispatch({
          type: "SCAFFOLD_NEEDED",
          payload: { contentRoot, worldRoot, reason: "missing" },
        });
        return;
      }

      if (!(await hasAnyWorldContent(worldRoot))) {
        dispatch({
          type: "SCAFFOLD_NEEDED",
          payload: { contentRoot, worldRoot, reason: "empty" },
        });
        return;
      }

      try {
        const payload = await scanWorldContent(contentRoot, worldRoot);
        dispatch({ type: "LOAD_ALL_DONE", payload });
      } catch (e) {
        dispatch({ type: "LOAD_ERROR", message: String(e?.message || e) });
      }
    },
    []
  );

  /**
   * Silent incremental refresh — rescans disk without resetting the UI.
   * Safe to call on a timer; no loading overlay shown.
   */
  const softRefresh = useCallback(async (contentRoot) => {
    if (!contentRoot) return;
    try {
      const worldRoot = await resolveWorldRoot(contentRoot);
      if (!(await fs.pathExists(worldRoot))) return;
      const payload = await scanWorldContent(contentRoot, worldRoot);
      dispatch({ type: "SOFT_LOAD_DONE", payload });
    } catch {
      // silently swallow — user is watching, don't interrupt with error state
    }
  }, []);

  const deleteZone = useCallback(async (zoneId, worldRoot) => {
    if (!zoneId || !worldRoot) return;
    const { joinPaths } = await import("../utils/paths.js");
    const zoneDir = joinPaths(worldRoot, "zones", zoneId);
    await fs.removeDirAll(zoneDir);
    dispatch({ type: "DELETE_ZONE", id: zoneId });
  }, []);

  const setContentRoot = useCallback(
    async (root) => {
      if (!root) {
        dispatch({ type: "RESET" });
        return;
      }
      await loadAll(root);
    },
    [loadAll]
  );

  const dismissPendingScaffold = useCallback(() => {
    dispatch({ type: "CLEAR_PENDING_SCAFFOLD" });
  }, []);

  const value = useMemo(
    () => ({
      ...state,
      dispatch,
      setContentRoot,
      loadAll,
      softRefresh,
      deleteZone,
      dismissPendingScaffold,
    }),
    [state, setContentRoot, loadAll, softRefresh, deleteZone, dismissPendingScaffold]
  );

  return createElement(ContentContext.Provider, { value }, children);
}

export function useContent() {
  const ctx = useContext(ContentContext);
  if (!ctx) throw new Error("useContent outside ContentProvider");
  return ctx;
}
