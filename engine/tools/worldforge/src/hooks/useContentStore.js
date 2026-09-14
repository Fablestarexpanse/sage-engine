import { loadWorldSchema } from "../utils/worldSchema.js";
import { createContext, createElement, useCallback, useContext, useMemo, useReducer, useRef } from "react";
import { joinPaths } from "../utils/paths.js";
import { hasAnyWorldContent } from "../utils/worldScaffold.js";
import * as fs from "../utils/fsBridge.js";

/**
 * @typedef {Object} ZoneState
 * @property {Record<string, object>} rooms Room YAML keyed by slug (file stem).
 *
 * @typedef {Object} PendingScaffold
 * @property {string} contentRoot The folder the user picked.
 * @property {string} worldRoot Resolved `content/world`-equivalent root.
 * @property {"missing"|"empty"} reason Why scaffolding is being offered.
 *
 * @typedef {Object} ContentState
 * @property {string|null} contentRoot Folder the user picked (before world-root resolution).
 * @property {string|null} worldRoot Resolved world content root (contains zones/, entities/, etc).
 * @property {Record<string, ZoneState>} zones Zone id -> zone state.
 * @property {string[]} zoneIds Sorted zone ids.
 * @property {Record<string, object>} entities Entity id -> entity template YAML.
 * @property {string[]} entityIds Sorted entity ids.
 * @property {Record<string, object>} items Item id -> item template YAML.
 * @property {string[]} itemIds Sorted item ids.
 * @property {object|null} worldSchema The package's content.schema.json (world lists, plugin fields), or null.
 * @property {boolean} loading True while a full loadAll() scan is in flight.
 * @property {string|null} loadError Set when loadAll() fails; cleared on next load.
 * @property {Record<string, boolean>} dirtyPaths Reserved for future dirty-file tracking.
 * @property {PendingScaffold|null} pendingScaffold Set when the picked folder needs scaffolding.
 */

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
  worldSchema: null,
  loading: false,
  loadError: null,
  dirtyPaths: {},
  /** When set, user picked a repo but world is missing or empty — ask to scaffold. */
  pendingScaffold: null,
};

function sortIds(ids) {
  return [...ids].sort((a, b) => a.localeCompare(b));
}

export function reducer(state, action) {
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
        worldSchema,
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
        worldSchema,
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
        entityIds: state.entityIds.includes(id) ? state.entityIds : sortIds([...state.entityIds, id]),
      };
    }
    case "DELETE_ENTITY": {
      const { id } = action;
      const { [id]: _, ...rest } = state.entities;
      return { ...state, entities: rest, entityIds: state.entityIds.filter((x) => x !== id) };
    }
    case "UPDATE_ITEM": {
      const { id, data } = action;
      return {
        ...state,
        items: { ...state.items, [id]: data },
        itemIds: state.itemIds.includes(id) ? state.itemIds : sortIds([...state.itemIds, id]),
      };
    }
    case "DELETE_ITEM": {
      const { id } = action;
      const { [id]: _, ...rest } = state.items;
      return { ...state, items: rest, itemIds: state.itemIds.filter((x) => x !== id) };
    }
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

/**
 * Read every `*.yaml` file directly under `worldRoot/subdir` into an id->doc map.
 * A file that fails to parse is kept in the map with a `_parseError: true` sentinel
 * (and `id` set from the filename) rather than being dropped, so callers can still
 * see it exists and warn the user instead of silently losing the entry.
 * @param {string} worldRoot
 * @param {string} subdir e.g. "entities", "items"
 * @returns {Promise<{map: Record<string, object>, ids: string[]}>}
 */
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
 *   picked/worlds/<id>/content/world/zones → SAGE repository root (first world with zones)
 *   picked/content/world/zones  → world package root
 *   picked/world/zones          → content root   (content/)
 *   picked/zones                → world root     (content/world/)
 * Returns null if none found.
 */
