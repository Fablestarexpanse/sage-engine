import { joinPaths } from "./paths.js";

/** Normalize `icon` field: path relative to `content/world/items/`. */
export function resolveItemIconDiskPath(worldRoot, icon) {
  if (!worldRoot || !icon || typeof icon !== "string") return null;
  let rel = icon.trim().replace(/^[/\\]+/, "");
  if (rel.startsWith("http://") || rel.startsWith("https://")) return null;
  if (rel.toLowerCase().startsWith("items/")) rel = rel.slice(6).replace(/^[/\\]+/, "");
  return joinPaths(worldRoot, "items", rel);
}

/**
 * Validation-collector convention: every collector in this module (async, fs injected
 * for testability) and `runZoneValidation` in validation.js (sync, no fs) take their
 * identifying arguments positionally and everything else — context plus any optional
 * knobs — as a single trailing options object. Keep new collectors consistent with this.
 *
 * @param {object} opts
 * @param {string} opts.worldRoot
 * @param {Record<string, object>} opts.items
 * @param {Record<string, object>} opts.entities
 * @param {string[]} opts.itemIds
 * @param {typeof import("./fsBridge.js")} opts.fs
 * @returns {Promise<{ level: string, msg: string, itemId?: string }[]>}
 */
export async function collectItemIssues({ worldRoot, items, entities, itemIds, fs }) {
  const issues = [];
  const set = new Set(itemIds || []);

  for (const id of itemIds || []) {
    const it = items[id];
    if (!it) continue;
    if (it._parseError) {
      issues.push({ level: "error", msg: `YAML parse error: items/${id}.yaml`, itemId: id });
      continue;
    }
    const icon = it.icon;
    if (icon && typeof icon === "string" && !/^https?:\/\//i.test(icon)) {
      const disk = resolveItemIconDiskPath(worldRoot, icon);
      if (disk && !(await fs.pathExists(disk))) {
        issues.push({ level: "warn", msg: `Missing icon file (${icon}): ${id}`, itemId: id });
      }
    }
    const t = String(it.type || "misc").toLowerCase();
    if (t === "weapon" && !it.weapon_profile && !(it.stat_bonuses && Object.keys(it.stat_bonuses).length)) {
      issues.push({ level: "info", msg: `Weapon "${id}" has no weapon_profile or stat_bonuses`, itemId: id });
    }
    if ((t === "weapon" || t === "armor") && !it.equip_slot) {
      issues.push({ level: "warn", msg: `${t} "${id}" has no equip_slot`, itemId: id });
    }
    if (it.on_use && t !== "consumable" && t !== "misc") {
      issues.push({ level: "info", msg: `Item "${id}" has on_use but type is ${t}`, itemId: id });
    }
  }

  for (const [eid, ent] of Object.entries(entities || {})) {
    const loot = Array.isArray(ent?.loot) ? ent.loot : [];
    for (const lid of loot) {
      const L = String(lid || "").trim();
      if (!L) continue;
      if (!set.has(L)) {
        issues.push({ level: "warn", msg: `Entity "${eid}" loot references missing item: ${L}` });
      }
    }
  }

  return issues;
}
