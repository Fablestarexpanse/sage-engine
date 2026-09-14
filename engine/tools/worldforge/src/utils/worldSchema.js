import { useMemo } from "react";
import { joinPaths } from "./paths.js";

/** The file each SAGE world package keeps beside world.toml (`python -m sage schema export`). */
export const SCHEMA_FILE = "content.schema.json";

export const ALL_DIRECTIONS = [
  "north",
  "south",
  "east",
  "west",
  "northeast",
  "northwest",
  "southeast",
  "southwest",
  "up",
  "down",
];

/** `<package>/content.schema.json` for a `<package>/content/world` root. */
export function schemaPathFor(worldRoot) {
  if (!worldRoot) return null;
  const sep = worldRoot.includes("\\") ? "\\" : "/";
  const parts = worldRoot.replace(/[/\\]+$/, "").split(/[/\\]/);
  if (parts.length < 3) return null;
  return joinPaths(parts.slice(0, -2).join(sep) || sep, SCHEMA_FILE);
}

/** Read the package's exported schema; null when the folder is not a world package (or has none). */
export async function loadWorldSchema(fs, worldRoot) {
  const path = schemaPathFor(worldRoot);
  if (!path || !(await fs.pathExists(path))) return null;
  try {
    const doc = JSON.parse(await fs.readText(path));
    return doc && typeof doc === "object" ? doc : null;
  } catch {
    return null;
  }
}

/**
 * The lists editors offer for a world. From the schema (world.toml) when present; otherwise the
 * room types already used in the loaded content, every direction and no declared slots.
 * @returns {{ roomTypes: string[], exitDirs: string[], slots: string[], declared: boolean }}
 */
export function worldLists(schema, zones) {
  const content = schema?.content || {};
  const declaredTypes = Array.isArray(content.room_types) ? content.room_types : [];
  const declaredDirs = Array.isArray(content.exit_dirs) ? content.exit_dirs : [];
  let roomTypes = declaredTypes;
  if (!roomTypes.length) {
    const seen = new Set();
    for (const zone of Object.values(zones || {})) {
      for (const room of Object.values(zone?.rooms || {})) {
        if (room?.type) seen.add(String(room.type));
      }
    }
    roomTypes = [...seen].sort();
  }
  return {
    roomTypes,
    exitDirs: declaredDirs.length ? declaredDirs : ALL_DIRECTIONS,
    slots: Array.isArray(content.equipment_slots) ? content.equipment_slots : [],
    declared: Boolean(declaredTypes.length || declaredDirs.length),
  };
}

/** A new room's type: the preferred one if the world allows it, else the world's first type. */
export function pickRoomType(preferred, roomTypes) {
  if (!roomTypes?.length || roomTypes.includes(preferred)) return preferred || roomTypes?.[0] || "room";
  return roomTypes[0];
}

export function useWorldLists(schema, zones) {
  return useMemo(() => worldLists(schema, zones), [schema, zones]);
}
