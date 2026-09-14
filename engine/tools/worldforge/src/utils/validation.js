import { resolveExitDestination } from "./zoneGraph.js";

/**
 * @typedef {Object} ZoneValidationCtx
 * @property {string} [zoneId] Zone being validated (used to label cross-zone exits).
 * @property {string[]} [entityIds] Known entity template ids — spawns referencing others error.
 * @property {string[]} [itemIds] Known item ids — loot referencing others errors.
 * @property {string[]} [roomTypes] The world's room types; other types error (empty: unchecked).
 * @property {string[]} [exitDirs] The world's exit directions; others error (empty: unchecked).
 * @property {Object<string, string[]>} [entityLoot] Map of entity id → loot item ids.
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
 *   plus the same fields as {@link ZoneValidationCtx}.
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
  const allRoomIds = new Set(ctx.allRoomIds || nodes.map((n) => n.id));

  edges.forEach((e) => {
    connected.add(e.source);
    connected.add(e.target);
  });

  const slugById = new Map();
  nodes.forEach((n) => {
    if (n.data?.slug) slugById.set(n.id, n.data.slug);
  });

  // The world's declared room types and exit directions (content.schema.json), when it has them.
  const typeSet = new Set(ctx.roomTypes || []);
  const dirSet = new Set(ctx.exitDirs || []);
  nodes.forEach((n) => {
    const raw = n.data?.raw || {};
    const label = n.data?.label || n.id;
    if (typeSet.size && raw.type && !typeSet.has(raw.type)) {
      issues.push({ level: "error", msg: `Room type "${raw.type}" is not one of this world's: ${label}`, nodeId: n.id });
    }
    if (dirSet.size && raw.exits && typeof raw.exits === "object") {
      for (const dir of Object.keys(raw.exits)) {
        if (!dirSet.has(dir)) {
          issues.push({ level: "error", msg: `Exit direction "${dir}" is not one of this world's: ${label}`, nodeId: n.id });
        }
      }
    }
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

  // Feature density (Epitaph/Griffin metric, docs/design/EPITAPH_LESSONS.md B5):
  // gameplay draws (features + spawns + hazards + ambient) per room. Below 0.5
  // the zone is mostly empty corridors — warn, don't error.
  if (nodes.length > 1) {
    let draws = 0;
    nodes.forEach((n) => {
      const raw = n.data?.raw || {};
      draws += Array.isArray(raw.features) ? raw.features.length : 0;
      draws += Array.isArray(raw.entity_spawns) ? raw.entity_spawns.length : 0;
      draws += Array.isArray(raw.hazards) ? raw.hazards.length : 0;
      if (raw.ambient && Array.isArray(raw.ambient.lines) && raw.ambient.lines.length) draws += 1;
    });
    const density = draws / nodes.length;
    if (density < 0.5) {
      issues.push({
        level: "warn",
        msg: `Low feature density: ${density.toFixed(2)} (${draws} draws / ${nodes.length} rooms; aim ≥ 0.5 — add features, spawns, hazards or ambient)`,
      });
    } else {
      issues.push({
        level: "info",
        msg: `Feature density ${density.toFixed(2)} (${draws} draws / ${nodes.length} rooms)`,
      });
    }
  }

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
