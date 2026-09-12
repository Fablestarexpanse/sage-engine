import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { unstable_batchedUpdates } from "react-dom";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  ConnectionMode,
  MarkerType,
  useReactFlow,
  ReactFlowProvider,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import yaml from "js-yaml";
import { joinPaths } from "../utils/paths.js";
import { parsePositionsDoc, serializePositionsDoc } from "../utils/positionsDoc.js";
import {
  buildZoneFlow,
  dedupeMutualBidirectionalEdges,
  DEFAULT_ROOM_NODE_H,
  DEFAULT_ROOM_NODE_W,
  mutedEdgeSetFromDoc,
  oppositeDir,
  resolveExitDestination,
} from "../utils/zoneGraph.js";
import {
  alignRoomsBottom,
  alignRoomsCenterX,
  alignRoomsCenterY,
  alignRoomsLeft,
  alignRoomsRight,
  alignRoomsTop,
  distributeRoomsHorizontally,
  distributeRoomsVertically,
  flowRectIntersects,
  getRoomRectFlow,
} from "../utils/layoutAlign.js";
import { layoutGraph } from "../utils/AutoLayout.js";
import { runZoneValidation, validationCounts } from "../utils/validation.js";
import RoomNode from "../nodes/RoomNode.jsx";
import NoteNode from "../nodes/NoteNode.jsx";
import ExitEdge from "../edges/ExitEdge.jsx";
import RoomPanel from "../panels/RoomPanel.jsx";
import ValidationPanel from "../components/ValidationPanel.jsx";
import TextPromptModal from "../components/TextPromptModal.jsx";
import GroupFormModal from "../components/GroupFormModal.jsx";
import SaveStampModal, { stampSlugFromDisplayName } from "../components/SaveStampModal.jsx";
import StampLibraryModal from "../components/StampLibraryModal.jsx";
import {
  saveStampBundle,
  loadStampBundle,
  expandStampForPlacement,
  buildPlacementSlugMap,
  stampFolderPath,
} from "../utils/stampBundle.js";
import { useTheme } from "../ThemeContext.jsx";
import * as fs from "../hooks/useFileSystem.js";
import { useContent } from "../hooks/useContentStore.js";
import { writeSnapEnabled } from "../hooks/useLocalSettings.js";

const nodeTypes = { room: RoomNode, note: NoteNode };
const edgeTypes = { exit: ExitEdge };

const SLUG_OK = (s) => /^[a-zA-Z0-9_-]+$/.test(s);
const floorLabel = (n) => (n === 0 ? "Ground" : n > 0 ? `F${n}` : `B${Math.abs(n)}`);

const UNDO_LIMIT = 40;

const CONN_DEBUG_PANEL_POS_KEY = "worldforge_conn_debug_panel_pos";