async function resolveWorldRoot(picked) {
  const worldsDir = joinPaths(picked, "worlds");
  if (await fs.pathExists(worldsDir)) {
    let entries = [];
    try {
      entries = await fs.listDir(worldsDir);
    } catch {
      entries = [];
    }
    const names = entries
      .map((e) => (typeof e === "string" ? e : e?.name))
      .filter(Boolean)
      .sort();
    for (const name of names) {
      const candidate = joinPaths(worldsDir, name, "content", "world");
      if (await fs.pathExists(joinPaths(candidate, "zones"))) return candidate;
    }
  }
  const candidates = [
    joinPaths(picked, "content", "world"),
    joinPaths(picked, "world"),
    picked,
  ];
  for (const candidate of candidates) {
    if (await fs.pathExists(joinPaths(candidate, "zones"))) return candidate;
    // Also accept if the directory itself exists but is just empty/new
    if (await fs.pathExists(joinPaths(candidate, "entities"))) return candidate;
  }
  // Fall back to the conventional path so scaffold prompt triggers correctly
  return joinPaths(picked, "content", "world");
}

/**
 * Shared scanning logic used by both loadAll and softRefresh: walks the whole world-content
 * tree (zones/rooms, entities, items) and returns a
 * fresh snapshot suitable for LOAD_ALL_DONE / SOFT_LOAD_DONE. A room file that fails
 * to parse is kept with a `_parseError: true` sentinel rather than dropped.
 * @param {string} contentRoot
 * @param {string} worldRoot
 * @returns {Promise<object>} payload shape matching LOAD_ALL_DONE/SOFT_LOAD_DONE.
 */
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

  const worldSchema = await loadWorldSchema(fs, worldRoot);

  return {
    contentRoot,
    worldRoot,
    zones,
    zoneIds: sortIds(zoneIds),
    entities: ent.map,
    entityIds: ent.ids,
    items: it.map,
    itemIds: it.ids,
    worldSchema,
  };
}

/**
 * React context provider for all world content state (zones/entities/items) plus the load, save, and delete actions that mutate it. See {@link ContentState}
 * for the state shape provided alongside these actions.
 * @param {{children: import('react').ReactNode}} props
 */
