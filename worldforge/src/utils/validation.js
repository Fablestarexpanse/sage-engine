import { resolveExitDestination } from "./zoneGraph.js";

/**
 * @typedef {Object} ZoneValidationCtx
 * @property {string} [zoneId] Zone being validated (used to label cross-zone exits).
 * @property {string[]} [entityIds] Known entity template ids — spawns referencing others error.
 * @property {string[]} [itemIds] Known item ids — loot referencing others errors.
 * @property {string[]} [glyphIds] Known glyph ids — prerequisites referencing others error.
 * @property {Object<string, string[]>} [entityLoot] Map of entity id → loot item ids.
 * @property {Object<string, {prerequisites?: string[]}>} [glyphs] Glyph docs keyed by id.
 * @property {string[]} [allRoomIds] Every room id across zones (for cross-zone exit checks).
 */

/**
 * @typedef {Object} ExternalExitRef
 * @property {string} from Source room id.
 * @property {string} direction Exit direction.
 * @property {string} destination Target room id (usually in another zone).
 */

/**
 * @param {import('@xyflow/react').Node[]} nodes
 * @param {import('@xyflow/react').Edge[]} edges
 * @param {ZoneValidationCtx & { externalExits?: ExternalExitRef[] }} [opts] Validation context; `externalExits`
 *   plus the same fields as {@link ZoneValidationCtx}, matching the options-object convention used by
 *   `collectItemIssues` in itemValidation.js.
 * @returns {{level: "error"|"warn", msg: string, nodeId?: string}[]}
 */