function readConnDebugPanelPos() {
  try {
    const raw = localStorage.getItem(CONN_DEBUG_PANEL_POS_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    if (
      typeof p.left === "number" &&
      typeof p.top === "number" &&
      Number.isFinite(p.left) &&
      Number.isFinite(p.top)
    ) {
      return { left: p.left, top: p.top };
    }
  } catch {
    /* ignore */
  }
  return null;
}

function clonePositionsDoc(doc) {
  return JSON.parse(JSON.stringify(doc ?? parsePositionsDoc(null)));
}

function normalizeRotationDeg(d) {
  const n = Number(d);
  if (!Number.isFinite(n)) return 0;
  return ((n % 360) + 360) % 360;
}

/** Deep clone room YAML for a duplicate: no exits/links, new id/zone/slug/name. */
function buildDuplicateRoomYaml(sourceRoom, zoneId, newSlug, fromSlug) {
  const copy = JSON.parse(JSON.stringify(sourceRoom || {}));
  copy.exits = {};
  copy.id = `${zoneId}:${newSlug}`;
  copy.zone = zoneId;
  const rawName = String(copy.name ?? "").trim();
  const baseLabel = rawName && rawName !== "?" ? rawName : String(fromSlug || newSlug).replace(/_/g, " ");
  copy.name = `${baseLabel} (copy)`;
  return copy;
}

/**
 * Match on-screen layout: `node.position` can diverge from the rendered box after resize/measure;
 * internals.positionAbsolute is the source of truth in @xyflow/react.
 */
function snapshotRoomNodeLayout(flow, n) {
  const internal = typeof flow.getInternalNode === "function" ? flow.getInternalNode(n.id) : undefined;
  const abs = internal?.internals?.positionAbsolute;
  const pos =
    abs && Number.isFinite(abs.x) && Number.isFinite(abs.y)
      ? { x: abs.x, y: abs.y }
      : { x: n.position.x, y: n.position.y };
  const style = { ...(n.style || {}) };
  const mw = internal?.measured?.width ?? n.measured?.width ?? n.width;
  const mh = internal?.measured?.height ?? n.measured?.height ?? n.height;
  if (typeof mw === "number" && mw > 0) style.width = mw;
  if (typeof mh === "number" && mh > 0) style.height = mh;
  return { position: pos, style };
}

function readNodeBox(style, wFallback, hFallback) {
  const s = style || {};
  const pw = typeof s.width === "number" ? s.width : parseFloat(String(s.width ?? "").replace(/px$/i, ""));
  const ph = typeof s.height === "number" ? s.height : parseFloat(String(s.height ?? "").replace(/px$/i, ""));
  return {
    width: Number.isFinite(pw) && pw > 0 ? pw : wFallback,
    height: Number.isFinite(ph) && ph > 0 ? ph : hFallback,
  };
}

/** DOM handle under pointer at release (compare to React Flow’s chosen target handle). */
function pickHandleUnderPointer(ev) {
  if (!ev || typeof ev.clientX !== "number" || typeof document.elementFromPoint !== "function") return null;
  const el = document.elementFromPoint(ev.clientX, ev.clientY);
  if (!el) return null;
  const h = el.closest?.(".react-flow__handle");
  if (!h) return null;
  return {
    nodeId: h.getAttribute("data-nodeid"),
    handleId: h.getAttribute("data-handleid"),
    dataId: h.getAttribute("data-id"),
  };
}

function ZoneEditorInner({
  zoneId,
  onZoneId,
  worldRoot,
  snapEnabled,
  setSnapEnabled,
  snapGrid,
  showYamlIds,
  connectionDebugLog = false,
  setConnectionDebugLog = () => {},
  nexusUrl,
  nexusToken,
  defaultRoomType,
}) {
  const { colors: COLORS, colorScheme } = useTheme();
  const tbBtn = useMemo(
    () => ({
      padding: "6px 10px",
      borderRadius: 6,
      border: `1px solid ${COLORS.border}`,
      background: COLORS.bgCard,
      color: COLORS.text,
      cursor: "pointer",
      fontSize: 11,
    }),
    [COLORS]
  );
  function MenuBtn({ onClick, children }) {
    return (
      <button
        type="button"
        onClick={onClick}
        style={{
          display: "block",
          width: "100%",
          textAlign: "left",
          padding: "6px 8px",
          border: "none",
          background: "transparent",
          color: COLORS.text,
          fontSize: 12,
          cursor: "pointer",
          borderRadius: 4,
        }}
      >
        {children}
      </button>
    );
  }
  const rf = useReactFlow();
  const rfRef = useRef(rf);
  rfRef.current = rf;
  const containerRef = useRef(null);
  const connDebugPanelRef = useRef(null);
  const [connDebugPanelPos, setConnDebugPanelPos] = useState(() => readConnDebugPanelPos());
  const suppressPaneContextUntilRef = useRef(0);
  const { zones, zoneIds, dispatch, entities, entityIds, items, itemIds, glyphs, glyphIds } = useContent();

  const [positionsDoc, setPositionsDoc] = useState(() => parsePositionsDoc(null));
  const [groups, setGroups] = useState([]);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const setNodesRef = useRef(setNodes);
  setNodesRef.current = setNodes;
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedSlug, setSelectedSlug] = useState(null);
  const [panelDraft, setPanelDraft] = useState(null);
  const [panelDirty, setPanelDirty] = useState(false);
  const [issues, setIssues] = useState([]);
  const [showVal, setShowVal] = useState(false);
  const [showStats, setShowStats] = useState(false);
  const [showGroups, setShowGroups] = useState(false);
  const [ctx, setCtx] = useState(null);
  const [statusMsg, setStatusMsg] = useState("");
  const [roomSlugModal, setRoomSlugModal] = useState(null);
  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [saveStampOpen, setSaveStampOpen] = useState(false);
  const [saveStampDraft, setSaveStampDraft] = useState(null);
  const saveStampDraftRef = useRef(null);
  const [stampLibraryOpen, setStampLibraryOpen] = useState(false);
  const [pendingStampPlace, setPendingStampPlace] = useState(null);
  const [pendingStairLink, setPendingStairLink] = useState(null);
  // { slug, ghostFloor, ghostDir: "up"|"down" }
  const [marqueeScreen, setMarqueeScreen] = useState(null);
  const [arrangeableSelectionCount, setArrangeableSelectionCount] = useState(0);
  const [currentFloor, setCurrentFloor] = useState(0);

  const positionsDocRef = useRef(positionsDoc);
  positionsDocRef.current = positionsDoc;
  saveStampDraftRef.current = saveStampDraft;
  const undoStackRef = useRef([]);
  const duplicateBusyRef = useRef(false);
  const stampPlaceBusyRef = useRef(false);
  const connectBusyRef = useRef(false);
  /** Same link twice in one gesture (double pointer-up / touch+mouse) — ignore second onConnect. */
  const lastConnectDedupeRef = useRef({ sig: "", t: 0 });
  const clearConnectionsBusyRef = useRef(false);
  const clearAllRoomsBusyRef = useRef(false);
  const connectionDragSeqRef = useRef(0);
  const connectionDragMetaRef = useRef(null);
  const [connectionDebugLines, setConnectionDebugLines] = useState([]);
  const connectionDebugLinesRef = useRef([]);

  const pushConnectionDebug = useCallback((kind, detail) => {
    if (!connectionDebugLog) return;
    const row = { t: new Date().toISOString(), kind, detail };
    console.info("[Fablestar WorldForger connection]", kind, detail);
    connectionDebugLinesRef.current = [row, ...connectionDebugLinesRef.current].slice(0, 80);
    setConnectionDebugLines([...connectionDebugLinesRef.current]);
  }, [connectionDebugLog]);

  const onConnDebugPanelHeaderPointerDown = useCallback((e) => {
    if (e.button !== 0 || e.target.closest("button")) return;
    const root = containerRef.current;
    const panel = connDebugPanelRef.current;
    if (!root || !panel) return;
    e.preventDefault();
    const rootR = root.getBoundingClientRect();
    const pr = panel.getBoundingClientRect();
    const curLeft = connDebugPanelPos != null ? connDebugPanelPos.left : pr.left - rootR.left;
    const curTop = connDebugPanelPos != null ? connDebugPanelPos.top : pr.top - rootR.top;
    const drag = { startX: e.clientX, startY: e.clientY, origLeft: curLeft, origTop: curTop };
    let lastPos = { left: curLeft, top: curTop };

    const onMove = (ev) => {
      const w = panel.offsetWidth;
      const h = panel.offsetHeight;
      const dx = ev.clientX - drag.startX;
      const dy = ev.clientY - drag.startY;
      let left = drag.origLeft + dx;
      let top = drag.origTop + dy;
      left = Math.max(4, Math.min(left, rootR.width - w - 4));
      top = Math.max(4, Math.min(top, rootR.height - h - 4));
      lastPos = { left, top };
      setConnDebugPanelPos(lastPos);
    };

    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      try {
        localStorage.setItem(CONN_DEBUG_PANEL_POS_KEY, JSON.stringify(lastPos));
      } catch {
        /* ignore */
      }
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }, [connDebugPanelPos]);

  const roomsMap = useMemo(() => zones[zoneId]?.rooms ?? {}, [zones, zoneId]);
  const zonesRef = useRef(zones);
  zonesRef.current = zones;

  const positionsPath = useMemo(() => joinPaths(worldRoot, "zones", zoneId, ".positions.json"), [worldRoot, zoneId]);
  const groupsPath = useMemo(() => joinPaths(worldRoot, "zones", zoneId, "groups.yaml"), [worldRoot, zoneId]);

  const roomIndexForPicker = useMemo(() => {
    const idx = {};
    for (const zid of zoneIds) {
      idx[zid] = zones[zid]?.rooms || {};
    }
    return idx;
  }, [zones, zoneIds]);

  /** Shared border value for selected unlocked rooms, or empty + mixed when they differ. */
  const selectionLayoutBorderDisplay = useMemo(() => {
    const sel = nodes.filter((n) => n.type === "room" && n.selected && !n.data?.locked);
    const slugs = [...new Set(sel.map((n) => n.data?.slug).filter(Boolean))];
    if (slugs.length === 0) return { value: "", mixed: false };
    const vals = slugs.map((s) => String(positionsDoc.positions?.[s]?.border_color ?? "").trim());
    const first = vals[0];
    const mixed = vals.some((v) => v !== first);
    return { value: mixed ? "" : first, mixed };
  }, [nodes, positionsDoc]);

  const allRoomIds = useMemo(() => {
    const s = new Set();
    for (const zid of zoneIds) {
      const rm = zones[zid]?.rooms || {};
      for (const [slug, data] of Object.entries(rm)) {
        s.add(String(data.id || `${zid}:${slug}`));
      }
    }
    return s;
  }, [zones, zoneIds]);

  const entityLootMap = useMemo(() => {
    const m = {};
    for (const id of entityIds) {
      const e = entities[id];
      if (e?.loot) m[id] = e.loot;
    }
    return m;
  }, [entities, entityIds]);

  const submitRoomSlug = useCallback(
    async (m, slug) => {
      if (!SLUG_OK(slug)) return;
      const zr = zonesRef.current;
      switch (m.mode) {
        case "add": {
          const base = {
            id: `${zoneId}:${slug}`,
            zone: zoneId,
            type: defaultRoomType || "chamber",
            depth: 1,
            description: { base: "" },
            exits: {},
            features: [],
            entity_spawns: [],
            hazards: [],
            tags: [],
          };
          await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), base);
          dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: base });
          {
            const prev = positionsDocRef.current;
            const next = { ...prev, floors: { ...(prev.floors || {}), [slug]: currentFloor } };
            setPositionsDoc(next);
            await fs.writeText(positionsPath, serializePositionsDoc(next));
          }
          break;
        }
        case "placeholder": {
          const base = {
            id: `${zoneId}:${slug}`,
            zone: zoneId,
            name: "?",
            type: "chamber",
            depth: 1,
            description: { base: "" },
            exits: {},
            features: [],
            entity_spawns: [],
            hazards: [],
            tags: [],
          };
          await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), base);
          dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: base });
          {
            const prev = positionsDocRef.current;
            const next = { ...prev, floors: { ...(prev.floors || {}), [slug]: currentFloor } };
            setPositionsDoc(next);
            await fs.writeText(positionsPath, serializePositionsDoc(next));
          }
          break;
        }
        case "addHere": {
          const p = m.flowPos;
          const base = {
            id: `${zoneId}:${slug}`,
            zone: zoneId,
            type: defaultRoomType || "chamber",
            depth: 1,
            description: { base: "New room" },
            exits: {},
            features: [],
            entity_spawns: [],
            hazards: [],
            tags: [],
          };
          await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), base);
          dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: base });
          {
            const prev = positionsDocRef.current;
            const next = {
              ...prev,
              positions: {
                ...prev.positions,
                [slug]: { x: p.x, y: p.y, width: DEFAULT_ROOM_NODE_W, height: DEFAULT_ROOM_NODE_H },
              },
              floors: { ...(prev.floors || {}), [slug]: currentFloor },
            };
            setPositionsDoc(next);
            await fs.writeText(positionsPath, serializePositionsDoc(next));
          }
          break;
        }
        case "duplicate": {
          const from = m.fromSlug;
          const src = zr[zoneId]?.rooms?.[from] || {};
          const copy = buildDuplicateRoomYaml(src, zoneId, slug, from);
          await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), copy);
          dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: copy });
          {
            // Inherit source room's floor so duplicate lands on the same level
            const prev = positionsDocRef.current;
            const fromFloor = (prev.floors || {})[from] ?? currentFloor;
            const next = { ...prev, floors: { ...(prev.floors || {}), [slug]: fromFloor } };
            setPositionsDoc(next);
            await fs.writeText(positionsPath, serializePositionsDoc(next));
          }
          break;
        }
        default:
          break;
      }
    },
    [zoneId, worldRoot, dispatch, defaultRoomType, currentFloor, positionsPath]
  );

  const onRoomSlugModalConfirm = useCallback(
    (slug) => {
      const m = roomSlugModal;
      setRoomSlugModal(null);
      if (!m) return;
      submitRoomSlug(m, slug).catch(() => {});
    },
    [roomSlugModal, submitRoomSlug]
  );

  useEffect(() => {
    undoStackRef.current = [];
  }, [zoneId]);

  const applyUndo = useCallback(async () => {
    const stack = undoStackRef.current;
    if (!stack.length) {
      setStatusMsg("Nothing to undo");
      return;
    }
    const entry = stack.pop();
    if (entry.type === "duplicate" || entry.type === "stampPlace") {
      for (const slug of entry.createdSlugs) {
        try {
          await fs.deleteFile(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`));
        } catch {
          /* missing file */
        }
        dispatch({ type: "DELETE_ZONE_ROOM", zoneId, slug });
      }
      const restored = clonePositionsDoc(entry.prevPositionsDoc);
      setPositionsDoc(restored);
      await fs.writeText(positionsPath, serializePositionsDoc(restored));
      setStatusMsg(
        entry.type === "stampPlace"
          ? `Undid stamp placement (${entry.createdSlugs.length} room(s))`
          : `Undid duplicate (${entry.createdSlugs.length} room(s))`
      );
    } else if (entry.type === "layout") {
      const restored = clonePositionsDoc(entry.prevPositionsDoc);
      setPositionsDoc(restored);
      await fs.writeText(positionsPath, serializePositionsDoc(restored));
      setStatusMsg("Undid layout / rotate / map border");
    } else if (entry.type === "clearConnections") {
      for (const [slug, data] of Object.entries(entry.prevRooms || {})) {
        dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data });
        await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), data);
      }
      const restored = clonePositionsDoc(entry.prevPositionsDoc);
      setPositionsDoc(restored);
      await fs.writeText(positionsPath, serializePositionsDoc(restored));
      setStatusMsg("Undid clear all connections");
    }
  }, [zoneId, worldRoot, dispatch, positionsPath]);

  const linkStairs = useCallback(
    async (fromSlug, fromDir, toSlug) => {
      const zr = zonesRef.current;
      const fromRoom = { ...(zr[zoneId]?.rooms?.[fromSlug] || {}) };
      fromRoom.exits = { ...(fromRoom.exits || {}) };
      fromRoom.exits[fromDir] = { destination: `${zoneId}:${toSlug}`, description: "" };
      dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: fromSlug, data: fromRoom });
      await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${fromSlug}.yaml`), fromRoom);
      const toDir = oppositeDir(fromDir);
      const toRoom = { ...(zr[zoneId]?.rooms?.[toSlug] || {}) };
      toRoom.exits = { ...(toRoom.exits || {}) };
      toRoom.exits[toDir] = { destination: `${zoneId}:${fromSlug}`, description: "" };
      dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: toSlug, data: toRoom });
      await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${toSlug}.yaml`), toRoom);
      setStatusMsg(`Linked ${fromSlug} ↕ ${toSlug}`);
    },
    [zoneId, worldRoot, dispatch]
  );

  const duplicateSelectedRooms = useCallback(async () => {
    if (duplicateBusyRef.current) {
      setStatusMsg("Already duplicating…");
      return;
    }

    const flow = rfRef.current;
    const selectedNodes = flow.getNodes().filter((n) => n.type === "room" && n.selected && !n.data?.locked);
    if (!selectedNodes.length) {
      setStatusMsg("Select unlocked rooms to duplicate");
      return;
    }

    const roomsLive = zonesRef.current[zoneId]?.rooms || {};
    const selSnapshot = selectedNodes.map((n) => {
      const { position, style } = snapshotRoomNodeLayout(flow, n);
      return {
        slug: n.data?.slug,
        roomId: n.id,
        position,
        style,
      };
    });

    const sourceBySlug = new Map();
    const missingSlugs = [];
    for (const row of selSnapshot) {
      if (!row.slug) {
        missingSlugs.push("(unnamed node)");
        continue;
      }
      const raw = roomsLive[row.slug];
      if (!raw) {
        missingSlugs.push(row.slug);
        continue;
      }
      if (!sourceBySlug.has(row.slug)) {
        sourceBySlug.set(row.slug, JSON.parse(JSON.stringify(raw)));
      }
    }

    if (!sourceBySlug.size) {
      setStatusMsg(
        missingSlugs.length ? `No room YAML loaded for: ${missingSlugs.slice(0, 6).join(", ")}${missingSlugs.length > 6 ? "…" : ""}` : "Nothing to duplicate"
      );
      return;
    }

    duplicateBusyRef.current = true;
    const snapshotBefore = clonePositionsDoc(positionsDoc);
    const usedSlugs = new Set(Object.keys(roomsLive));
    const pairs = [];

    const allocSlug = (base) => {
      let cand = `${base}_copy`;
      if (!usedSlugs.has(cand)) {
        usedSlugs.add(cand);
        return cand;
      }
      let i = 2;
      while (usedSlugs.has(`${base}_copy_${i}`)) i += 1;
      cand = `${base}_copy_${i}`;
      usedSlugs.add(cand);
      return cand;
    };

    try {
      for (const row of selSnapshot) {
        if (!row.slug || !sourceBySlug.has(row.slug)) continue;

        const newSlug = allocSlug(row.slug);
        const copy = buildDuplicateRoomYaml(sourceBySlug.get(row.slug), zoneId, newSlug, row.slug);
        await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${newSlug}.yaml`), copy);
        pairs.push({ fromSlug: row.slug, newSlug, snap: row, copy });
      }

      if (!pairs.length) {
        setStatusMsg("Nothing duplicated");
        return;
      }

      const newIds = pairs.map((p) => `${zoneId}:${p.newSlug}`);

      unstable_batchedUpdates(() => {
        for (const p of pairs) {
          dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: p.newSlug, data: p.copy });
        }
        setPositionsDoc((prev) => {
          const positions = { ...prev.positions };
          for (const { fromSlug, newSlug, snap } of pairs) {
            const preserved = { ...(positions[fromSlug] || {}) };
            delete preserved.locked;
            delete preserved.x;
            delete preserved.y;
            delete preserved.width;
            delete preserved.height;
            const box = readNodeBox(snap.style, DEFAULT_ROOM_NODE_W, DEFAULT_ROOM_NODE_H);
            positions[newSlug] = {
              ...preserved,
              x: snap.position.x,
              y: snap.position.y,
              width: box.width,
              height: box.height,
            };
          }
          const next = { ...prev, positions };
          fs.writeText(positionsPath, serializePositionsDoc(next)).catch(() => {});
          return next;
        });
      });

      undoStackRef.current.push({
        type: "duplicate",
        prevPositionsDoc: snapshotBefore,
        createdSlugs: pairs.map((p) => p.newSlug),
      });
      if (undoStackRef.current.length > UNDO_LIMIT) undoStackRef.current.shift();

      const notDuped = selectedNodes.length - pairs.length;
      const warn =
        notDuped > 0
          ? ` — ${notDuped} not duplicated (no slug or room not loaded).`
          : "";
      setStatusMsg(`Duplicated ${pairs.length} room(s); copies match selection layout, new names, no exits.${warn}`);

      const selectIds = new Set(newIds);
      window.setTimeout(() => {
        setNodesRef.current((nds) =>
          nds.map((n) => ({
            ...n,
            selected: n.type === "room" && selectIds.has(n.id),
          }))
        );
      }, 48);
    } catch {
      setStatusMsg("Duplicate failed");
    } finally {
      duplicateBusyRef.current = false;
    }
  }, [zoneId, worldRoot, dispatch, positionsPath, positionsDoc]);

  const beginSaveStamp = useCallback(() => {
    const flow = rfRef.current;
    const selectedNodes = flow.getNodes().filter((n) => n.type === "room" && n.selected && !n.data?.locked);
    if (!selectedNodes.length) {
      setStatusMsg("Select unlocked rooms to save as a stamp");
      return;
    }

    const roomsLive = zonesRef.current[zoneId]?.rooms || {};
    const selSnapshot = selectedNodes.map((n) => {
      const { position, style } = snapshotRoomNodeLayout(flow, n);
      return {
        slug: n.data?.slug,
        position,
        style,
      };
    });

    const sourceBySlug = {};
    const missingSlugs = [];
    const seen = new Set();
    const snapshots = [];
    for (const row of selSnapshot) {
      if (!row.slug) {
        missingSlugs.push("(unnamed node)");
        continue;
      }
      const raw = roomsLive[row.slug];
      if (!raw) {
        missingSlugs.push(row.slug);
        continue;
      }
      if (!seen.has(row.slug)) {
        seen.add(row.slug);
        sourceBySlug[row.slug] = JSON.parse(JSON.stringify(raw));
        snapshots.push({ slug: row.slug, position: row.position, style: row.style });
      }
    }

    if (!Object.keys(sourceBySlug).length) {
      setStatusMsg(
        missingSlugs.length
          ? `No room YAML loaded for: ${missingSlugs.slice(0, 6).join(", ")}${missingSlugs.length > 6 ? "…" : ""}`
          : "Nothing to save as stamp"
      );
      return;
    }

    const first = snapshots[0]?.slug || "stamp";
    setSaveStampDraft({
      snapshots,
      roomsBySourceSlug: sourceBySlug,
      defaultDisplayName: `${String(first).replace(/_/g, " ")} stamp`,
    });
    setSaveStampOpen(true);
  }, [zoneId]);

  const onSaveStampConfirm = useCallback(
    async ({ displayName, stampSlug, preserve }) => {
      const draft = saveStampDraftRef.current;
      setSaveStampOpen(false);
      setSaveStampDraft(null);
      saveStampDraftRef.current = null;
      if (!draft || !worldRoot) {
        if (!worldRoot) setStatusMsg("No content folder open — cannot save stamp.");
        else if (!draft) setStatusMsg("Stamp draft missing — try Save stamp… again.");
        return;
      }
      const folder = stampFolderPath(worldRoot, stampSlug);
      try {
        if (await fs.pathExists(folder)) {
          if (!window.confirm(`Replace existing stamp “${stampSlug}”?`)) return;
          await fs.removeDirAll(folder);
        }
        await saveStampBundle(
          worldRoot,
          stampSlug,
          displayName,
          zoneId,
          preserve,
          draft.roomsBySourceSlug,
          positionsDoc.positions || {},
          draft.snapshots,
          DEFAULT_ROOM_NODE_W,
          DEFAULT_ROOM_NODE_H
        );
        setStatusMsg(`Saved stamp “${displayName}” (${stampSlug})`);
      } catch {
        setStatusMsg("Save stamp failed");
      }
    },
    [worldRoot, zoneId, positionsDoc]
  );

  const placeStampAtFlow = useCallback(
    async (flowX, flowY) => {
      const stampSlug = pendingStampPlace?.stampSlug;
      if (!stampSlug || !worldRoot || !zoneId) return;
      if (stampPlaceBusyRef.current) return;
      stampPlaceBusyRef.current = true;
      try {
        const bundle = await loadStampBundle(worldRoot, stampSlug);
        if (!bundle) {
          setStatusMsg("Stamp not found");
          setPendingStampPlace(null);
          return;
        }
        const { meta, roomsMap: sm, positionsDoc: spd } = bundle;
        const logicalKeys =
          Array.isArray(meta.logical_keys) && meta.logical_keys.length ? meta.logical_keys : Object.keys(sm).sort();
        const roomsLive = zonesRef.current[zoneId]?.rooms || {};
        const usedSlugs = new Set(Object.keys(roomsLive));
        const stampKey = meta.slug || stampSlug;
        const logicalToNew = buildPlacementSlugMap(logicalKeys, sm, stampKey, usedSlugs);
        const { outRooms, outPositions, newSlugs } = expandStampForPlacement(zoneId, sm, spd, logicalToNew, flowX, flowY);

        if (!newSlugs.length) {
          setStatusMsg("Stamp has no rooms to place");
          setPendingStampPlace(null);
          return;
        }

        const snapshotBefore = clonePositionsDoc(positionsDocRef.current);

        for (const s of newSlugs) {
          await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${s}.yaml`), outRooms[s]);
        }

        /* One React commit: avoid intermediate rebuilds that grid-layout new rooms and freeze wrong coords via live-node override. */
        unstable_batchedUpdates(() => {
          for (const s of newSlugs) {
            dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: s, data: outRooms[s] });
          }
          setPositionsDoc((prev) => {
            const positions = { ...prev.positions, ...outPositions };
            const next = { ...prev, positions };
            fs.writeText(positionsPath, serializePositionsDoc(next)).catch(() => {});
            return next;
          });
        });

        undoStackRef.current.push({
          type: "stampPlace",
          prevPositionsDoc: snapshotBefore,
          createdSlugs: newSlugs,
        });
        if (undoStackRef.current.length > UNDO_LIMIT) undoStackRef.current.shift();

        const newIds = newSlugs.map((s) => `${zoneId}:${s}`);
        const selectIds = new Set(newIds);
        window.setTimeout(() => {
          setNodesRef.current((nds) =>
            nds.map((n) => ({
              ...n,
              selected: n.type === "room" && selectIds.has(n.id),
            }))
          );
        }, 48);

        setPendingStampPlace(null);
        setStatusMsg(`Placed stamp (${newSlugs.length} room(s)); Ctrl/⌘+Z to undo`);
      } catch {
        setStatusMsg("Place stamp failed");
      } finally {
        stampPlaceBusyRef.current = false;
      }
    },
    [pendingStampPlace, worldRoot, zoneId, dispatch, positionsPath]
  );

  useEffect(() => {
    const typingTarget = (el) => {
      if (!el || typeof el !== "object") return false;
      const tag = String(el.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || tag === "option") return true;
      if (el.isContentEditable) return true;
      return false;
    };

    const onKeyDown = (e) => {
      if (e.repeat) return;
      if (e.key === "Escape") {
        if (saveStampOpen) {
          e.preventDefault();
          setSaveStampOpen(false);
          setSaveStampDraft(null);
          return;
        }
        if (stampLibraryOpen) {
          e.preventDefault();
          setStampLibraryOpen(false);
          return;
        }
        if (pendingStairLink) {
          e.preventDefault();
          setPendingStairLink(null);
          setStatusMsg("Stair link cancelled");
          return;
        }
        if (pendingStampPlace) {
          e.preventDefault();
          setPendingStampPlace(null);
          setStatusMsg("Stamp placement cancelled");
          return;
        }
      }
      if (!e.ctrlKey && !e.metaKey) return;
      if (typingTarget(e.target)) return;
      if (roomSlugModal || groupModalOpen || saveStampOpen || stampLibraryOpen) return;

      const k = e.key?.length === 1 ? e.key.toLowerCase() : e.key;
      if (k === "d") {
        e.preventDefault();
        duplicateSelectedRooms().catch(() => setStatusMsg("Duplicate failed"));
      } else if (k === "z" && !e.shiftKey) {
        e.preventDefault();
        applyUndo().catch(() => setStatusMsg("Undo failed"));
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    roomSlugModal,
    groupModalOpen,
    saveStampOpen,
    stampLibraryOpen,
    pendingStairLink,
    pendingStampPlace,
    duplicateSelectedRooms,
    applyUndo,
  ]);

  /** Remove exit on edge.source and any exit on edge.target that points back (mutual in-zone link). */
  const removeLinkedExitPair = useCallback(
    async (edge) => {
      const parts = edge.id.split("|");
      if (parts.length < 3) return;
      const direction = parts[1];
      const sourceId = edge.source;
      const targetId = edge.target;
      const nodesLive = rfRef.current.getNodes().filter((n) => n.type === "room");
      const knownIds = new Set(nodesLive.map((n) => n.id));
      const srcSlug = nodesLive.find((n) => n.id === sourceId)?.data?.slug;
      const tgtSlug = nodesLive.find((n) => n.id === targetId)?.data?.slug;
      if (!srcSlug) return;
      const zr = zonesRef.current[zoneId]?.rooms || {};

      const curS = JSON.parse(JSON.stringify(zr[srcSlug] || {}));
      curS.exits = { ...(curS.exits || {}) };
      delete curS.exits[direction];
      dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: srcSlug, data: curS });
      await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${srcSlug}.yaml`), curS);

      if (!tgtSlug) return;
      const curT = JSON.parse(JSON.stringify(zr[tgtSlug] || {}));
      curT.exits = { ...(curT.exits || {}) };
      let changed = false;
      for (const dir of Object.keys({ ...curT.exits })) {
        const ex = curT.exits[dir];
        const tid = resolveExitDestination(zoneId, String(ex?.destination || ""), knownIds);
        if (tid === sourceId) {
          delete curT.exits[dir];
          changed = true;
        }
      }
      if (changed) {
        dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: tgtSlug, data: curT });
        await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${tgtSlug}.yaml`), curT);
      }
    },
    [zoneId, worldRoot, dispatch]
  );

  const rebuildGraph = useCallback(() => {
    const doc = positionsDoc;
    const muted = mutedEdgeSetFromDoc(doc);
    const { nodes: rn, edges: re, externalExits } = buildZoneFlow(zoneId, roomsMap, doc, {
      mutedEdgeSet: muted,
      colors: COLORS,
    });
    const selectedIds = new Set();
    for (const n of rf.getNodes()) {
      if (n.selected) selectedIds.add(n.id);
    }
    const liveByRoomId = new Map();
    for (const n of rf.getNodes()) {
      if (n.type === "room" && n.id) {
        liveByRoomId.set(n.id, n);
      }
    }
    rn.forEach((n) => {
      const slug = n.data?.slug;
      if (!slug) return;
      if (selectedIds.has(n.id)) n.selected = true;
      const docP = doc.positions?.[slug];
      const locked = Boolean(docP?.locked);
      const live = liveByRoomId.get(n.id);
      if (!locked && live) {
        n.position = { x: live.position.x, y: live.position.y };
        const built = n.style || {};
        const lv = live.style || {};
        if (lv.width != null || lv.height != null) {
          n.style = {
            ...built,
            width: lv.width ?? built.width,
            height: lv.height ?? built.height,
          };
        }
      }
    });
    const gmap = new Map((groups || []).map((g) => [g.id, g]));
    const zr = zonesRef.current;
    rn.forEach((n) => {
      const gid = n.data.group;
      if (gid && gmap.has(gid)) {
        const g = gmap.get(gid);
        n.data.groupColor = g.color;
        n.data.groupName = g.name;
      }
      n.data.zoneId = zoneId;
      n.data.showRoomId = showYamlIds;
      n.data.toolbar = {
        onQuickExit: (dir) => {
          const slug = n.data.slug;
          const cur = { ...(zr[zoneId]?.rooms?.[slug] || {}) };
          cur.exits = { ...(cur.exits || {}) };
          if (cur.exits[dir]) {
            const dest = String(cur.exits[dir]?.destination || "").trim();
            if (dest && !window.confirm(`Remove ${dir} exit from ${slug}?\nThis will clear its link to "${dest}".`)) return;
            delete cur.exits[dir];
            dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: cur });
            fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), cur).catch(() => {});
            setSelectedSlug(slug);
            setPanelDraft(cur);
            setStatusMsg(`Removed ${dir} exit`);
            return;
          }
          cur.exits[dir] = { destination: "", description: "" };
          dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: cur });
          fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), cur).catch(() => {});
          setSelectedSlug(slug);
          setPanelDraft(cur);
          setStatusMsg("Set destination in Exits tab");
        },
        onToggleStair: (dir) => {
          const slug = n.data.slug;
          const cur = { ...(zr[zoneId]?.rooms?.[slug] || {}) };
          cur.exits = { ...(cur.exits || {}) };
          if (cur.exits[dir]) {
            const dest = String(cur.exits[dir]?.destination || "").trim();
            if (dest && !window.confirm(`Remove ${dir} exit from ${slug}?\nThis will clear its link to "${dest}".`)) return;
            delete cur.exits[dir];
            setStatusMsg(`Removed ${dir} exit`);
          } else {
            cur.exits[dir] = { destination: "", description: "" };
            setStatusMsg(`Added ${dir} exit — set destination in Exits tab`);
          }
          dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: cur });
          fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), cur).catch(() => {});
          setSelectedSlug(slug);
          setPanelDraft(cur);
        },
        onDuplicate: () => {
          setRoomSlugModal({
            mode: "duplicate",
            defaultSlug: `${n.data.slug}_copy`,
            fromSlug: n.data.slug,
          });
        },
        onAiDescribe: async () => {
          if (!nexusUrl) return;
          const headers = { "Content-Type": "application/json" };
          if (nexusToken) headers.Authorization = `Bearer ${nexusToken}`;
          const res = await fetch(`${nexusUrl.replace(/\/$/, "")}/forge/generate`, {
            method: "POST",
            headers,
            body: JSON.stringify({
              seed: `Room ${n.data.slug}`,
              room_type: n.data.roomType || "chamber",
              depth: n.data.depth || 1,
            }),
          });
          if (!res.ok) return;
          const data = await res.json();
          const parsed = data.data || yaml.load(data.yaml || "");
          const slug = n.data.slug;
          const cur = { ...(zr[zoneId]?.rooms?.[slug] || {}) };
          cur.description = { ...(cur.description || {}), base: parsed?.description?.base || "" };
          dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: cur });
          await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), cur);
        },
        onDelete: async () => {
          if (!window.confirm(`Delete room ${n.data.slug}?`)) return;
          await fs.deleteFile(joinPaths(worldRoot, "zones", zoneId, "rooms", `${n.data.slug}.yaml`));
          dispatch({ type: "DELETE_ZONE_ROOM", zoneId, slug: n.data.slug });
        },
      };
      const locked = Boolean(doc.positions?.[n.data.slug]?.locked);
      n.data.locked = locked;
      n.draggable = !locked;
    });
    re.forEach((e) => {
      e.markerEnd = { type: MarkerType.ArrowClosed, color: COLORS.borderActive, width: 18, height: 18 };
      e.data = {
        ...e.data,
        edgeToolbar: {
          onAddReturn: async () => {
            const parts = e.id.split("|");
            const direction = parts[1];
            const sourceId = e.source;
            const targetId = e.target;
            const srcSlug = rn.find((x) => x.id === sourceId)?.data?.slug;
            const tgtSlug = rn.find((x) => x.id === targetId)?.data?.slug;
            if (!srcSlug || !tgtSlug) return;
            const rev = oppositeDir(direction);
            const tRoom = { ...(zr[zoneId]?.rooms?.[tgtSlug] || {}) };
            tRoom.exits = { ...(tRoom.exits || {}) };
            if (tRoom.exits[rev]) return;
            tRoom.exits[rev] = { destination: `${zoneId}:${srcSlug}`, description: "" };
            dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: tgtSlug, data: tRoom });
            await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${tgtSlug}.yaml`), tRoom);
          },
          onRemove: async () => {
            await removeLinkedExitPair(e);
          },
          onSetMapLabel: async (label) => {
            const parts = e.id.split("|");
            const direction = parts[1];
            const sourceId = e.source;
            const srcSlug = rn.find((x) => x.id === sourceId)?.data?.slug;
            if (!srcSlug) return;
            const cur = { ...(zr[zoneId]?.rooms?.[srcSlug] || {}) };
            cur.exits = { ...(cur.exits || {}) };
            const ex = { ...(cur.exits[direction] || {}) };
            const trimmed = String(label || "").trim();
            const dlow = String(direction || "").toLowerCase();
            if (!trimmed || trimmed.toLowerCase() === dlow) delete ex.map_label;
            else ex.map_label = trimmed;
            cur.exits[direction] = ex;
            dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: srcSlug, data: cur });
            await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${srcSlug}.yaml`), cur);
          },
        },
      };
    });
    const notes = (doc.notes || []).map((note) => ({
      id: note.id,
      type: "note",
      selected: selectedIds.has(note.id),
      position: { x: note.x || 0, y: note.y || 0 },
      data: {
        text: note.text || "",
        color: note.color || "yellow",
        onChangeText: (nid, text) => {
          setPositionsDoc((prev) => {
            const nnotes = (prev.notes || []).map((x) => (x.id === nid ? { ...x, text } : x));
            return { ...prev, notes: nnotes };
          });
        },
      },
    }));
    const reFlow = dedupeMutualBidirectionalEdges(re);

    // Z-level floor filtering
    const floorsMap = positionsDoc.floors || {};
    const currentFloorSlugs = new Set(
      Object.keys(roomsMap).filter((s) => (floorsMap[s] ?? 0) === currentFloor)
    );
    // Ghost nodes: rooms on the floor directly below with an "up" exit, and rooms on the
    // floor directly above with a "down" exit — rendered at their canvas position so you
    // can see where stairs land and build/connect accordingly.
    const ghostData = {};
    const floorBelow = currentFloor - 1;
    const floorAbove = currentFloor + 1;
    for (const [slug, room] of Object.entries(roomsMap)) {
      const roomFloor = floorsMap[slug] ?? 0;
      if (roomFloor !== floorBelow && roomFloor !== floorAbove) continue;
      const exits = room.exits && typeof room.exits === "object" ? room.exits : {};
      if (roomFloor === floorBelow) {
        const upExit = Object.entries(exits).find(([k]) => k.toLowerCase() === "up")?.[1];
        if (upExit !== undefined) {
          const linked = Boolean(String(upExit?.destination || "").trim());
          ghostData[slug] = { ghostFloor: floorBelow, ghostDir: "up", ghostLinked: linked };
        }
      } else if (roomFloor === floorAbove) {
        const downExit = Object.entries(exits).find(([k]) => k.toLowerCase() === "down")?.[1];
        if (downExit !== undefined) {
          const linked = Boolean(String(downExit?.destination || "").trim());
          ghostData[slug] = { ghostFloor: floorAbove, ghostDir: "down", ghostLinked: linked };
        }
      }
    }
    // Also ghost explicit up/down destinations of current-floor rooms not already covered.
    for (const slug of currentFloorSlugs) {
      const room = roomsMap[slug] || {};
      const exits = room.exits && typeof room.exits === "object" ? room.exits : {};
      for (const [dir, ex] of Object.entries(exits)) {
        if (dir.toLowerCase() !== "up" && dir.toLowerCase() !== "down") continue;
        const dest = String(ex?.destination || "");
        if (!dest) continue;
        const tgtSlug = dest.includes(":")
          ? dest.startsWith(`${zoneId}:`) ? dest.slice(zoneId.length + 1) : null
          : dest;
        if (!tgtSlug || !roomsMap[tgtSlug] || ghostData[tgtSlug]) continue;
        const tgtFloor = floorsMap[tgtSlug] ?? 0;
        if (tgtFloor !== currentFloor) {
          ghostData[tgtSlug] = { ghostFloor: tgtFloor, ghostDir: dir.toLowerCase(), ghostLinked: true };
        }
      }
    }
    const visibleNodeIds = new Set();
    const filteredRn = rn.flatMap((n) => {
      const slug = n.data?.slug;
      if (!slug) return [n];
      if (currentFloorSlugs.has(slug)) { visibleNodeIds.add(n.id); return [n]; }
      if (ghostData[slug]) {
        visibleNodeIds.add(n.id);
        const gd = ghostData[slug];
        return [{
          ...n,
          draggable: false,
          selectable: false,
          data: {
            ...n.data,
            ghost: true,
            ghostFloor: gd.ghostFloor,
            ghostDir: gd.ghostDir,
            ghostLinked: gd.ghostLinked,
            toolbar: {
              onStartLink: () => setPendingStairLink({ slug, ghostFloor: gd.ghostFloor, ghostDir: gd.ghostDir }),
              onToggleExit: async () => {
                const dir = gd.ghostDir;
                const cur = { ...(zr[zoneId]?.rooms?.[slug] || {}) };
                cur.exits = { ...(cur.exits || {}) };
                if (cur.exits[dir]) {
                  const dest = String(cur.exits[dir]?.destination || "").trim();
                  if (dest && !window.confirm(`Remove ${dir} exit from "${slug}"?\nThis will clear its link to "${dest}".`)) return;
                  delete cur.exits[dir];
                } else {
                  cur.exits[dir] = { destination: "", description: "" };
                }
                dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: cur });
                await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), cur);
                setStatusMsg(`${cur.exits[dir] ? "Added" : "Removed"} ${dir} exit on ${slug}`);
              },
            },
          },
        }];
      }
      return [];
    });
    const filteredEdges = reFlow.filter((e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target));

    setNodes([...filteredRn, ...notes]);
    setEdges(filteredEdges);
    setIssues(
      runZoneValidation(rn, reFlow, externalExits, {
        zoneId,
        roomsMap,
        entityIds,
        itemIds,
        glyphIds,
        glyphs,
        allRoomIds,
        entityLoot: entityLootMap,
      })
    );
  }, [
    zoneId,
    roomsMap,
    positionsDoc,
    groups,
    showYamlIds,
    worldRoot,
    dispatch,
    zoneIds,
    entityIds,
    itemIds,
    glyphIds,
    glyphs,
    allRoomIds,
    entityLootMap,
    nexusUrl,
    nexusToken,
    rf,
    setNodes,
    setEdges,
    removeLinkedExitPair,
    COLORS,
    currentFloor,
    linkStairs,
  ]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!zoneId || !worldRoot) return;
      try {
        const raw = (await fs.pathExists(positionsPath)) ? JSON.parse(await fs.readText(positionsPath)) : {};
        if (cancelled) return;
        setPositionsDoc(parsePositionsDoc(raw));
      } catch {
        if (!cancelled) setPositionsDoc(parsePositionsDoc(null));
      }
      try {
        if (await fs.pathExists(groupsPath)) {
          const g = await fs.readYaml(groupsPath);
          if (cancelled) return;
          setGroups(Array.isArray(g) ? g : g?.groups || []);
        } else setGroups([]);
      } catch {
        setGroups([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [zoneId, worldRoot, positionsPath, groupsPath]);

  useEffect(() => {
    rebuildGraph();
  }, [rebuildGraph]);

  const patchRoomLayout = useCallback(
    (slug, patch) => {
      setPositionsDoc((prev) => {
        const prevPos = { ...(prev.positions?.[slug] || {}) };
        for (const [k, v] of Object.entries(patch)) {
          if (v === undefined || v === null || v === "") delete prevPos[k];
          else prevPos[k] = v;
        }
        const nextDoc = { ...prev, positions: { ...prev.positions, [slug]: prevPos } };
        fs.writeText(positionsPath, serializePositionsDoc(nextDoc)).catch(() => {});
        return nextDoc;
      });
    },
    [positionsPath]
  );

  const applyLayoutBorderColorToSelection = useCallback(
    (hex) => {
      const sel = rfRef.current.getNodes().filter((n) => n.type === "room" && n.selected && !n.data?.locked);
      const slugs = [...new Set(sel.map((n) => n.data?.slug).filter(Boolean))];
      if (!slugs.length) {
        setStatusMsg("Select unlocked rooms to change map border color");
        return;
      }
      const raw = hex != null ? String(hex).trim() : "";
      const clearIt = raw === "";

      undoStackRef.current.push({
        type: "layout",
        prevPositionsDoc: clonePositionsDoc(positionsDocRef.current),
      });
      if (undoStackRef.current.length > UNDO_LIMIT) undoStackRef.current.shift();

      setPositionsDoc((prev) => {
        const positions = { ...prev.positions };
        for (const slug of slugs) {
          const prevPos = { ...(positions[slug] || {}) };
          if (clearIt) delete prevPos.border_color;
          else prevPos.border_color = raw;
          positions[slug] = prevPos;
        }
        const nextDoc = { ...prev, positions };
        fs.writeText(positionsPath, serializePositionsDoc(nextDoc)).catch(() => {});
        return nextDoc;
      });
      if (slugs.length > 1) setStatusMsg(`Map border → ${slugs.length} rooms`);
      else setStatusMsg(clearIt ? "Map border reset" : "Map border updated");
    },
    [positionsPath]
  );

  const applyRoomLayoutPatches = useCallback(
    (patches) => {
      if (!patches?.length) return;
      undoStackRef.current.push({
        type: "layout",
        prevPositionsDoc: clonePositionsDoc(positionsDocRef.current),
      });
      if (undoStackRef.current.length > UNDO_LIMIT) undoStackRef.current.shift();
      setNodes((nds) =>
        nds.map((n) => {
          const p = patches.find((x) => x.id === n.id);
          if (!p) return n;
          return { ...n, position: { ...n.position, x: p.position.x, y: p.position.y } };
        })
      );
      for (const p of patches) {
        if (p.slug) patchRoomLayout(p.slug, { x: p.position.x, y: p.position.y });
      }
      setStatusMsg("Rooms arranged");
    },
    [setNodes, patchRoomLayout]
  );

  const runArrange = useCallback(
    (fn, opts = {}) => {
      const min = opts.minRooms ?? 2;
      const sel = rfRef.current.getNodes().filter((n) => n.selected && n.type === "room" && !n.data?.locked);
      if (sel.length < min) {
        if (opts.tooFewMsg) setStatusMsg(opts.tooFewMsg);
        return;
      }
      const patches = fn(sel);
      if (!patches.length) return;
      applyRoomLayoutPatches(patches);
    },
    [applyRoomLayoutPatches]
  );

  const rotateSelectedRooms = useCallback(
    (deltaDeg) => {
      const sel = rfRef.current
        .getNodes()
        .filter((n) => n.type === "room" && n.selected && !n.data?.locked);
      if (!sel.length) {
        setStatusMsg("Select unlocked rooms to rotate");
        return;
      }
      undoStackRef.current.push({
        type: "layout",
        prevPositionsDoc: clonePositionsDoc(positionsDocRef.current),
      });
      if (undoStackRef.current.length > UNDO_LIMIT) undoStackRef.current.shift();

      const boxes = sel.map((n) => {
        const r = getRoomRectFlow(n, DEFAULT_ROOM_NODE_W, DEFAULT_ROOM_NODE_H);
        return { n, ...r, cx: r.x + r.w / 2, cy: r.y + r.h / 2 };
      });
      const minX = Math.min(...boxes.map((b) => b.x));
      const minY = Math.min(...boxes.map((b) => b.y));
      const maxX = Math.max(...boxes.map((b) => b.x + b.w));
      const maxY = Math.max(...boxes.map((b) => b.y + b.h));
      const pivotX = (minX + maxX) / 2;
      const pivotY = (minY + maxY) / 2;

      const rad = (deltaDeg * Math.PI) / 180;
      const cos = Math.cos(rad);
      const sin = Math.sin(rad);

      /** @type {{ id: string, slug: string, x: number, y: number }[]} */
      const geo = [];
      for (const b of boxes) {
        const slug = b.n.data?.slug;
        if (!slug) continue;
        const dx = b.cx - pivotX;
        const dy = b.cy - pivotY;
        const ncx = dx * cos - dy * sin + pivotX;
        const ncy = dx * sin + dy * cos + pivotY;
        geo.push({ id: b.n.id, slug, x: ncx - b.w / 2, y: ncy - b.h / 2 });
      }

      setNodes((nds) =>
        nds.map((node) => {
          const g = geo.find((x) => x.id === node.id);
          if (!g) return node;
          return { ...node, position: { x: g.x, y: g.y } };
        })
      );

      setPositionsDoc((prev) => {
        const positions = { ...prev.positions };
        for (const g of geo) {
          const prevPos = { ...(positions[g.slug] || {}) };
          const cur = Number(prevPos.rotation);
          const base = Number.isFinite(cur) ? cur : 0;
          const next = normalizeRotationDeg(base + deltaDeg);
          prevPos.x = g.x;
          prevPos.y = g.y;
          if (next === 0) delete prevPos.rotation;
          else prevPos.rotation = next;
          positions[g.slug] = prevPos;
        }
        const nextDoc = { ...prev, positions };
        fs.writeText(positionsPath, serializePositionsDoc(nextDoc)).catch(() => {});
        return nextDoc;
      });

      const n = geo.length;
      setStatusMsg(n > 1 ? `Rotated ${n} rooms as a group` : `Rotated 1 room`);
    },
    [positionsPath, setNodes]
  );

  const resetRotationSelected = useCallback(() => {
    const sel = rfRef.current
      .getNodes()
      .filter((n) => n.type === "room" && n.selected && !n.data?.locked);
    if (!sel.length) {
      setStatusMsg("Select unlocked rooms to reset rotation");
      return;
    }
    undoStackRef.current.push({
      type: "layout",
      prevPositionsDoc: clonePositionsDoc(positionsDocRef.current),
    });
    if (undoStackRef.current.length > UNDO_LIMIT) undoStackRef.current.shift();

    setPositionsDoc((prev) => {
      const positions = { ...prev.positions };
      for (const n of sel) {
        const slug = n.data?.slug;
        if (!slug) continue;
        const prevPos = { ...(positions[slug] || {}) };
        delete prevPos.rotation;
        positions[slug] = prevPos;
      }
      const nextDoc = { ...prev, positions };
      fs.writeText(positionsPath, serializePositionsDoc(nextDoc)).catch(() => {});
      return nextDoc;
    });
    setStatusMsg("Rotation reset");
  }, [positionsPath]);

  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;

    const isChromeUi = (el) =>
      Boolean(
        el?.closest?.(".react-flow__minimap") ||
          el?.closest?.(".react-flow__controls") ||
          el?.closest?.(".react-flow__panel")
      );

    const onPointerDownCapture = (e) => {
      if (e.pointerType === "touch") return;

      const rightMarquee = e.button === 2;
      if (!rightMarquee) return;

      const viewport = root.querySelector(".react-flow__viewport");
      if (!viewport || !viewport.contains(e.target) || isChromeUi(e.target)) return;

      const startX = e.clientX;
      const startY = e.clientY;
      let curX = startX;
      let curY = startY;
      const additive = e.ctrlKey || e.metaKey;

      let pointerCaptureHeld = false;
      try {
        viewport.setPointerCapture(e.pointerId);
        pointerCaptureHeld = true;
      } catch {
        /* WebView may omit setPointerCapture */
      }

      const paint = () => {
        const rr = root.getBoundingClientRect();
        setMarqueeScreen({
          left: Math.min(startX, curX) - rr.left,
          top: Math.min(startY, curY) - rr.top,
          width: Math.abs(curX - startX),
          height: Math.abs(curY - startY),
        });
      };
      paint();

      const onContextMenuWhileDrag = (ev) => {
        if (Math.abs(curX - startX) > 2 || Math.abs(curY - startY) > 2) {
          ev.preventDefault();
          ev.stopPropagation();
        }
      };
      window.addEventListener("contextmenu", onContextMenuWhileDrag, true);

      const onMove = (ev) => {
        curX = ev.clientX;
        curY = ev.clientY;
        paint();
      };

      const finish = (ev) => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", finish);
        window.removeEventListener("pointercancel", finish);
        window.removeEventListener("contextmenu", onContextMenuWhileDrag, true);

        if (pointerCaptureHeld) {
          try {
            viewport.releasePointerCapture(ev.pointerId);
          } catch {
            /* ignore */
          }
        }

        const endX = ev.clientX;
        const endY = ev.clientY;
        setMarqueeScreen(null);

        if (Math.abs(endX - startX) < 5 && Math.abs(endY - startY) < 5) return;

        if (rightMarquee) suppressPaneContextUntilRef.current = Date.now() + 400;

        const flow = rfRef.current;
        const xMin = Math.min(startX, endX);
        const yMin = Math.min(startY, endY);
        const xMax = Math.max(startX, endX);
        const yMax = Math.max(startY, endY);
        const p1 = flow.screenToFlowPosition({ x: xMin, y: yMin });
        const p2 = flow.screenToFlowPosition({ x: xMax, y: yMax });
        const rect = {
          x1: Math.min(p1.x, p2.x),
          y1: Math.min(p1.y, p2.y),
          x2: Math.max(p1.x, p2.x),
          y2: Math.max(p1.y, p2.y),
        };

        const hits = new Set();
        for (const n of flow.getNodes()) {
          if (n.type !== "room" || n.data?.locked) continue;
          if (flowRectIntersects(rect, getRoomRectFlow(n))) hits.add(n.id);
        }

        setNodesRef.current((nds) => {
          const prevSel = new Set(nds.filter((n) => n.type === "room" && n.selected && !n.data?.locked).map((n) => n.id));
          const nextSel = additive ? new Set([...prevSel, ...hits]) : hits;
          return nds.map((n) => ({
            ...n,
            selected: n.type === "room" && !n.data?.locked ? nextSel.has(n.id) : false,
          }));
        });
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", finish);
      window.addEventListener("pointercancel", finish);
    };

    root.addEventListener("pointerdown", onPointerDownCapture, true);
    return () => root.removeEventListener("pointerdown", onPointerDownCapture, true);
  }, [zoneId]);

  const saveLayout = useCallback(async () => {
    const nds = rf.getNodes();
    const pos = { ...(positionsDoc.positions || {}) };
    for (const n of nds) {
      if (n.type !== "room") continue;
      if (n.data?.ghost) continue; // ghost nodes belong to another floor — don't overwrite their saved position
      const slug = n.data?.slug;
      if (!slug) continue;
      const prev = pos[slug] || {};
      const box = readNodeBox(n.style, DEFAULT_ROOM_NODE_W, DEFAULT_ROOM_NODE_H);
      pos[slug] = { ...prev, x: n.position.x, y: n.position.y, width: box.width, height: box.height };
    }
    // Assign auto-positions for rooms that have no saved position yet (e.g. added via
    // keyboard shortcut on a different floor and never explicitly placed).
    const floorCounters = {};
    for (const slug of Object.keys(roomsMap)) {
      if (pos[slug]) continue;
      const floor = (positionsDoc.floors || {})[slug] ?? 0;
      const i = floorCounters[floor] ?? 0;
      floorCounters[floor] = i + 1;
      pos[slug] = { x: (i % 6) * 220, y: Math.floor(i / 6) * 130, width: DEFAULT_ROOM_NODE_W, height: DEFAULT_ROOM_NODE_H };
    }
    const notes = nds
      .filter((n) => n.type === "note")
      .map((n) => ({
        id: n.id,
        text: n.data?.text || "",
        color: n.data?.color || "yellow",
        x: n.position.x,
        y: n.position.y,
      }));
    const nextDoc = { ...positionsDoc, positions: pos, notes };
    setPositionsDoc(nextDoc);
    await fs.writeText(positionsPath, serializePositionsDoc(nextDoc));
    setStatusMsg("Layout saved");
  }, [rf, positionsDoc, positionsPath, roomsMap]);

  const onConnectStart = useCallback(
    (_event, { nodeId, handleId, handleType }) => {
      if (!connectionDebugLog) return;
      const seq = ++connectionDragSeqRef.current;
      connectionDragMetaRef.current = { seq, nodeId, handleId, handleType };
      pushConnectionDebug("connectStart", { seq, nodeId, handleId, handleType });
    },
    [connectionDebugLog, pushConnectionDebug]
  );

  const onConnectEnd = useCallback(
    (event, state) => {
      try {
        if (connectionDebugLog) {
          const meta = connectionDragMetaRef.current;
          const nds = rfRef.current.getNodes();
          const slugOf = (nid) => (nid ? nds.find((n) => n.id === nid)?.data?.slug : null) ?? null;
          const fn = state?.fromNode;
          const tn = state?.toNode;
          const fh = state?.fromHandle;
          const th = state?.toHandle;
          pushConnectionDebug("connectEnd", {
            seq: meta?.seq ?? null,
            startMeta: meta,
            rfState: {
              isValid: state?.isValid ?? null,
              fromNodeId: fn?.id ?? null,
              fromSlug: slugOf(fn?.id),
              fromHandleId: fh?.id ?? null,
              fromHandleType: fh?.type ?? null,
              toNodeId: tn?.id ?? null,
              toSlug: slugOf(tn?.id),
              toHandleId: th?.id ?? null,
              toHandleType: th?.type ?? null,
              pointerFlow: state?.pointer ?? null,
            },
            domUnderPointer: pickHandleUnderPointer(event),
          });
        }
      } finally {
        connectionDragMetaRef.current = null;
      }
    },
    [connectionDebugLog, pushConnectionDebug]
  );

  const onConnect = useCallback(
    async (params) => {
      const drag = connectionDragMetaRef.current;
      if (connectionDebugLog) {
        pushConnectionDebug("onConnect_fired", {
          seq: drag?.seq ?? null,
          connectBusyBefore: connectBusyRef.current,
          raw: {
            source: params.source,
            target: params.target,
            sourceHandle: params.sourceHandle,
            targetHandle: params.targetHandle,
          },
        });
      }

      if (connectBusyRef.current) {
        if (connectionDebugLog) pushConnectionDebug("onConnect_skipped_busy", { seq: drag?.seq ?? null });
        return;
      }
      connectBusyRef.current = true;
      try {
        const { source, target, sourceHandle, targetHandle } = params;
        if (!source || !target || source === target) {
          if (connectionDebugLog) pushConnectionDebug("onConnect_aborted_invalid_pair", { source, target });
          return;
        }
        const nds = rf.getNodes();
        const src = nds.find((n) => n.id === source);
        const tgt = nds.find((n) => n.id === target);
        if (!src?.data?.slug || !tgt?.data?.slug) {
          if (connectionDebugLog) {
            pushConnectionDebug("onConnect_aborted_missing_slug", {
              source,
              target,
              srcSlug: src?.data?.slug ?? null,
              tgtSlug: tgt?.data?.slug ?? null,
            });
          }
          return;
        }
        const sDir = (sourceHandle || "north").toLowerCase();
        const tDir = (targetHandle || oppositeDir(sDir)).toLowerCase();
        const srcSlug = src.data.slug;
        const tgtSlug = tgt.data.slug;
        const destForward = `${zoneId}:${tgtSlug}`;
        const destBack = `${zoneId}:${srcSlug}`;

        const sig = `${source}|${sDir}|${target}|${tDir}`;
        const now = typeof performance !== "undefined" ? performance.now() : Date.now();
        const prevDedupe = lastConnectDedupeRef.current;
        if (prevDedupe.sig === sig && now - prevDedupe.t < 750) {
          if (connectionDebugLog) {
            pushConnectionDebug("onConnect_skipped_duplicate_link", {
              seq: drag?.seq ?? null,
              sig,
              deltaMs: Math.round(now - prevDedupe.t),
            });
          }
          setStatusMsg("Same link fired twice; ignored duplicate (within 0.75s)");
          return;
        }

        const curS = { ...(zones[zoneId]?.rooms?.[srcSlug] || {}) };
        curS.exits = { ...(curS.exits || {}) };
        curS.exits[sDir] = { destination: destForward, description: String(curS.exits[sDir]?.description || "") };
        dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: srcSlug, data: curS });
        await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${srcSlug}.yaml`), curS);

        const curT = { ...(zones[zoneId]?.rooms?.[tgtSlug] || {}) };
        curT.exits = { ...(curT.exits || {}) };
        curT.exits[tDir] = { destination: destBack, description: String(curT.exits[tDir]?.description || "") };
        dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug: tgtSlug, data: curT });
        await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${tgtSlug}.yaml`), curT);
        setStatusMsg(`Linked ${sDir} → ${tgtSlug} (${tDir} back)`);
        lastConnectDedupeRef.current = {
          sig,
          t: typeof performance !== "undefined" ? performance.now() : Date.now(),
        };
        if (connectionDebugLog) {
          pushConnectionDebug("onConnect_applied", {
            seq: drag?.seq ?? null,
            srcSlug,
            tgtSlug,
            sDir,
            tDir,
            destForward,
            destBack,
          });
        }
      } finally {
        connectBusyRef.current = false;
      }
    },
    [rf, zoneId, zones, worldRoot, dispatch, connectionDebugLog, pushConnectionDebug]
  );

  const clearAllZoneConnections = useCallback(async () => {
    if (clearConnectionsBusyRef.current) return;
    const zr = zonesRef.current[zoneId]?.rooms || {};
    const slugsToClear = [];
    let exitCount = 0;
    for (const [slug, room] of Object.entries(zr)) {
      const ex = room?.exits && typeof room.exits === "object" ? room.exits : {};
      const n = Object.keys(ex).length;
      if (n > 0) {
        slugsToClear.push(slug);
        exitCount += n;
      }
    }
    if (!slugsToClear.length) {
      setStatusMsg("No connections to clear in this zone");
      return;
    }
    const msg =
      `You are about to remove every exit on every room in zone "${zoneId}".\n\n` +
      `This deletes ${exitCount} connection(s) across ${slugsToClear.length} room(s). YAML files are saved right away.\n\n` +
      `You can undo once with Ctrl+Z or ⌘+Z if this was a mistake.\n\n` +
      `Cancel keeps everything. OK clears all connections.`;
    if (!window.confirm(msg)) return;
    if (
      !window.confirm(
        `Confirm again: clear all ${exitCount} connection(s) in "${zoneId}"? This is easy to undo (Ctrl+Z / ⌘+Z) but destructive until then.`
      )
    ) {
      return;
    }

    clearConnectionsBusyRef.current = true;
    try {
      const prevRooms = {};
      for (const slug of slugsToClear) {
        prevRooms[slug] = JSON.parse(JSON.stringify(zr[slug]));
      }
      const prevPositionsDoc = clonePositionsDoc(positionsDocRef.current);

      undoStackRef.current.push({
        type: "clearConnections",
        prevRooms,
        prevPositionsDoc,
      });
      if (undoStackRef.current.length > UNDO_LIMIT) undoStackRef.current.shift();

      for (const slug of slugsToClear) {
        const cur = JSON.parse(JSON.stringify(zr[slug]));
        cur.exits = {};
        dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data: cur });
        await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), cur);
      }

      setPositionsDoc((prev) => {
        const nextDoc = { ...prev, muted_edges: [] };
        fs.writeText(positionsPath, serializePositionsDoc(nextDoc)).catch(() => {});
        return nextDoc;
      });

      setStatusMsg(`Cleared ${exitCount} connection(s). Press Ctrl+Z or ⌘+Z to undo.`);
    } catch {
      setStatusMsg("Clear all connections failed");
    } finally {
      clearConnectionsBusyRef.current = false;
    }
  }, [zoneId, worldRoot, dispatch, positionsPath]);

  /** Temporary dev tool: delete every room file in the zone (not undoable). */
  const clearAllZoneRoomsTemp = useCallback(async () => {
    if (clearAllRoomsBusyRef.current) return;
    if (!worldRoot || !zoneId) return;
    const zr = zonesRef.current[zoneId]?.rooms || {};
    const slugs = Object.keys(zr);
    if (!slugs.length) {
      setStatusMsg("This zone has no rooms to delete");
      return;
    }
    const msg =
      `TEMP — Delete ALL ${slugs.length} room(s) in zone “${zoneId}”?\n\n` +
      `This permanently removes every rooms/*.yaml file in this zone, clears room positions on the map, and clears muted edges. Canvas notes are kept.\n\n` +
      `This is NOT undone by Ctrl+Z. OK to continue.`;
    if (!window.confirm(msg)) return;
    if (!window.confirm(`Final confirm: delete all rooms in “${zoneId}”?`)) return;

    clearAllRoomsBusyRef.current = true;
    try {
      for (const slug of slugs) {
        try {
          await fs.deleteFile(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`));
        } catch {
          /* missing file */
        }
        dispatch({ type: "DELETE_ZONE_ROOM", zoneId, slug });
      }
      const nextDoc = {
        ...clonePositionsDoc(positionsDocRef.current),
        positions: {},
        muted_edges: [],
      };
      setPositionsDoc(nextDoc);
      await fs.writeText(positionsPath, serializePositionsDoc(nextDoc));
      setSelectedSlug(null);
      setPanelDraft(null);
      setPanelDirty(false);
      setStatusMsg(`TEMP: deleted all ${slugs.length} room(s) in ${zoneId}`);
    } catch {
      setStatusMsg("TEMP clear all rooms failed");
    } finally {
      clearAllRoomsBusyRef.current = false;
    }
  }, [worldRoot, zoneId, dispatch, positionsPath]);

  const onEdgesDelete = useCallback(
    async (deleted) => {
      for (const edge of deleted) {
        await removeLinkedExitPair(edge);
      }
    },
    [removeLinkedExitPair]
  );

  const saveRoomFile = async (slug, data) => {
    await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), data);
    dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data });
    setPanelDirty(false);
  };

  const { err: errC, warn: warnC } = validationCounts(issues);

  if (!zoneId) {
    return <div style={{ padding: 40, color: COLORS.textMuted }}>No zone selected.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: COLORS.bg, position: "relative" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 8,
          padding: "8px 10px",
          borderBottom: `1px solid ${COLORS.border}`,
          background: COLORS.bgPanel,
        }}
      >
        <select
          value={zoneId}
          onChange={(e) => onZoneId(e.target.value)}
          style={{ padding: 6, background: COLORS.bgInput, color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 6 }}
        >
          {zoneIds.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </select>
        <button type="button" style={tbBtn} onClick={() => setRoomSlugModal({ mode: "add", defaultSlug: "" })}>
          Add Room
        </button>
        <button
          type="button"
          style={tbBtn}
          onClick={() => setRoomSlugModal({ mode: "placeholder", defaultSlug: `room_${Date.now()}` })}
        >
          Placeholder
        </button>
        <button type="button" style={tbBtn} onClick={() => layoutGraph(rf.getNodes().filter((n) => n.type === "room"), rf.getEdges()).then((laid) => {
          const rest = rf.getNodes().filter((n) => n.type === "note");
          rf.setNodes([...laid, ...rest]);
        })}>
          Auto Layout
        </button>
        <button type="button" style={tbBtn} onClick={() => rf.fitView({ padding: 0.2 })}>
          Fit View
        </button>
        <button
          type="button"
          style={{
            ...tbBtn,
            background: snapEnabled ? `${COLORS.warning}33` : COLORS.bgCard,
            borderColor: snapEnabled ? COLORS.warning : COLORS.border,
          }}
          onClick={() => {
            const v = !snapEnabled;
            setSnapEnabled(v);
            writeSnapEnabled(v);
          }}
        >
          Snap {snapEnabled ? "ON" : "OFF"}
        </button>
        <button type="button" style={tbBtn} onClick={() => setShowGroups((x) => !x)}>
          Groups
        </button>
        <button type="button" style={tbBtn} onClick={() => setShowVal((x) => !x)}>
          Validate {errC || warnC ? `(${errC ? `✕${errC}` : ""}${warnC ? ` ⚠${warnC}` : ""})` : ""}
        </button>
        <button
          type="button"
          style={{
            ...tbBtn,
            fontSize: 10,
            background: connectionDebugLog ? `${COLORS.info}33` : COLORS.bgCard,
            borderColor: connectionDebugLog ? COLORS.info : COLORS.border,
          }}
          title="Log each door-drag to the console ([Fablestar WorldForger connection]) and to the panel on the map. Also in Settings."
          onClick={() => setConnectionDebugLog(!connectionDebugLog)}
        >
          Conn debug
        </button>
        <button type="button" style={tbBtn} onClick={() => setShowStats((x) => !x)}>
          ∑
        </button>
        <button type="button" style={tbBtn} onClick={saveLayout}>
          Save layout
        </button>
        <button type="button" style={tbBtn} title="Save selected unlocked rooms as a reusable stamp under world/stamps/" onClick={beginSaveStamp}>
          Save stamp…
        </button>
        <button type="button" style={tbBtn} title="Browse and place layout stamps" onClick={() => setStampLibraryOpen(true)}>
          Stamps…
        </button>
        <button
          type="button"
          style={{
            ...tbBtn,
            color: COLORS.danger,
            borderColor: COLORS.danger,
            background: `${COLORS.danger}14`,
          }}
          title="Removes every exit on every room in this zone (two-step confirmation). Ctrl+Z / ⌘+Z undoes once."
          onClick={() => clearAllZoneConnections().catch(() => setStatusMsg("Clear all connections failed"))}
        >
          Clear all connections
        </button>
        <button
          type="button"
          style={{
            ...tbBtn,
            color: COLORS.danger,
            borderColor: COLORS.danger,
            background: `${COLORS.danger}22`,
            fontWeight: 700,
          }}
          title="TEMP: deletes every room YAML in this zone and clears room positions (not undoable). Keeps canvas notes."
          onClick={() => clearAllZoneRoomsTemp().catch(() => setStatusMsg("TEMP clear all rooms failed"))}
        >
          TEMP: Clear all rooms
        </button>
        <span style={{ fontSize: 11, color: COLORS.textDim }}>{statusMsg}</span>
        {arrangeableSelectionCount >= 1 ? (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: 4,
              paddingLeft: 10,
              marginLeft: 4,
              borderLeft: `1px solid ${COLORS.border}`,
            }}
            title="Unlocked rooms in the current selection"
          >
            <span style={{ fontSize: 10, color: COLORS.textDim, marginRight: 4 }}>Rotate</span>
            <button type="button" style={tbBtn} onClick={() => rotateSelectedRooms(-90)} title="Rotate selection −90° around group center (2+ rooms move together)">
              ↺ 90°
            </button>
            <button type="button" style={tbBtn} onClick={() => rotateSelectedRooms(-15)} title="Rotate selection −15° around group center">
              −15°
            </button>
            <button type="button" style={tbBtn} onClick={() => rotateSelectedRooms(15)} title="Rotate selection +15° around group center">
              +15°
            </button>
            <button type="button" style={tbBtn} onClick={() => rotateSelectedRooms(90)} title="Rotate selection +90° around group center">
              90° ↻
            </button>
            <button type="button" style={tbBtn} onClick={resetRotationSelected} title="Clear rotation (0°)">
              0°
            </button>
            <span style={{ fontSize: 10, color: COLORS.textDim, margin: "0 4px 0 10px" }}>Map border</span>
            <input
              type="color"
              aria-label="Map border color for selected rooms"
              value={
                /^#[0-9A-Fa-f]{6}$/i.test(String(selectionLayoutBorderDisplay.value || "").trim())
                  ? selectionLayoutBorderDisplay.value.trim()
                  : "#6b7280"
              }
              onChange={(e) => applyLayoutBorderColorToSelection(e.target.value)}
              style={{
                width: 36,
                height: 28,
                padding: 0,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 6,
                cursor: "pointer",
                background: COLORS.bgInput,
              }}
            />
            <button
              type="button"
              style={tbBtn}
              onClick={() => applyLayoutBorderColorToSelection("")}
              title="Clear custom map border on selected rooms (default)"
            >
              Default
            </button>
          </div>
        ) : null}
        {arrangeableSelectionCount >= 2 ? (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: 4,
              paddingLeft: 10,
              marginLeft: 4,
              borderLeft: `1px solid ${COLORS.border}`,
            }}
            title="Uses unlocked room nodes in the current selection"
          >
            <span style={{ fontSize: 10, color: COLORS.textDim, marginRight: 4 }}>Arrange</span>
            <button type="button" style={tbBtn} onClick={() => runArrange(alignRoomsLeft)} title="Align left edges">
              ← L
            </button>
            <button type="button" style={tbBtn} onClick={() => runArrange(alignRoomsRight)} title="Align right edges">
              R →
            </button>
            <button type="button" style={tbBtn} onClick={() => runArrange(alignRoomsTop)} title="Align top edges">
              ↑ T
            </button>
            <button type="button" style={tbBtn} onClick={() => runArrange(alignRoomsBottom)} title="Align bottom edges">
              ↓ B
            </button>
            <button type="button" style={tbBtn} onClick={() => runArrange(alignRoomsCenterX)} title="Align centers horizontally">
              | ↔ |
            </button>
            <button type="button" style={tbBtn} onClick={() => runArrange(alignRoomsCenterY)} title="Align centers vertically">
              — ⊕ —
            </button>
            <button
              type="button"
              style={{ ...tbBtn, opacity: arrangeableSelectionCount >= 3 ? 1 : 0.45 }}
              disabled={arrangeableSelectionCount < 3}
              onClick={() =>
                runArrange(distributeRoomsHorizontally, {
                  minRooms: 3,
                  tooFewMsg: "Pick 3 or more rooms to distribute horizontally",
                })
              }
              title="Even horizontal spacing between rooms (3+)"
            >
              ≡ H
            </button>
            <button
              type="button"
              style={{ ...tbBtn, opacity: arrangeableSelectionCount >= 3 ? 1 : 0.45 }}
              disabled={arrangeableSelectionCount < 3}
              onClick={() =>
                runArrange(distributeRoomsVertically, {
                  minRooms: 3,
                  tooFewMsg: "Pick 3 or more rooms to distribute vertically",
                })
              }
              title="Even vertical spacing between rooms (3+)"
            >
              ≡ V
            </button>
          </div>
        ) : null}
        <span style={{ fontSize: 10, color: COLORS.textDim, marginLeft: 8, maxWidth: 560 }} title="Door ports use loose connections (source-to-source)">
          Link: door to door (ports stay on map N/S/E/W; room art rotates) · Ctrl/⌘+click add/remove room · Ctrl/⌘+drag box on pane · Rotate + map border toolbar (1+ rooms) · Ctrl/⌘+D duplicate (same layout) · Stamps: Save stamp… / Stamps… then click map to place · Esc cancels placement · Ctrl/⌘+Z undo duplicate / stamp place / arrange / rotate / map border / clear-all-connections · Conn debug → console + panel (drag title bar) · right-drag box (Ctrl/⌘ adds)
        </span>
      </div>

      {showGroups ? (
        <div style={{ padding: 10, background: COLORS.bgCard, borderBottom: `1px solid ${COLORS.border}` }}>
          <div style={{ fontSize: 12, color: COLORS.text, marginBottom: 8 }}>Room groups</div>
          {(groups || []).map((g) => (
            <div key={g.id} style={{ fontSize: 11, color: COLORS.textMuted }}>
              <span style={{ display: "inline-block", width: 12, height: 12, background: g.color, marginRight: 8, borderRadius: 2 }} />
              {g.name} ({g.id})
            </div>
          ))}
          <button type="button" style={{ ...tbBtn, marginTop: 8 }} onClick={() => setGroupModalOpen(true)}>
            + New group
          </button>
        </div>
      ) : null}

      <div ref={containerRef} style={{ flex: 1, position: "relative", minHeight: 0 }}>
        <ReactFlow
          colorMode={colorScheme}
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onConnectStart={onConnectStart}
          onConnectEnd={onConnectEnd}
          onEdgesDelete={onEdgesDelete}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          connectionMode={ConnectionMode.Loose}
          defaultEdgeOptions={{ selectable: false }}
          fitView
          nodesConnectable
          connectionRadius={10}
          nodeDragThreshold={0}
          snapToGrid={snapEnabled}
          snapGrid={snapGrid}
          panOnDrag={[0, 1]}
          selectionKeyCode={["Control", "Meta"]}
          multiSelectionKeyCode={["Control", "Meta"]}
          selectionMode="partial"
          onSelectionChange={({ nodes: sel }) => {
            setArrangeableSelectionCount(sel.filter((n) => n.type === "room" && !n.data?.locked).length);
          }}
          onNodeClick={(_, n) => {
            if (n.type === "room") {
              if (pendingStairLink) {
                if (!n.data?.ghost) {
                  linkStairs(pendingStairLink.slug, pendingStairLink.ghostDir, n.data.slug).catch(() => {});
                  setPendingStairLink(null);
                } else {
                  setPendingStairLink(null);
                  setCurrentFloor(n.data.ghostFloor);
                }
                return;
              }
              if (n.data?.ghost) { setCurrentFloor(n.data.ghostFloor); return; }
              const slug = n.data.slug;
              setSelectedSlug(slug);
              setPanelDraft(zones[zoneId]?.rooms?.[slug] || null);
              setPanelDirty(false);
            }
          }}
          onPaneClick={(ev) => {
            if (pendingStampPlace?.stampSlug && !stampPlaceBusyRef.current) {
              const p = rf.screenToFlowPosition({ x: ev.clientX, y: ev.clientY });
              placeStampAtFlow(p.x, p.y).catch(() => setStatusMsg("Place stamp failed"));
              return;
            }
            setCtx(null);
          }}
          onPaneContextMenu={(e) => {
            if (Date.now() < suppressPaneContextUntilRef.current) {
              e.preventDefault();
              return;
            }
            e.preventDefault();
            const pane = containerRef.current?.getBoundingClientRect();
            if (!pane) return;
            setCtx({ type: "pane", x: e.clientX - pane.left, y: e.clientY - pane.top, flowX: e.clientX, flowY: e.clientY });
          }}
          onNodeContextMenu={(e, n) => {
            e.preventDefault();
            const pane = containerRef.current?.getBoundingClientRect();
            if (!pane) return;
            setCtx({ type: "node", x: e.clientX - pane.left, y: e.clientY - pane.top, node: n });
          }}
          onEdgeContextMenu={(e, edge) => {
            e.preventDefault();
            const pane = containerRef.current?.getBoundingClientRect();
            if (!pane) return;
            setCtx({ type: "edge", x: e.clientX - pane.left, y: e.clientY - pane.top, edge });
          }}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1.5} color={COLORS.textDim} />
          <Controls />
          <MiniMap />
        </ReactFlow>

        {/* Z-level floor switcher */}
        {(() => {
          const floorsMap = positionsDoc.floors || {};
          const floorSet = new Set([0, ...Object.values(floorsMap).map(Number).filter(Number.isFinite)]);
          const allFloors = [...floorSet].sort((a, b) => b - a);
          return (
            <div
              style={{
                position: "absolute",
                left: 10,
                top: 10,
                zIndex: 100,
                display: "flex",
                flexDirection: "column",
                gap: 2,
                background: COLORS.bgPanel,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 8,
                padding: "4px 2px",
                pointerEvents: "all",
                boxShadow: `0 2px 8px ${COLORS.bg}88`,
              }}
            >
              <button
                type="button"
                title="Go up one floor"
                onClick={() => setCurrentFloor((f) => f + 1)}
                style={{ fontSize: 13, lineHeight: 1, padding: "3px 10px", background: "none", border: "none", color: COLORS.info, cursor: "pointer", borderRadius: 5 }}
              >
                ▲
              </button>
              {allFloors.map((f) => (
                <button
                  key={f}
                  type="button"
                  title={`Switch to ${floorLabel(f)}`}
                  onClick={() => setCurrentFloor(f)}
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    fontFamily: "'JetBrains Mono', monospace",
                    padding: "3px 10px",
                    background: f === currentFloor ? COLORS.accent : "none",
                    border: f === currentFloor ? `1px solid ${COLORS.accent}` : "1px solid transparent",
                    borderRadius: 5,
                    color: f === currentFloor ? "#fff" : COLORS.textDim,
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                  }}
                >
                  {floorLabel(f)}
                </button>
              ))}
              <button
                type="button"
                title="Go down one floor"
                onClick={() => setCurrentFloor((f) => f - 1)}
                style={{ fontSize: 13, lineHeight: 1, padding: "3px 10px", background: "none", border: "none", color: COLORS.forge, cursor: "pointer", borderRadius: 5 }}
              >
                ▼
              </button>
            </div>
          );
        })()}

        {/* Stair link mode banner */}
        {pendingStairLink ? (
          <div
            style={{
              position: "absolute",
              top: 10,
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 200,
              background: pendingStairLink.ghostDir === "up" ? COLORS.info : COLORS.forge,
              color: "#fff",
              padding: "6px 16px",
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 700,
              fontFamily: "'DM Sans', sans-serif",
              display: "flex",
              alignItems: "center",
              gap: 10,
              boxShadow: "0 2px 10px #0009",
              pointerEvents: "all",
            }}
          >
            <span>
              {pendingStairLink.ghostDir === "up" ? "↑" : "↓"} Click a room to link {pendingStairLink.ghostDir} from{" "}
              <b>{pendingStairLink.slug}</b> ({floorLabel(pendingStairLink.ghostFloor)}) — ESC to cancel
            </span>
            <button
              type="button"
              onClick={() => setPendingStairLink(null)}
              style={{ background: "none", border: "none", color: "#ffffffcc", cursor: "pointer", fontSize: 16, lineHeight: 1, padding: 0 }}
            >
              ✕
            </button>
          </div>
        ) : null}

        {marqueeScreen && marqueeScreen.width + marqueeScreen.height > 0 ? (
          <div
            style={{
              position: "absolute",
              left: marqueeScreen.left,
              top: marqueeScreen.top,
              width: marqueeScreen.width,
              height: marqueeScreen.height,
              border: `1px dashed ${COLORS.accent}`,
              background: `${COLORS.accent}14`,
              pointerEvents: "none",
              zIndex: 4,
              boxSizing: "border-box",
            }}
          />
        ) : null}

        {connectionDebugLog ? (
          <div
            ref={connDebugPanelRef}
            style={{
              position: "absolute",
              ...(connDebugPanelPos
                ? { left: connDebugPanelPos.left, top: connDebugPanelPos.top, right: "auto", bottom: "auto" }
                : { right: 12, bottom: 12, left: "auto", top: "auto" }),
              zIndex: 1000,
              width: "min(440px, calc(100% - 24px))",
              maxHeight: 260,
              display: "flex",
              flexDirection: "column",
              background: `${COLORS.bgPanel}f2`,
              border: `1px solid ${COLORS.info}`,
              borderRadius: 8,
              boxShadow: `0 4px 20px ${COLORS.bg}aa`,
              fontFamily: "'JetBrains Mono', ui-monospace, monospace",
              fontSize: 10,
              color: COLORS.text,
            }}
          >
            <div
              onPointerDown={onConnDebugPanelHeaderPointerDown}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                padding: "6px 8px",
                borderBottom: `1px solid ${COLORS.border}`,
                flexShrink: 0,
                cursor: "grab",
                userSelect: "none",
              }}
              title="Drag to reposition (saved) · double-click the title to dock bottom-right again"
            >
              <span
                style={{ color: COLORS.textMuted, flex: 1, minWidth: 0 }}
                onDoubleClick={(e) => {
                  e.stopPropagation();
                  setConnDebugPanelPos(null);
                  try {
                    localStorage.removeItem(CONN_DEBUG_PANEL_POS_KEY);
                  } catch {
                    /* ignore */
                  }
                }}
              >
                Connection debug (newest first)
              </span>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  type="button"
                  style={{ ...tbBtn, fontSize: 9, padding: "2px 8px" }}
                  onClick={() => {
                    connectionDebugLinesRef.current = [];
                    setConnectionDebugLines([]);
                  }}
                >
                  Clear
                </button>
                <button
                  type="button"
                  style={{ ...tbBtn, fontSize: 9, padding: "2px 8px" }}
                  onClick={() => {
                    const text = JSON.stringify(connectionDebugLinesRef.current, null, 2);
                    if (navigator.clipboard?.writeText) {
                      navigator.clipboard.writeText(text).then(
                        () => setStatusMsg("Connection log copied to clipboard"),
                        () => setStatusMsg("Copy failed")
                      );
                    } else setStatusMsg("Clipboard not available");
                  }}
                >
                  Copy JSON
                </button>
              </div>
            </div>
            <div style={{ overflow: "auto", padding: 8, lineHeight: 1.35, flex: 1, minHeight: 0 }}>
              {connectionDebugLines.length === 0 ? (
                <span style={{ color: COLORS.textDim }}>
                  Each drag gets its own <code style={{ color: COLORS.text }}>seq</code> (connectStart → onConnect_fired → onConnect_applied → connectEnd). Multiple seq values
                  = multiple drags. Same link twice in under 0.75s logs <code style={{ color: COLORS.text }}>onConnect_skipped_duplicate_link</code>. Compare{" "}
                  <code style={{ color: COLORS.text }}>raw</code> to <code style={{ color: COLORS.text }}>domUnderPointer</code> on connectEnd. Each applied link still writes{" "}
                  <strong>two</strong> YAML exits (out + return) by design.
                </span>
              ) : (
                connectionDebugLines.map((row, i) => (
                  <div key={`${row.t}-${row.kind}-${i}`} style={{ marginBottom: 10, wordBreak: "break-word" }}>
                    <div style={{ color: COLORS.info, marginBottom: 2 }}>
                      {row.t} · {row.kind}
                    </div>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", color: COLORS.textMuted }}>{JSON.stringify(row.detail, null, 2)}</pre>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : null}

        {ctx ? (
          <div
            style={{
              position: "absolute",
              left: ctx.x,
              top: ctx.y,
              zIndex: 20,
              minWidth: 160,
              background: COLORS.bgPanel,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              padding: 6,
              boxShadow: `0 8px 24px ${COLORS.bg}cc`,
            }}
            onMouseLeave={() => setCtx(null)}
          >
            {ctx.type === "pane" ? (
              <>
                <MenuBtn
                  onClick={() => {
                    const p = rf.screenToFlowPosition({ x: ctx.flowX, y: ctx.flowY });
                    setCtx(null);
                    setRoomSlugModal({ mode: "addHere", defaultSlug: "", flowPos: p });
                  }}
                >
                  Add room here
                </MenuBtn>
                <MenuBtn onClick={() => {
                  const p = rf.screenToFlowPosition({ x: ctx.flowX, y: ctx.flowY });
                  const id = `note_${Date.now()}`;
                  setPositionsDoc((prev) => ({
                    ...prev,
                    notes: [...(prev.notes || []), { id, text: "Note", color: "yellow", x: p.x, y: p.y }],
                  }));
                  setCtx(null);
                }}>Add note</MenuBtn>
              </>
            ) : null}
            {ctx.type === "node" && ctx.node?.type === "room" ? (
              <MenuBtn onClick={async () => {
                const slug = ctx.node.data.slug;
                const prevPos = positionsDoc.positions?.[slug] || { x: ctx.node.position.x, y: ctx.node.position.y };
                const locked = !prevPos.locked;
                const nextDoc = {
                  ...positionsDoc,
                  positions: {
                    ...positionsDoc.positions,
                    [slug]: { ...prevPos, x: ctx.node.position.x, y: ctx.node.position.y, locked },
                  },
                };
                setPositionsDoc(nextDoc);
                await fs.writeText(positionsPath, serializePositionsDoc(nextDoc));
                setCtx(null);
              }}>Toggle lock</MenuBtn>
            ) : null}
            {ctx.type === "edge" ? (
              <MenuBtn onClick={async () => {
                const eid = ctx.edge.id;
                const me = [...(positionsDoc.muted_edges || [])];
                if (!me.includes(eid)) me.push(eid);
                const nextDoc = { ...positionsDoc, muted_edges: me };
                setPositionsDoc(nextDoc);
                await fs.writeText(positionsPath, serializePositionsDoc(nextDoc));
                setCtx(null);
              }}>Mute exit</MenuBtn>
            ) : null}
          </div>
        ) : null}

        {(showVal || showStats) && (
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: 0,
              maxHeight: showStats ? 200 : 160,
              background: COLORS.bgPanel,
              borderTop: `1px solid ${COLORS.border}`,
              padding: 10,
              zIndex: 15,
            }}
          >
            {showVal ? (
              <ValidationPanel
                issues={issues}
                onPick={({ nodeId }) => {
                  const n = rf.getNodes().find((x) => x.id === nodeId);
                  if (n) rf.fitView({ nodes: [n], padding: 0.5 });
                }}
              />
            ) : null}
            {showStats ? (
              <div style={{ fontSize: 11, color: COLORS.textMuted }}>
                Rooms: {Object.keys(roomsMap).length} · Exits in graph: {edges.length}
              </div>
            ) : null}
          </div>
        )}
      </div>

      {selectedSlug && panelDraft ? (
        <div
          style={{
            position: "absolute",
            top: 48,
            right: 0,
            width: 360,
            bottom: 0,
            borderLeft: `1px solid ${COLORS.border}`,
            zIndex: 12,
            display: "flex",
            flexDirection: "column",
          }}
        >
          <RoomPanel
            bundleSceneArtIntoWorld
            worldRoot={worldRoot}
            zoneId={zoneId}
            roomSlug={selectedSlug}
            room={panelDraft}
            groups={groups}
            layoutBorderColor={selectionLayoutBorderDisplay.value}
            layoutBorderColorMixed={selectionLayoutBorderDisplay.mixed}
            layoutBorderAppliesToCount={arrangeableSelectionCount}
            onLayoutBorderColorChange={applyLayoutBorderColorToSelection}
            onChangeRoom={(d) => {
              setPanelDraft(d);
              setPanelDirty(true);
              if (selectedSlug) {
                setNodes((nds) =>
                  nds.map((n) =>
                    n.data?.slug === selectedSlug
                      ? { ...n, data: { ...n.data, label: d.name || selectedSlug } }
                      : n
                  )
                );
              }
            }}
            onSave={() => saveRoomFile(selectedSlug, panelDraft)}
            onRevert={() => {
              setPanelDraft(zones[zoneId]?.rooms?.[selectedSlug] || null);
              setPanelDirty(false);
            }}
            dirty={panelDirty}
            roomIndexForPicker={roomIndexForPicker}
            nexusUrl={nexusUrl}
            nexusToken={nexusToken}
          />
        </div>
      ) : null}

      <TextPromptModal
        open={!!roomSlugModal}
        title={
          roomSlugModal?.mode === "add"
            ? "Add room"
            : roomSlugModal?.mode === "placeholder"
              ? "Placeholder room"
              : roomSlugModal?.mode === "addHere"
                ? "Add room here"
                : "Duplicate room"
        }
        hint={
          roomSlugModal?.mode === "add"
            ? "Filename slug — saved as rooms/<slug>.yaml. Letters, numbers, underscore, and hyphen only."
            : roomSlugModal?.mode === "placeholder"
              ? 'Creates a tentative room (display name "?") for layout planning.'
              : roomSlugModal?.mode === "addHere"
                ? "The new room is placed where you right-clicked on the canvas."
                : "Copies this room's YAML except exits. Choose a new unique slug."
        }
        initialValue={roomSlugModal?.defaultSlug ?? ""}
        confirmLabel={
          roomSlugModal?.mode === "duplicate" ? "Duplicate" : roomSlugModal?.mode === "placeholder" ? "Create" : "Add room"
        }
        validate={SLUG_OK}
        invalidMessage="Use only letters, numbers, underscore (_), and hyphen (-)."
        onConfirm={onRoomSlugModalConfirm}
        onCancel={() => setRoomSlugModal(null)}
      />

      <GroupFormModal
        open={groupModalOpen}
        onCancel={() => setGroupModalOpen(false)}
        onConfirm={async ({ id, name, color }) => {
          setGroupModalOpen(false);
          const next = [...(groups || []), { id, name, color }];
          setGroups(next);
          await fs.writeYaml(groupsPath, next);
        }}
      />

      <SaveStampModal
        open={saveStampOpen}
        initialDisplayName={saveStampDraft?.defaultDisplayName ?? ""}
        initialSlug={stampSlugFromDisplayName(saveStampDraft?.defaultDisplayName ?? "")}
        validateSlug={SLUG_OK}
        invalidMessage="Use only letters, numbers, underscore (_), and hyphen (-)."
        onSave={onSaveStampConfirm}
        onCancel={() => {
          setSaveStampOpen(false);
          setSaveStampDraft(null);
        }}
      />

      <StampLibraryModal
        open={stampLibraryOpen}
        worldRoot={worldRoot}
        onClose={() => setStampLibraryOpen(false)}
        onPlaceInZone={(slug) => {
          setPendingStampPlace({ stampSlug: slug });
          setStatusMsg("Click the map to place the stamp (anchor = normalized top-left). Esc to cancel.");
        }}
      />
    </div>
  );
}

export default function ZoneEditor(props) {
  return (
    <ReactFlowProvider>
      <ZoneEditorInner {...props} />
    </ReactFlowProvider>
  );
}
