import { joinPaths } from "./paths.js";
import { deepClone } from "./clone.js";
import { parsePositionsDoc, serializePositionsDoc } from "./positionsDoc.js";
import { DEFAULT_ROOM_NODE_H, DEFAULT_ROOM_NODE_W } from "./zoneGraph.js";
import * as fs from "../hooks/useFileSystem.js";

/** Synthetic zone id stored in stamp room YAML for preview + internal exit resolution. */
export const STAMP_ZONE_ID = "__stamp__";

export function stampsRoot(worldRoot) {
  return joinPaths(worldRoot, "stamps");
}

export function stampFolderPath(worldRoot, stampSlug) {
  return joinPaths(stampsRoot(worldRoot), stampSlug);
}

export function readNodeBox(style, wFallback, hFallback) {
  const s = style || {};
  const pw = typeof s.width === "number" ? s.width : parseFloat(String(s.width ?? "").replace(/px$/i, ""));
  const ph = typeof s.height === "number" ? s.height : parseFloat(String(s.height ?? "").replace(/px$/i, ""));
  return {
    width: Number.isFinite(pw) && pw > 0 ? pw : wFallback,
    height: Number.isFinite(ph) && ph > 0 ? ph : hFallback,
  };
}

/**
 * @param {string[]} slugs
 * @returns {{ logicalKeys: string[], slugToLogical: Record<string, string> }}
 */
