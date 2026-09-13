import { DEFAULT_ROOM_NODE_H, DEFAULT_ROOM_NODE_W } from "./zoneGraph.js";

function readSize(style, wFallback, hFallback) {
  const s = style || {};
  const pw = typeof s.width === "number" ? s.width : parseFloat(String(s.width ?? "").replace(/px$/i, ""));
  const ph = typeof s.height === "number" ? s.height : parseFloat(String(s.height ?? "").replace(/px$/i, ""));
  return {
    w: Number.isFinite(pw) && pw > 0 ? pw : wFallback,
    h: Number.isFinite(ph) && ph > 0 ? ph : hFallback,
  };
}

/** Flow-space AABB for intersection / layout (top-left origin). */
export function getRoomRectFlow(n, wFallback = DEFAULT_ROOM_NODE_W, hFallback = DEFAULT_ROOM_NODE_H) {
  const { w, h } = readSize(n.style, wFallback, hFallback);
  return { x: n.position.x, y: n.position.y, w, h };
}

export function flowRectIntersects(sel, r) {
  const x2 = r.x + r.w;
  const y2 = r.y + r.h;
  return !(r.x > sel.x2 || x2 < sel.x1 || r.y > sel.y2 || y2 < sel.y1);
}

/**
 * @param {import('@xyflow/react').Node[]} rooms type room, unlocked
 * @returns {{ id: string, position: { x: number, y: number }, slug?: string }[]}
 */
export function alignRoomsLeft(rooms) {
  if (rooms.length < 2) return [];
  const xs = rooms.map((n) => getRoomRectFlow(n).x);
  const minX = Math.min(...xs);
  return rooms.map((n) => ({ id: n.id, slug: n.data?.slug, position: { x: minX, y: n.position.y } }));
}

export function alignRoomsRight(rooms) {
  if (rooms.length < 2) return [];
  const boxes = rooms.map((n) => ({ n, ...getRoomRectFlow(n) }));
  const maxR = Math.max(...boxes.map((b) => b.x + b.w));
  return boxes.map(({ n, w, y }) => ({ id: n.id, slug: n.data?.slug, position: { x: maxR - w, y } }));
}

export function alignRoomsTop(rooms) {
  if (rooms.length < 2) return [];
  const minY = Math.min(...rooms.map((n) => getRoomRectFlow(n).y));
  return rooms.map((n) => ({ id: n.id, slug: n.data?.slug, position: { x: n.position.x, y: minY } }));
}

export function alignRoomsBottom(rooms) {
  if (rooms.length < 2) return [];
  const boxes = rooms.map((n) => ({ n, ...getRoomRectFlow(n) }));
  const maxB = Math.max(...boxes.map((b) => b.y + b.h));
  return boxes.map(({ n, w, h, x }) => ({ id: n.id, slug: n.data?.slug, position: { x, y: maxB - h } }));
}

export function alignRoomsCenterX(rooms) {
  if (rooms.length < 2) return [];
  const boxes = rooms.map((n) => ({ n, ...getRoomRectFlow(n) }));
  const cx =
    boxes.reduce((s, b) => s + b.x + b.w / 2, 0) / boxes.length;
  return boxes.map(({ n, w, x, y }) => ({ id: n.id, slug: n.data?.slug, position: { x: cx - w / 2, y } }));
}

export function alignRoomsCenterY(rooms) {
  if (rooms.length < 2) return [];
  const boxes = rooms.map((n) => ({ n, ...getRoomRectFlow(n) }));
  const cy =
    boxes.reduce((s, b) => s + b.y + b.h / 2, 0) / boxes.length;
  return boxes.map(({ n, h, x, y }) => ({ id: n.id, slug: n.data?.slug, position: { x, y: cy - h / 2 } }));
}

/** Equal gaps between adjacent rooms by x (left → right); keeps left/right extent of span. */
export function distributeRoomsHorizontally(rooms) {
  if (rooms.length < 3) return [];
  const boxes = rooms
    .map((n) => ({ n, ...getRoomRectFlow(n) }))
    .sort((a, b) => a.x - b.x);
  const n = boxes.length;
  const left = boxes[0].x;
  const right = boxes[n - 1].x + boxes[n - 1].w;
  const totalW = boxes.reduce((s, b) => s + b.w, 0);
  const inner = right - left - totalW;
  const gap = inner / (n - 1);
  const out = [];
  let x = left;
  for (let i = 0; i < n; i++) {
    const b = boxes[i];
    out.push({ id: b.n.id, slug: b.n.data?.slug, position: { x, y: b.n.position.y } });
    x += b.w + gap;
  }
  return out;
}

/** Equal gaps between adjacent rooms by y (top → bottom); keeps top/bottom extent. */
export function distributeRoomsVertically(rooms) {
  if (rooms.length < 3) return [];
  const boxes = rooms
    .map((n) => ({ n, ...getRoomRectFlow(n) }))
    .sort((a, b) => a.y - b.y);
  const n = boxes.length;
  const top = boxes[0].y;
  const bottom = boxes[n - 1].y + boxes[n - 1].h;
  const totalH = boxes.reduce((s, b) => s + b.h, 0);
  const inner = bottom - top - totalH;
  const gap = inner / (n - 1);
  const out = [];
  let y = top;
  for (let i = 0; i < n; i++) {
    const b = boxes[i];
    out.push({ id: b.n.id, slug: b.n.data?.slug, position: { x: b.n.position.x, y } });
    y += b.h + gap;
  }
  return out;
}