export function ContentProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  /**
   * Full (re)load of a picked content folder. Resolves the world root, checks whether it
   * exists / has content (dispatching SCAFFOLD_NEEDED and returning early if not), then scans
   * the whole tree and dispatches LOAD_ALL_DONE.
   *
   * Error contract: never throws — a scan failure is caught and turned into `state.loadError`
   * via LOAD_ERROR (loading is also cleared). Callers do not need a try/catch; they should
   * read `loadError` from state after awaiting this.
   * @param {string} contentRoot Folder the user picked.
   * @returns {Promise<void>}
   */
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
   *
   * Error contract: best-effort, and swallows everything — a failed or missing world root, a
   * transient read error, or an overlapping call all just return without updating state or
   * throwing. Never surfaces an error to the caller; do not await this expecting a rejection.
   * @param {string} contentRoot
   * @returns {Promise<void>}
   */
  // In-flight guard: the 2s live-watch tick must never overlap a slow scan,
  // and a stale scan must never overwrite a newer one's result.
  const softRefreshSeq = useRef(0);
  const softRefreshBusy = useRef(false);
  const softRefresh = useCallback(async (contentRoot) => {
    if (!contentRoot || softRefreshBusy.current) return;
    softRefreshBusy.current = true;
    const seq = ++softRefreshSeq.current;
    try {
      const worldRoot = await resolveWorldRoot(contentRoot);
      if (!(await fs.pathExists(worldRoot))) return;
      const payload = await scanWorldContent(contentRoot, worldRoot);
      if (seq === softRefreshSeq.current) {
        dispatch({ type: "SOFT_LOAD_DONE", payload });
      }
    } catch {
      // silently swallow — user is watching, don't interrupt with error state
    } finally {
      softRefreshBusy.current = false;
    }
  }, []);

  /**
   * Delete a zone's entire directory (all rooms, positions, groups) from disk, then remove it
   * from state.
   *
   * Error contract: throws on failure (e.g. permission error, missing disk access) — the write
   * happens first, so a throw here means nothing was removed from state; the caller should
   * catch and show feedback rather than assume the zone is gone.
   * @param {string} zoneId
   * @param {string} worldRoot
   * @returns {Promise<void>}
   */
  const deleteZone = useCallback(async (zoneId, worldRoot) => {
    if (!zoneId || !worldRoot) return;
    const { joinPaths } = await import("../utils/paths.js");
    const zoneDir = joinPaths(worldRoot, "zones", zoneId);
    await fs.removeDirAll(zoneDir);
    dispatch({ type: "DELETE_ZONE", id: zoneId });
  }, []);

  /**
   * Save an entity template: write `worldRoot/entities/{id}.yaml`, then dispatch UPDATE_ENTITY.
   * Error contract: throws on write failure; state is left untouched (dispatch only runs after
   * a successful write). Caller catches and shows its own feedback.
   * @param {string} worldRoot
   * @param {string} id
   * @param {object} data
   * @returns {Promise<void>}
   */
  const saveEntity = useCallback(async (worldRoot, id, data) => {
    await fs.writeYaml(joinPaths(worldRoot, "entities", `${id}.yaml`), data);
    dispatch({ type: "UPDATE_ENTITY", id, data });
  }, []);

  /**
   * Save an item template: write `worldRoot/items/{id}.yaml`, then dispatch UPDATE_ITEM.
   * Error contract: throws on write failure; state is left untouched.
   * @param {string} worldRoot
   * @param {string} id
   * @param {object} data
   * @returns {Promise<void>}
   */
  const saveItem = useCallback(async (worldRoot, id, data) => {
    await fs.writeYaml(joinPaths(worldRoot, "items", `${id}.yaml`), data);
    dispatch({ type: "UPDATE_ITEM", id, data });
  }, []);

  /**
   * Save one zone room: write `worldRoot/zones/{zoneId}/rooms/{slug}.yaml`, then dispatch
   * UPDATE_ZONE_ROOM. This is the simple single-file room save used by most zone-editing call
   * sites; multi-file flows (duplicate, stamp placement, clear-all-connections) write and
   * dispatch per room themselves and do not go through this action.
   * Error contract: throws on write failure; state is left untouched.
   * @param {string} worldRoot
   * @param {string} zoneId
   * @param {string} slug
   * @param {object} data
   * @returns {Promise<void>}
   */
  const saveZoneRoom = useCallback(async (worldRoot, zoneId, slug, data) => {
    await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), data);
    dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data });
  }, []);

  /**
   * Set (or clear) the picked content folder. Clearing (`root` falsy) resets all state
   * synchronously; setting a root delegates to loadAll and shares its error contract (never
   * throws — failures land in `state.loadError`).
   * @param {string|null} root
   * @returns {Promise<void>}
   */
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

  /** Clear a pending scaffold prompt without creating anything. @returns {void} */
  const dismissPendingScaffold = useCallback(() => {
    dispatch({ type: "CLEAR_PENDING_SCAFFOLD" });
  }, []);

  // NOTE: `dispatch` stays on the provider value for load/refresh internals (e.g. rebuilding
  // positions/groups state that live outside the reducer, or editors reacting to live-watch
  // updates) — but any code that *writes content to disk* should go through one of the named
  // save actions above (saveEntity/saveItem/saveZoneRoom) or deleteZone, not call `dispatch` directly to fake a write. Those actions
  // guarantee the file write happens before the state update, and throw (rather than silently
  // diverging store state from disk) if the write fails.
  const value = useMemo(
    () => ({
      ...state,
      dispatch,
      setContentRoot,
      loadAll,
      softRefresh,
      deleteZone,
      dismissPendingScaffold,
      saveEntity,
      saveItem,
      saveZoneRoom,
    }),
    [
      state,
      setContentRoot,
      loadAll,
      softRefresh,
      deleteZone,
      dismissPendingScaffold,
      saveEntity,
      saveItem,
      saveZoneRoom,
    ]
  );

  return createElement(ContentContext.Provider, { value }, children);
}

/**
 * Read the shared content store. Must be called under a {@link ContentProvider}.
 * @returns {ContentState & {
 *   dispatch: Function,
 *   setContentRoot: (root: string|null) => Promise<void>,
 *   loadAll: (contentRoot: string) => Promise<void>,
 *   softRefresh: (contentRoot: string) => Promise<void>,
 *   deleteZone: (zoneId: string, worldRoot: string) => Promise<void>,
 *   dismissPendingScaffold: () => void,
 *   saveEntity: (worldRoot: string, id: string, data: object) => Promise<void>,
 *   saveItem: (worldRoot: string, id: string, data: object) => Promise<void>,
 *   saveZoneRoom: (worldRoot: string, zoneId: string, slug: string, data: object) => Promise<void>,
 * }}
 */
export function useContent() {
  const ctx = useContext(ContentContext);
  if (!ctx) throw new Error("useContent outside ContentProvider");
  return ctx;
}
