import { MarkerType } from "@xyflow/react";
import { COLORS_DARK } from "../theme.js";

export const DEFAULT_ROOM_NODE_W = 176;
export const DEFAULT_ROOM_NODE_H = 108;

export function oppositeDir(direction) {
  const d = String(direction || "").toLowerCase();
  return (
    {
      north: "south",
      south: "north",
      east: "west",
      west: "east",
      northeast: "southwest",
      southwest: "northeast",
      northwest: "southeast",
      southeast: "northwest",
      up: "down",
      down: "up",
    }[d] ?? null
  );
}

export function resolveExitDestination(zoneId, dest, knownIds) {
  if (!dest || typeof dest !== "string") return null;
  const d = dest.trim();
  if (d.startsWith("self:") || d.startsWith("@") || !d) return null;
  if (d.includes(":")) return knownIds.has(d) ? d : null;
  const cand = `${zoneId}:${d}`;
  return knownIds.has(cand) ? cand : null;
}

/**
 * @param {string} zoneId
 * @param {Record<string, object>} roomsMap slug -> room yaml
 * @param {object} positionsDoc parsePositionsDoc result
 * @param {object} opts { mutedEdgeSet: Set<string> }
 */
export function buildZoneFlow(zoneId, roomsMap, positionsDoc, opts = {}) {
  const { mutedEdgeSet = new Set(), colors: COLORS = COLORS_DARK } = opts;
  const positions = positionsDoc.positions || {};
  const slugs = Object.keys(roomsMap).sort();
  const knownIds = new Set();
  for (const slug of slugs) {
    const data = roomsMap[slug] || {};
    knownIds.add(String(data.id || `${zoneId}:${slug}`));
  }

  const nodes = [];
  let i = 0;
  for (const slug of slugs) {
    const data = roomsMap[slug] || {};
    const rid = String(data.id || `${zoneId}:${slug}`);
    const pos = positions[slug] || {
      x: (i % 6) * 220,
      y: Math.floor(i / 6) * 120,
    };
    const nw = Number(pos.width);
    const nh = Number(pos.height);
    const nodeStyle = {
      width: nw > 0 ? nw : DEFAULT_ROOM_NODE_W,
      height: nh > 0 ? nh : DEFAULT_ROOM_NODE_H,
    };
    const borderColor =
      typeof pos.border_color === "string" && /^#[0-9A-Fa-f]{3,8}$/.test(pos.border_color.trim())
        ? pos.border_color.trim()
        : null;
    const desc = data.description || {};
    const hasDesc = typeof desc === "object" ? Boolean(String(desc.base || "").trim()) : Boolean(String(desc || "").trim());
    const exits = data.exits && typeof data.exits === "object" ? data.exits : {};
    const spawns = Array.isArray(data.entity_spawns) ? data.entity_spawns : [];
    let tags = data.tags || [];
    if (!(tags instanceof Array)) tags = tags ? [...tags] : [];
    const locked = Boolean(pos.locked);
    const rot = Number(pos.rotation);
    const rotation = Number.isFinite(rot) ? rot : 0;
    const parseError = Boolean(data._parseError);
    const label = parseError ? `⚠ ${slug}` : data.name || slug;
    const isPlaceholder = String(data.name || "").trim() === "?";

    /** Directions with an exit linked to another room in this zone (in-zone graph edge). */
    const linkedExitDirs = [];
    /** Directions with an exit in YAML but no in-zone graph edge (empty / external / unknown target). */
    const unlinkedExitDirs = [];
    for (const [direction, ex] of Object.entries(exits)) {
      if (!ex || typeof ex !== "object") continue;
      const dest = String(ex.destination || "");
      const targetId = resolveExitDestination(zoneId, dest, knownIds);
      const dlow = String(direction).toLowerCase();
      if (targetId) linkedExitDirs.push(dlow);
      else unlinkedExitDirs.push(dlow);
    }

    nodes.push({
      id: rid,
      type: "room",
      position: { x: Number(pos.x) || 0, y: Number(pos.y) || 0 },
      style: nodeStyle,
      data: {
        slug,
        label,
        roomId: rid,
        roomType: data.type || "?",
        depth: data.depth ?? 0,
        group: data.group,
        hasDescription: hasDesc,
        entityCount: spawns.length,
        exitCount: Object.keys(exits).length,
        linkedExitDirs,
        unlinkedExitDirs,
        tags,
        raw: data,
        locked,
        isPlaceholder,
        layoutBorderColor: borderColor,
        rotation,
        parseError,
      },
    });
    i += 1;
  }

  const edges = [];
  const edgeIds = new Set();
  const externalExits = [];

  for (const slug of slugs) {
    const data = roomsMap[slug] || {};
    const sourceId = String(data.id || `${zoneId}:${slug}`);
    const exits = data.exits && typeof data.exits === "object" ? data.exits : {};
    for (const [direction, ex] of Object.entries(exits)) {
      if (!ex || typeof ex !== "object") continue;
      const dest = String(ex.destination || "");
      const targetId = resolveExitDestination(zoneId, dest, knownIds);
      const edesc = String(ex.description || "");
      const oneWay = Boolean(ex.one_way);
      const mapLabel = String(ex.map_label || "").trim();
      if (targetId) {
        const eid = `${sourceId}|${direction}|${targetId}`;
        if (edgeIds.has(eid)) continue;
        edgeIds.add(eid);
        const dlow = String(direction).toLowerCase();
        const muted = mutedEdgeSet.has(eid);
        edges.push({
          id: eid,
          source: sourceId,
          target: targetId,
          sourceHandle: dlow,
          targetHandle: oppositeDir(dlow),
          type: "exit",
          markerEnd: { type: MarkerType.ArrowClosed, color: COLORS.borderActive, width: 18, height: 18 },
          data: {
            direction: String(direction),
            description: edesc,
            mapLabel: mapLabel || null,
            oneWay,
            muted,
            zoneId,
            sourceSlug: slug,
          },
        });
      } else {
        externalExits.push({
          from: sourceId,
          direction: String(direction),
          destination: dest,
          description: edesc,
        });
      }
    }
  }

  return { nodes, edges, externalExits };
}

/**
 * One link writes two in-zone exits (A→B and B→A), which becomes two React Flow edges.
 * Collapse mutual pairs to a single edge so one drag shows one arrow (stable: keep edge where source id sorts first).
 */
export function dedupeMutualBidirectionalEdges(edges) {
  const byPair = new Map();
  for (const e of edges) {
    const a = e.source;
    const b = e.target;
    const key = a < b ? `${a}|${b}` : `${b}|${a}`;
    if (!byPair.has(key)) byPair.set(key, []);
    byPair.get(key).push(e);
  }
  const out = [];
  for (const list of byPair.values()) {
    if (list.length === 2) {
      const [e1, e2] = list;
      if (e1.source === e2.target && e1.target === e2.source) {
        out.push(e1.source < e2.source ? e1 : e2);
        continue;
      }
    }
    out.push(...list);
  }
  return out;
}

export function mutedEdgeSetFromDoc(doc) {
  const s = new Set();
  const arr = doc.muted_edges || [];
  for (const e of arr) {
    if (typeof e === "string") s.add(e);
    else if (e && e.id) s.add(e.id);
  }
  return s;
}
