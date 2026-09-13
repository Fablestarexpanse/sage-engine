import { Position } from "@xyflow/react";

/**
 * Rotate a point like CSS `transform: rotate(deg)` clockwise, origin (0,0).
 * Axes: +x right, +y down (React Flow / screen).
 */
export function rotateCWCanvas(x, y, deg) {
  const r = (-deg * Math.PI) / 180;
  const c = Math.cos(r);
  const s = Math.sin(r);
  return { x: x * c + y * s, y: -x * s + y * c };
}

const MAP = {
  north: { x: 0, y: -1 },
  east: { x: 1, y: 0 },
  south: { x: 0, y: 1 },
  west: { x: -1, y: 0 },
};

const MAP_DIAG = {
  northwest: { x: -1, y: -1 },
  northeast: { x: 1, y: -1 },
  southwest: { x: -1, y: 1 },
  southeast: { x: 1, y: 1 },
};

/** Pull ports slightly inside the outline so they do not sit on @xyflow/node-resizer corner/side handles. */
const PORT_INSET_FROM_EDGE_PX = 14;
const PORT_INSET_FROM_CORNER_PX = 22;

/** Pick Top/Right/Bottom/Left for React Flow handle routing from outward normal (parent coords). */
export function flowPositionFromOutwardNormal(nx, ny) {
  if (Math.abs(ny) >= Math.abs(nx)) return ny < 0 ? Position.Top : Position.Bottom;
  return nx < 0 ? Position.Left : Position.Right;
}

function buildLocalEdges(hw, hh) {
  return [
    { mid: { x: 0, y: -hh }, n: { x: 0, y: -1 }, a: { x: -hw, y: -hh }, b: { x: hw, y: -hh } },
    { mid: { x: hw, y: 0 }, n: { x: 1, y: 0 }, a: { x: hw, y: -hh }, b: { x: hw, y: hh } },
    { mid: { x: 0, y: hh }, n: { x: 0, y: 1 }, a: { x: hw, y: hh }, b: { x: -hw, y: hh } },
    { mid: { x: -hw, y: 0 }, n: { x: -1, y: 0 }, a: { x: -hw, y: hh }, b: { x: -hw, y: -hh } },
  ];
}

function pickEdgeForMapNormal(hw, hh, rotationDeg, mapNx, mapNy) {
  const edges = buildLocalEdges(hw, hh);
  let best = edges[0];
  let bestDot = -Infinity;
  for (const e of edges) {
    const nr = rotateCWCanvas(e.n.x, e.n.y, rotationDeg);
    const dot = nr.x * mapNx + nr.y * mapNy;
    if (dot > bestDot) {
      bestDot = dot;
      best = e;
    }
  }
  return best;
}

/**
 * Pixel position (center of port) and RF Handle position for a cardinal exit in **map / workspace** space.
 * @param {number} W
 * @param {number} H
 * @param {number} rotationDeg  CSS rotation of the room graphic (clockwise, degrees)
 * @param {'north'|'south'|'east'|'west'} exitId
 */
export function canvasLayoutCardinal(W, H, rotationDeg, exitId) {
  const map = MAP[exitId];
  if (!map || W <= 0 || H <= 0) return null;
  const hw = W / 2;
  const hh = H / 2;
  const e = pickEdgeForMapNormal(hw, hh, rotationDeg, map.x, map.y);
  const midIn = {
    x: e.mid.x - e.n.x * PORT_INSET_FROM_EDGE_PX,
    y: e.mid.y - e.n.y * PORT_INSET_FROM_EDGE_PX,
  };
  const p = rotateCWCanvas(midIn.x, midIn.y, rotationDeg);
  const nr = rotateCWCanvas(e.n.x, e.n.y, rotationDeg);
  return {
    left: W / 2 + p.x,
    top: H / 2 + p.y,
    position: flowPositionFromOutwardNormal(nr.x, nr.y),
    outwardNormal: nr,
  };
}

/**
 * Corner exit: vertex of the rectangle that best matches map diagonal (NE = up+right on screen).
 */
export function canvasLayoutCorner(W, H, rotationDeg, exitId) {
  const map = MAP_DIAG[exitId];
  if (!map || W <= 0 || H <= 0) return null;
  const hw = W / 2;
  const hh = H / 2;
  const verts = [
    { x: -hw, y: -hh },
    { x: hw, y: -hh },
    { x: hw, y: hh },
    { x: -hw, y: hh },
  ];
  let best = verts[0];
  let bestDot = -Infinity;
  for (const v of verts) {
    const pr = rotateCWCanvas(v.x, v.y, rotationDeg);
    const dot = pr.x * map.x + pr.y * map.y;
    if (dot > bestDot) {
      bestDot = dot;
      best = v;
    }
  }
  const len = Math.hypot(best.x, best.y) || 1;
  const inset = PORT_INSET_FROM_CORNER_PX;
  const midIn = {
    x: best.x - (best.x / len) * inset,
    y: best.y - (best.y / len) * inset,
  };
  const p = rotateCWCanvas(midIn.x, midIn.y, rotationDeg);
  const pos = flowPositionFromOutwardNormal(p.x, p.y);
  return {
    left: W / 2 + p.x,
    top: H / 2 + p.y,
    position: pos,
  };
}

const STAIRS_T = 0.22;

/**
 * Stairs up/down along the map-north or map-south face (same 22% offset as before).
 */
export function canvasLayoutStairs(W, H, rotationDeg, exitId) {
  if (W <= 0 || H <= 0) return null;
  const hw = W / 2;
  const hh = H / 2;
  const map = exitId === "up" ? MAP.north : MAP.south;
  const e = pickEdgeForMapNormal(hw, hh, rotationDeg, map.x, map.y);
  const ar = rotateCWCanvas(e.a.x, e.a.y, rotationDeg);
  const br = rotateCWCanvas(e.b.x, e.b.y, rotationDeg);
  const t = STAIRS_T;
  const mx = ar.x + t * (br.x - ar.x);
  const my = ar.y + t * (br.y - ar.y);
  const nr = rotateCWCanvas(e.n.x, e.n.y, rotationDeg);
  return {
    left: W / 2 + mx,
    top: H / 2 + my,
    position: flowPositionFromOutwardNormal(nr.x, nr.y),
  };
}