export function buildLogicalSlugMap(slugs) {
  const sorted = [...new Set(slugs.filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const slugToLogical = {};
  const logicalKeys = sorted.map((s, i) => {
    const k = `r${i}`;
    slugToLogical[s] = k;
    return k;
  });
  return { logicalKeys, slugToLogical };
}

/**
 * @typedef {object} StampPreserveFlags
 * @property {boolean} descriptions
 * @property {boolean} gameplay
 * @property {boolean} internalExits
 * @property {boolean} layoutExtras
 */

/**
 * Remap exit destination to logical slug or null if dropped.
 * @param {string} dest
 * @param {string} sourceZoneId
 * @param {Record<string, string>} slugToLogical
 */
function remapExitDestination(dest, sourceZoneId, slugToLogical) {
  const d = String(dest || "").trim();
  if (!d || d.startsWith("self:") || d.startsWith("@")) return null;
  let slugPart = d;
  if (d.includes(":")) {
    const [z, s] = d.split(":", 2);
    if (z !== sourceZoneId) return null;
    slugPart = s;
  }
  const logical = slugToLogical[slugPart];
  return logical || null;
}

/**
 * Build one room document for stamp storage.
 * @param {object} sourceRoom
 * @param {string} sourceZoneId
 * @param {string} logicalKey
 * @param {Record<string, string>} slugToLogical
 * @param {StampPreserveFlags} preserve
 */
export function buildStampRoomYaml(sourceRoom, sourceZoneId, logicalKey, slugToLogical, preserve) {
  const copy = deepClone(sourceRoom || {});
  copy.id = `${STAMP_ZONE_ID}:${logicalKey}`;
  copy.zone = STAMP_ZONE_ID;
  copy.slug = logicalKey;

  if (!preserve.descriptions) {
    copy.description = { base: "" };
  }

  if (!preserve.gameplay) {
    copy.entity_spawns = [];
    copy.hazards = [];
    copy.features = [];
    copy.tags = [];
  }

  const exits = copy.exits && typeof copy.exits === "object" ? { ...copy.exits } : {};
  copy.exits = {};

  if (preserve.internalExits) {
    const knownIds = new Set(Object.values(slugToLogical).map((lk) => `${STAMP_ZONE_ID}:${lk}`));
    for (const [dir, ex] of Object.entries(exits)) {
      if (!ex || typeof ex !== "object") continue;
      const dest = String(ex.destination || "");
      const short = remapExitDestination(dest, sourceZoneId, slugToLogical);
      if (!short) continue;
      const next = { ...ex };
      next.destination = short;
      copy.exits[dir] = next;
    }
  }

  if (!preserve.descriptions && copy.exits) {
    for (const ex of Object.values(copy.exits)) {
      if (ex && typeof ex === "object") {
        if (ex.description != null) delete ex.description;
        if (ex.map_label != null) delete ex.map_label;
      }
    }
  }

  return copy;
}

/**
 * @param {Record<string, object>} positionsDocPositions
 * @param {string[]} sourceSlugs
 * @param {Record<string, string>} slugToLogical
 * @param {Array<{ slug: string, position: {x,y}, style: object }>} snapshots
 * @param {StampPreserveFlags} preserve
 * @param {typeof DEFAULT_ROOM_NODE_W} wFallback
 * @param {typeof DEFAULT_ROOM_NODE_H} hFallback
 */
export function buildNormalizedStampPositions(positionsDocPositions, snapshots, slugToLogical, preserve, wFallback, hFallback) {
  const xs = [];
  const ys = [];
  for (const snap of snapshots) {
    const lg = slugToLogical[snap.slug];
    if (!lg) continue;
    xs.push(snap.position.x);
    ys.push(snap.position.y);
  }
  if (!xs.length) return { positions: {} };
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);

  /** @type {Record<string, object>} */
  const positions = {};
  for (const snap of snapshots) {
    const lg = slugToLogical[snap.slug];
    if (!lg) continue;
    const prev = { ...(positionsDocPositions?.[snap.slug] || {}) };
    delete prev.locked;
    const box = readNodeBox(snap.style, wFallback, hFallback);
    const rot = Number(prev.rotation);
    const entry = {
      x: snap.position.x - minX,
      y: snap.position.y - minY,
      width: box.width,
      height: box.height,
    };
    if (Number.isFinite(rot) && rot !== 0) entry.rotation = rot;
    if (preserve.layoutExtras && typeof prev.border_color === "string" && prev.border_color.trim()) {
      entry.border_color = prev.border_color.trim();
    }
    positions[lg] = entry;
  }
  return { positions };
}

/**
 * @param {string} worldRoot
 * @param {string} stampSlug filesystem-safe
 * @param {string} displayName
 * @param {string} sourceZoneId
 * @param {StampPreserveFlags} preserve
 * @param {Record<string, object>} roomsBySourceSlug slug -> yaml from zone
 * @param {Record<string, object>} positionsDocPositions
 * @param {Array<{ slug: string, position: {x:number,y:number}, style: object }>} snapshots
 * @param {typeof DEFAULT_ROOM_NODE_W} wFallback
 * @param {typeof DEFAULT_ROOM_NODE_H} hFallback
 */
export async function saveStampBundle(
  worldRoot,
  stampSlug,
  displayName,
  sourceZoneId,
  preserve,
  roomsBySourceSlug,
  positionsDocPositions,
  snapshots,
  wFallback,
  hFallback
) {
  const slugs = snapshots.map((s) => s.slug).filter(Boolean);
  const { logicalKeys, slugToLogical } = buildLogicalSlugMap(slugs);

  const dir = stampFolderPath(worldRoot, stampSlug);
  const roomsDir = joinPaths(dir, "rooms");
  await fs.createDir(roomsDir);

  const roomsMapForMeta = {};
  for (const slug of slugs) {
    const lk = slugToLogical[slug];
    const raw = roomsBySourceSlug[slug];
    if (!lk || !raw) continue;
    const yamlDoc = buildStampRoomYaml(raw, sourceZoneId, lk, slugToLogical, preserve);
    roomsMapForMeta[lk] = yamlDoc;
    await fs.writeYaml(joinPaths(roomsDir, `${lk}.yaml`), yamlDoc);
  }

  const { positions } = buildNormalizedStampPositions(positionsDocPositions, snapshots, slugToLogical, preserve, wFallback, hFallback);
  const layoutDoc = { version: 2, positions, notes: [], muted_edges: [] };
  await fs.writeText(joinPaths(dir, "layout.json"), serializePositionsDoc(layoutDoc));

  const meta = {
    version: 1,
    slug: stampSlug,
    display_name: displayName,
    created_at: new Date().toISOString(),
    source_zone: sourceZoneId,
    preserve,
    logical_keys: logicalKeys,
    slug_map: slugToLogical,
  };
  await fs.writeText(joinPaths(dir, "stamp.json"), JSON.stringify(meta, null, 2));
}

/**
 * @returns {Promise<{ meta: object, roomsMap: Record<string, object>, positionsDoc: ReturnType<typeof parsePositionsDoc> } | null>}
 */
export async function loadStampBundle(worldRoot, stampSlug) {
  const dir = stampFolderPath(worldRoot, stampSlug);
  const metaPath = joinPaths(dir, "stamp.json");
  const layoutPath = joinPaths(dir, "layout.json");
  if (!(await fs.pathExists(metaPath)) || !(await fs.pathExists(layoutPath))) return null;
  const meta = JSON.parse(await fs.readText(metaPath));
  const layoutRaw = JSON.parse(await fs.readText(layoutPath));
  const positionsDoc = parsePositionsDoc(layoutRaw);
  const roomsMap = {};
  const roomsDir = joinPaths(dir, "rooms");
  if (await fs.pathExists(roomsDir)) {
    const entries = await fs.listDir(roomsDir);
    for (const e of entries) {
      if (e.is_dir || !e.name.toLowerCase().endsWith(".yaml")) continue;
      const lk = e.name.replace(/\.yaml$/i, "");
      const data = await fs.readYaml(e.path);
      roomsMap[lk] = data;
    }
  }
  return { meta, roomsMap, positionsDoc };
}

/** List stamp slugs that have stamp.json */
export async function listStampSlugs(worldRoot) {
  const root = stampsRoot(worldRoot);
  if (!(await fs.pathExists(root))) return [];
  const entries = await fs.listDir(root);
  const out = [];
  for (const e of entries) {
    if (!e.is_dir) continue;
    const stampJson = joinPaths(e.path, "stamp.json");
    if (await fs.pathExists(stampJson)) out.push(e.name);
  }
  out.sort((a, b) => a.localeCompare(b));
  return out;
}

export async function deleteStampFolder(worldRoot, stampSlug) {
  const dir = stampFolderPath(worldRoot, stampSlug);
  if (await fs.pathExists(dir)) await fs.removeDirAll(dir);
}

/**
 * Allocate unique slug in zone.
 * @param {string} base
 * @param {Set<string>} used
 */
export function allocStampPlaceSlug(base, used) {
  const safe = String(base || "room")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 48) || "room";
  let cand = safe;
  if (!used.has(cand)) {
    used.add(cand);
    return cand;
  }
  let i = 2;
  while (used.has(`${safe}_${i}`)) i += 1;
  cand = `${safe}_${i}`;
  used.add(cand);
  return cand;
}

