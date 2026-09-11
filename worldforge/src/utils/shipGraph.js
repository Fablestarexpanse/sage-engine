import { MarkerType } from "@xyflow/react";
import { deepClone } from "./clone.js";
import { COLORS_DARK } from "../theme.js";
import { oppositeDir } from "./zoneGraph.js";

export function buildShipFlow(shipId, shipDoc, layoutDoc, opts = {}) {
  const { colors: COLORS = COLORS_DARK } = opts;
  const ship = shipDoc?.ship || shipDoc || {};
  const rooms = Array.isArray(ship.rooms) ? ship.rooms : [];
  const prefix = `ship:${shipId}:`;
  const known = new Set();
  for (const r of rooms) {
    if (r?.id) known.add(prefix + r.id);
  }
  const pos = layoutDoc?.positions || {};
  const nodes = [];
  let i = 0;
  for (const r of rooms) {
    if (!r?.id) continue;
    const rid = prefix + r.id;
    const p = pos[r.id] || { x: (i % 4) * 200, y: Math.floor(i / 4) * 120 };
    const desc = r.description || {};
    const hasDesc = typeof desc === "object" ? Boolean(String(desc.base || "").trim()) : Boolean(String(desc || "").trim());
    nodes.push({
      id: rid,
      type: "shipRoom",
      position: { x: Number(p.x) || 0, y: Number(p.y) || 0 },
      data: {
        slug: r.id,
        label: r.name || r.id,
        roomType: r.type || "?",
        depth: 0,
        hasDescription: hasDesc,
        entityCount: 0,
        exitCount: Object.keys(r.exits || {}).length,
        raw: r,
      },
    });
    i += 1;
  }
  const edges = [];
  const seen = new Set();
  for (const r of rooms) {
    if (!r?.id) continue;
    const sourceId = prefix + r.id;
    const exits = r.exits && typeof r.exits === "object" ? r.exits : {};
    for (const [direction, ex] of Object.entries(exits)) {
      if (!ex || typeof ex !== "object") continue;
      let targetId = null;
      const dest = String(ex.destination || "");
      if (dest.startsWith("self:")) {
        const tail = dest.slice(5);
        const cand = prefix + tail;
        if (known.has(cand)) targetId = cand;
      } else if (known.has(dest)) targetId = dest;
      if (!targetId) continue;
      const eid = `${sourceId}|${direction}|${targetId}`;
      if (seen.has(eid)) continue;
      seen.add(eid);
      const dlow = String(direction).toLowerCase();
      edges.push({
        id: eid,
        source: sourceId,
        target: targetId,
        sourceHandle: dlow,
        targetHandle: oppositeDir(dlow),
        type: "exit",
        markerEnd: { type: MarkerType.ArrowClosed, color: COLORS.borderActive, width: 18, height: 18 },
        data: { direction: String(direction), description: String(ex.description || ""), oneWay: Boolean(ex.one_way) },
      });
    }
  }
  return { nodes, edges };
}

export function roomsArrayFromDoc(shipDoc) {
  const ship = shipDoc?.ship || shipDoc || {};
  return Array.isArray(ship.rooms) ? ship.rooms : [];
}

export function updateRoomInShipDoc(shipDoc, localId, roomData) {
  const next = deepClone(shipDoc || { ship: { rooms: [] } });
  const ship = next.ship || (next.ship = {});
  ship.rooms = Array.isArray(ship.rooms) ? [...ship.rooms] : [];
  const idx = ship.rooms.findIndex((r) => r.id === localId);
  if (idx >= 0) ship.rooms[idx] = roomData;
  else ship.rooms.push(roomData);
  return next;
}

export function deleteRoomFromShipDoc(shipDoc, localId) {
  const next = deepClone(shipDoc || { ship: { rooms: [] } });
  const ship = next.ship || (next.ship = {});
  ship.rooms = (ship.rooms || []).filter((r) => r.id !== localId);
  return next;
}