export function runZoneValidation(nodes, edges, opts = {}) {
  const { externalExits = [], ...ctx } = opts;
  const issues = [];
  const ids = new Set(nodes.map((n) => n.id));
  const connected = new Set();
  const zoneId = ctx.zoneId || "";
  const entitySet = new Set(ctx.entityIds || []);
  const itemSet = new Set(ctx.itemIds || []);
  const glyphSet = new Set(ctx.glyphIds || []);
  const allRoomIds = new Set(ctx.allRoomIds || nodes.map((n) => n.id));

  edges.forEach((e) => {
    connected.add(e.source);
    connected.add(e.target);
  });

  const slugById = new Map();
  nodes.forEach((n) => {
    if (n.data?.slug) slugById.set(n.id, n.data.slug);
  });

  nodes.forEach((n) => {
    const d = n.data || {};
    if (!d.hasDescription) {
      issues.push({ level: "warn", msg: `Missing description: ${d.label || n.id}`, nodeId: n.id });
    }
  });

  nodes.forEach((n) => {
    if (!connected.has(n.id) && nodes.length > 1) {
      issues.push({ level: "warn", msg: `Disconnected room: ${n.data?.label || n.id}`, nodeId: n.id });
    }
  });

  edges.forEach((e) => {
    if (!ids.has(e.source) || !ids.has(e.target)) {
      issues.push({ level: "error", msg: `Broken edge ${e.id}` });
    }
  });

  edges.forEach((e) => {
    const tgtSlug = slugById.get(e.target);
    let mutualYaml = false;
    if (tgtSlug && ctx.roomsMap && typeof ctx.roomsMap === "object") {
      const room = ctx.roomsMap[tgtSlug];
      const exits = room?.exits && typeof room.exits === "object" ? room.exits : {};
      for (const ex of Object.values(exits)) {
        const tid = resolveExitDestination(zoneId, String(ex?.destination || ""), ids);
        if (tid === e.source) {
          mutualYaml = true;
          break;
        }
      }
    }
    const rev = mutualYaml;
    const oneWay = Boolean(e.data?.oneWay);
    if (!rev && e.data?.direction && !oneWay) {
      issues.push({
        level: "warn",
        msg: `Asymmetric exit (no return, not marked one_way): ${e.source} → ${e.target} (${e.data.direction})`,
        nodeId: e.source,
        edgeId: e.id,
      });
    }
    if (!rev && oneWay) {
      issues.push({
        level: "info",
        msg: `One-way: ${e.source} → ${e.target} (${e.data.direction})`,
        nodeId: e.source,
        edgeId: e.id,
      });
    }
  });

  externalExits.forEach((ex) => {
    issues.push({
      level: "info",
      msg: `External exit ${ex.from} ${ex.direction} → ${ex.destination}`,
    });
  });

  // Self-referencing exit
  edges.forEach((e) => {
    if (e.source === e.target) {
      issues.push({
        level: "error",
        msg: `Self-referencing exit: ${e.source} (${e.data?.direction})`,
        nodeId: e.source,
        edgeId: e.id,
      });
    }
  });

  // Orphaned: no exits in YAML
  nodes.forEach((n) => {
    const raw = n.data?.raw || {};
    const ex = raw.exits && typeof raw.exits === "object" ? raw.exits : {};
    if (Object.keys(ex).length === 0 && nodes.length > 1) {
      issues.push({
        level: "warn",
        msg: `Orphaned room (no exits in YAML): ${n.data?.label || n.id}`,
        nodeId: n.id,
      });
    }
  });

  // Dead-end: 0 or 1 exit edge (internal graph)
  nodes.forEach((n) => {
    const out = edges.filter((e) => e.source === n.id || e.target === n.id);
    const uniq = new Set(out.map((e) => (e.source === n.id ? e.target : e.source)));
    if (uniq.size <= 1 && nodes.length > 1) {
      issues.push({
        level: "info",
        msg: `Dead-end (≤1 connected neighbor): ${n.data?.label || n.id}`,
        nodeId: n.id,
      });
    }
  });

  // Broken exit destination to unknown room (internal edges only - external already listed)
  edges.forEach((e) => {
    if (!allRoomIds.has(e.target)) {
      issues.push({ level: "error", msg: `Broken exit target: ${e.id}`, nodeId: e.source, edgeId: e.id });
    }
  });

  // Depth discontinuity
  const depthById = new Map(nodes.map((n) => [n.id, Number(n.data?.depth ?? 0)]));
  edges.forEach((e) => {
    const da = depthById.get(e.source) ?? 0;
    const db = depthById.get(e.target) ?? 0;
    if (Math.abs(da - db) >= 2) {
      issues.push({
        level: "info",
        msg: `Depth jump ${da} → ${db}: ${e.source} to ${e.target}`,
        nodeId: e.source,
        edgeId: e.id,
      });
    }
  });

  // Features missing description
  nodes.forEach((n) => {
    const feats = n.data?.raw?.features;
    if (!Array.isArray(feats)) return;
    feats.forEach((f, idx) => {
      if (f && f.name && !String(f.description || "").trim()) {
        issues.push({
          level: "warn",
          msg: `Feature "${f.name}" missing description (${n.data?.label || n.id})`,
          nodeId: n.id,
        });
      }
    });
  });

  // Entity spawns
  nodes.forEach((n) => {
    const spawns = n.data?.raw?.entity_spawns;
    if (!Array.isArray(spawns)) return;
    spawns.forEach((s) => {
      const tid = s?.template;
      if (tid && !entitySet.has(tid)) {
        issues.push({
          level: "error",
          msg: `Unknown entity template "${tid}" in ${n.data?.label || n.id}`,
          nodeId: n.id,
        });
      }
    });
  });

  // Loot on entities (ctx.entityLoot: map entityId -> loot ids) — optional
  if (ctx.entityLoot && typeof ctx.entityLoot === "object") {
    for (const [eid, loot] of Object.entries(ctx.entityLoot)) {
      if (!Array.isArray(loot)) continue;
      for (const itemId of loot) {
        if (itemId && !itemSet.has(itemId)) {
          issues.push({
            level: "error",
            msg: `Entity ${eid} loot references unknown item "${itemId}"`,
          });
        }
      }
    }
  }

  // Glyph prerequisites (zone editor skips if no glyphs in ctx)
  if (glyphSet.size) {
    for (const gid of glyphSet) {
      const g = ctx.glyphs?.[gid];
      const pre = g?.prerequisites;
      if (!Array.isArray(pre)) continue;
      for (const p of pre) {
        if (p && !glyphSet.has(p)) {
          issues.push({
            level: "error",
            msg: `Glyph ${gid} prerequisite unknown: ${p}`,
          });
        }
      }
    }
  }

  return issues;
}

export function validationCounts(issues) {
  let err = 0;
  let warn = 0;
  for (const i of issues || []) {
    if (i.level === "error") err += 1;
    else if (i.level === "warn") warn += 1;
  }
  return { err, warn };
}