/**
 * Produce new room YAMLs and positions for target zone.
 * @param {string} targetZoneId
 * @param {Record<string, object>} stampRoomsMap logicalKey -> yaml
 * @param {ReturnType<typeof parsePositionsDoc>} stampPositionsDoc
 * @param {Record<string, string>} logicalToNewSlug
 * @param {number} offsetX
 * @param {number} offsetY
 */
export function expandStampForPlacement(targetZoneId, stampRoomsMap, stampPositionsDoc, logicalToNewSlug, offsetX, offsetY) {
  /** @type {string[]} */
  const newSlugs = [];

  /** @type {Record<string, object>} */
  const outRooms = {};
  /** @type {Record<string, object>} */
  const outPositions = {};

  const stampLogicalSet = new Set(Object.keys(stampRoomsMap));

  for (const [lk, yamlIn] of Object.entries(stampRoomsMap)) {
    const newSlug = logicalToNewSlug[lk];
    if (!newSlug) continue;
    const y = deepClone(yamlIn || {});
    y.id = `${targetZoneId}:${newSlug}`;
    y.zone = targetZoneId;
    delete y.slug;

    const exits = y.exits && typeof y.exits === "object" ? { ...y.exits } : {};
    y.exits = {};
    for (const [dir, ex] of Object.entries(exits)) {
      if (!ex || typeof ex !== "object") continue;
      const dest = String(ex.destination || "").trim();
      let peerLogical = null;
      if (dest.includes(":")) {
        const [z, s] = dest.split(":", 2);
        if (z === STAMP_ZONE_ID && stampLogicalSet.has(s)) peerLogical = s;
      } else if (stampLogicalSet.has(dest)) {
        peerLogical = dest;
      }
      if (!peerLogical || !logicalToNewSlug[peerLogical]) continue;
      const next = { ...ex };
      next.destination = logicalToNewSlug[peerLogical];
      y.exits[dir] = next;
    }

    outRooms[newSlug] = y;

    const p = stampPositionsDoc.positions?.[lk] || {};
    outPositions[newSlug] = {
      ...p,
      x: (Number(p.x) || 0) + offsetX,
      y: (Number(p.y) || 0) + offsetY,
    };
    newSlugs.push(newSlug);
  }

  return { outRooms, outPositions, newSlugs };
}

/**
 * Build new slug map: logical -> new zone slug using room display name or logical key as base.
 * @param {string[]} logicalKeys
 * @param {Record<string, object>} stampRoomsMap
 * @param {string} stampSlug
 * @param {Set<string>} usedSlugs
 */
export function buildPlacementSlugMap(logicalKeys, stampRoomsMap, stampSlug, usedSlugs) {
  const logicalToNew = {};
  const shortStamp = String(stampSlug || "stamp")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 24) || "stamp";
  for (const lk of logicalKeys) {
    const room = stampRoomsMap[lk] || {};
    const name = String(room.name || "").trim();
    const base =
      name && name !== "?"
        ? `${shortStamp}_${name.replace(/[^a-zA-Z0-9_-]+/g, "_").toLowerCase().slice(0, 32)}_${lk}`
        : `${shortStamp}_${lk}`;
    logicalToNew[lk] = allocStampPlaceSlug(base, usedSlugs);
  }
  return logicalToNew;
}
