import { memo, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Handle, NodeResizer, NodeToolbar, Position, useStore } from "@xyflow/react";
import { useTheme } from "../ThemeContext.jsx";
import {
  canvasLayoutCardinal,
  canvasLayoutCorner,
  canvasLayoutStairs,
} from "../utils/roomExitCanvasLayout.js";
import { DEFAULT_ROOM_NODE_H, DEFAULT_ROOM_NODE_W } from "../utils/zoneGraph.js";

/** Shown on ports (map / workspace compass, not room-local after spin). */
const EXIT_EDGE_LABEL = { north: "N", south: "S", east: "E", west: "W" };
const EXIT_CORNER_LABEL = { northwest: "NW", northeast: "NE", southwest: "SW", southeast: "SE" };

/**
 * @param {'edge' | 'corner' | 'stairs-up' | 'stairs-down'} variant
 * @param {{ left: number, top: number, position: import('@xyflow/react').Position }} [canvasPlacement] map/workspace-aligned position (parent = unrotated node box)
 */
function DoorPort({ position, canvasPlacement, id, style = {}, linked, unlinked, variant = "edge", onContextMenu }) {
  const { colors: COLORS } = useTheme();
  const doorBorder = unlinked ? COLORS.warning : linked ? COLORS.success : COLORS.borderActive;
  const doorBg = unlinked ? `${COLORS.warning}44` : linked ? `${COLORS.success}33` : COLORS.bgPanel;

  const upBorder = unlinked ? COLORS.warning : linked ? COLORS.success : COLORS.info;
  const upBg = unlinked ? `${COLORS.warning}44` : linked ? `${COLORS.success}33` : `${COLORS.info}2a`;
  const downBorder = unlinked ? COLORS.warning : linked ? COLORS.success : COLORS.forge;
  const downBg = unlinked ? `${COLORS.warning}44` : linked ? `${COLORS.success}33` : `${COLORS.forge}2a`;

  const flowPos = canvasPlacement?.position ?? position;
  const canvasCorner = Boolean(canvasPlacement && variant === "corner");

  let border;
  let bg;
  let borderRadius;
  let width = 18;
  let height = 18;
  let extra = {};
  let z = 6;

  if (canvasCorner) {
    border = doorBorder;
    bg = doorBg;
    borderRadius = 7;
    width = 14;
    height = 14;
    z = 8;
  } else if (variant === "stairs-up") {
    border = upBorder;
    bg = upBg;
    borderRadius = 4;
    width = 13;
    height = 15;
    extra = {
      boxShadow: linked ? `inset 0 -3px 0 ${COLORS.info}99` : `inset 0 -3px 0 ${COLORS.info}55`,
      zIndex: 8,
    };
    z = 8;
  } else if (variant === "stairs-down") {
    border = downBorder;
    bg = downBg;
    borderRadius = 4;
    width = 13;
    height = 15;
    extra = {
      boxShadow: linked ? `inset 0 3px 0 ${COLORS.forge}aa` : `inset 0 3px 0 ${COLORS.forge}55`,
      zIndex: 8,
    };
    z = 8;
  } else {
    border = doorBorder;
    bg = doorBg;
    borderRadius = 4;
  }

  const placeStyle = canvasPlacement
    ? {
        position: "absolute",
        left: canvasPlacement.left,
        top: canvasPlacement.top,
        transform: "translate(-50%, -50%)",
        zIndex: z,
      }
    : {};

  const base = {
    width,
    height,
    border: `2px solid ${border}`,
    background: bg,
    borderRadius,
    boxSizing: "border-box",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    ...extra,
    ...(canvasPlacement ? {} : { zIndex: z }),
    ...placeStyle,
    ...style,
  };

  let tip = `Exit “${id}” — map / workspace compass; drag to link`;
  if (unlinked) tip = `Exit “${id}” — unlinked; drag to another room or set destination`;
  else if (linked) tip = `Exit “${id}” — linked in this zone`;
  if (variant === "stairs-up") tip = `Stairs / up (${id}) — ${tip}`;
  if (variant === "stairs-down") tip = `Stairs / down (${id}) — ${tip}`;
  if (variant === "corner") tip = `Corner ${id} — ${tip}`;

  const labelStyle = {
    fontSize: variant === "corner" ? 6 : 8,
    fontWeight: 800,
    color: border,
    lineHeight: 1,
    pointerEvents: "none",
    userSelect: "none",
  };

  const mark =
    variant === "stairs-up" ? (
      <span style={{ fontSize: 9, fontWeight: 800, color: border, lineHeight: 1, pointerEvents: "none", userSelect: "none" }}>↑</span>
    ) : variant === "stairs-down" ? (
      <span style={{ fontSize: 9, fontWeight: 800, color: border, lineHeight: 1, pointerEvents: "none", userSelect: "none" }}>↓</span>
    ) : variant === "corner" && EXIT_CORNER_LABEL[id] ? (
      <span style={labelStyle}>{EXIT_CORNER_LABEL[id]}</span>
    ) : EXIT_EDGE_LABEL[id] ? (
      <span style={labelStyle}>{EXIT_EDGE_LABEL[id]}</span>
    ) : null;

  return (
    <Handle type="source" position={flowPos} id={id} style={base} title={tip} onContextMenu={onContextMenu}>
      {mark}
    </Handle>
  );
}

/** Inset so door ports (≈18px) + 3px stripe never sit over text/tags */
const CONTENT_INSET = { top: 22, right: 22, bottom: 22, left: 26 };

export default memo(function RoomNode({ data, selected }) {
  const { colors: COLORS, roomTypeColors: ROOM_TYPE_COLORS } = useTheme();
  const btnStyle = useMemo(
    () => ({
      fontSize: 10,
      padding: "0 6px",
      height: 22,
      borderRadius: 4,
      border: `1px solid ${COLORS.border}`,
      background: COLORS.bgCard,
      color: COLORS.text,
      cursor: "pointer",
    }),
    [COLORS]
  );
  const tc = ROOM_TYPE_COLORS[data.roomType] || ROOM_TYPE_COLORS["?"];
  const gc = data.groupColor;
  const isPh = data.isPlaceholder;
  const locked = data.locked;
  const showGroupStripe = Boolean(gc);
  const borderStyle = isPh ? "dashed" : "solid";
  const isGhost = Boolean(data.ghost);
  const opacity = isGhost ? 0.35 : isPh ? 0.6 : 1;
  const customEdge = typeof data.layoutBorderColor === "string" ? data.layoutBorderColor : null;
  const edgeStroke = customEdge || (selected ? tc : COLORS.border);
  const glow = customEdge || tc;

  const tb = data.toolbar || {};
  const unlinked = Array.isArray(data.unlinkedExitDirs) ? data.unlinkedExitDirs : [];
  const linked = Array.isArray(data.linkedExitDirs) ? data.linkedExitDirs : [];

  const rot = Number(data.rotation);
  const rotationDeg = Number.isFinite(rot) ? rot : 0;

  const containerRef = useRef(null);
  const [dims, setDims] = useState({ w: DEFAULT_ROOM_NODE_W, h: DEFAULT_ROOM_NODE_H });

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => {
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      if (w > 0 && h > 0) setDims({ w, h });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const multiRoomSelect = useStore(
    (s) => s.nodes.filter((n) => n.type === "room" && n.selected).length > 1
  );

  const lay = useMemo(() => {
    const W = dims.w;
    const H = dims.h;
    return {
      north: canvasLayoutCardinal(W, H, rotationDeg, "north"),
      south: canvasLayoutCardinal(W, H, rotationDeg, "south"),
      east: canvasLayoutCardinal(W, H, rotationDeg, "east"),
      west: canvasLayoutCardinal(W, H, rotationDeg, "west"),
      nw: canvasLayoutCorner(W, H, rotationDeg, "northwest"),
      ne: canvasLayoutCorner(W, H, rotationDeg, "northeast"),
      sw: canvasLayoutCorner(W, H, rotationDeg, "southwest"),
      se: canvasLayoutCorner(W, H, rotationDeg, "southeast"),
      up: canvasLayoutStairs(W, H, rotationDeg, "up"),
      down: canvasLayoutStairs(W, H, rotationDeg, "down"),
    };
  }, [dims.w, dims.h, rotationDeg]);

  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        boxSizing: "border-box",
        overflow: "visible",
        opacity,
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          width: "100%",
          height: "100%",
          boxSizing: "border-box",
          borderRadius: 10,
          border: `2px ${borderStyle} ${edgeStroke}`,
          background: selected ? `${tc}0d` : COLORS.bgCard,
          boxShadow: selected ? `0 0 0 2px ${glow}55` : "none",
          overflow: "visible",
          transform: `translate(-50%, -50%)${rotationDeg ? ` rotate(${rotationDeg}deg)` : ""}`,
          transformOrigin: "center center",
        }}
      >
        {!locked ? (
          <NodeResizer
            isVisible={selected}
            minWidth={140}
            minHeight={88}
            maxWidth={520}
            maxHeight={400}
            color={COLORS.accent}
            handleStyle={{
              width: 11,
              height: 11,
              borderRadius: 3,
              border: `2px solid ${COLORS.bgPanel}`,
              background: COLORS.accent,
              boxShadow: `0 0 0 1px ${COLORS.border}`,
            }}
            lineStyle={{ borderColor: `${COLORS.accent}99`, borderWidth: 1 }}
          />
        ) : null}
        {showGroupStripe ? (
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: 3,
              background: gc,
              opacity: 0.95,
              borderRadius: "10px 0 0 10px",
            }}
          />
        ) : (
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: 3,
              background: tc,
              opacity: 0.85,
              borderRadius: "10px 0 0 10px",
            }}
          />
        )}

        <NodeToolbar position={Position.Top} align="center" isVisible={selected && !locked && !multiRoomSelect}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
            padding: "4px 6px",
            borderRadius: 8,
            background: COLORS.bgPanel,
            border: `1px solid ${COLORS.border}`,
            boxShadow: `0 2px 8px ${COLORS.bg}88`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap", justifyContent: "center" }}>
            <button type="button" title="Add exit north" style={btnStyle} onClick={() => tb.onQuickExit?.("north")}>
              ↑N
            </button>
            <button type="button" title="Add exit south" style={btnStyle} onClick={() => tb.onQuickExit?.("south")}>
              ↓S
            </button>
            <button type="button" title="Add exit east" style={btnStyle} onClick={() => tb.onQuickExit?.("east")}>
              →E
            </button>
            <button type="button" title="Add exit west" style={btnStyle} onClick={() => tb.onQuickExit?.("west")}>
              ←W
            </button>
            <button type="button" title="Add exit up" style={btnStyle} onClick={() => tb.onQuickExit?.("up")}>
              U
            </button>
            <button type="button" title="Add exit down" style={btnStyle} onClick={() => tb.onQuickExit?.("down")}>
              Dn
            </button>
            <div style={{ width: 1, alignSelf: "stretch", background: COLORS.border, margin: "0 2px" }} />
            <button type="button" title="Duplicate room" style={btnStyle} onClick={() => tb.onDuplicate?.()}>
              ⧉
            </button>
            <button type="button" title="AI describe" style={btnStyle} onClick={() => tb.onAiDescribe?.()}>
              ✨
            </button>
            <button type="button" title="Delete room" style={{ ...btnStyle, color: COLORS.danger }} onClick={() => tb.onDelete?.()}>
              🗑
            </button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap", justifyContent: "center" }}>
            <button type="button" title="Add exit northwest" style={btnStyle} onClick={() => tb.onQuickExit?.("northwest")}>
              NW
            </button>
            <button type="button" title="Add exit northeast" style={btnStyle} onClick={() => tb.onQuickExit?.("northeast")}>
              NE
            </button>
            <button type="button" title="Add exit southwest" style={btnStyle} onClick={() => tb.onQuickExit?.("southwest")}>
              SW
            </button>
            <button type="button" title="Add exit southeast" style={btnStyle} onClick={() => tb.onQuickExit?.("southeast")}>
              SE
            </button>
          </div>
        </div>
      </NodeToolbar>

      {locked ? (
        <div
          style={{
            position: "absolute",
            right: CONTENT_INSET.right - 4,
            top: CONTENT_INSET.top - 4,
            fontSize: 11,
            zIndex: 8,
          }}
          title="Locked"
        >
          🔒
        </div>
      ) : null}

      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxSizing: "border-box",
          padding: `${CONTENT_INSET.top}px ${CONTENT_INSET.right}px ${CONTENT_INSET.bottom}px ${CONTENT_INSET.left}px`,
        }}
      >
        <div
          style={{
            minWidth: 0,
            width: "100%",
            maxWidth: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontWeight: 700,
              fontSize: 12,
              color: COLORS.text,
              fontFamily: "'Space Grotesk', sans-serif",
              lineHeight: 1.25,
              maxWidth: "100%",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {data.showRoomId ? `${data.zoneId || ""}:${data.slug}` : null}
            {data.showRoomId ? <br /> : null}
            {isPh ? "?" : data.label || data.slug}
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              flexWrap: "wrap",
              maxWidth: "100%",
            }}
          >
            <span
              style={{
                fontSize: 9,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                padding: "2px 7px",
                borderRadius: 4,
                background: `${tc}22`,
                color: tc,
                border: `1px solid ${tc}55`,
                fontFamily: "'JetBrains Mono', monospace",
                fontWeight: 600,
              }}
            >
              {data.roomType || "?"}
            </span>
            {data.groupName && (data.zoom ?? 1) > 0.8 ? (
              <span
                style={{
                  fontSize: 9,
                  color: COLORS.textDim,
                  maxWidth: "min(120px, 100%)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {data.groupName}
              </span>
            ) : null}
            <span style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>d{data.depth ?? 0}</span>
            {data.entityCount > 0 && (
              <span
                title="Entity spawns"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  minWidth: 20,
                  height: 18,
                  padding: "0 5px",
                  borderRadius: 5,
                  fontSize: 9,
                  fontWeight: 700,
                  fontFamily: "'JetBrains Mono', monospace",
                  color: COLORS.danger,
                  background: `${COLORS.danger}18`,
                  border: `1px solid ${COLORS.danger}55`,
                }}
              >
                {data.entityCount}
              </span>
            )}
            {!data.hasDescription && (
              <span style={{ fontSize: 10, color: COLORS.warning, fontWeight: 700 }} title="Missing description">
                !
              </span>
            )}
          </div>
        </div>
      </div>
      </div>

      {isGhost ? (
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: "100%",
            height: "100%",
            boxSizing: "border-box",
            borderRadius: 10,
            transform: `translate(-50%, -50%)${rotationDeg ? ` rotate(${rotationDeg}deg)` : ""}`,
            transformOrigin: "center center",
            background: "rgba(10,12,28,0.55)",
            border: `2px dashed ${data.ghostDir === "up" ? COLORS.info : COLORS.forge}88`,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 5,
            cursor: "pointer",
            zIndex: 10,
            pointerEvents: "all",
          }}
        >
          <span
            style={{
              padding: "2px 8px",
              borderRadius: 6,
              background: data.ghostDir === "up" ? `${COLORS.info}cc` : `${COLORS.forge}cc`,
              color: "#fff",
              fontSize: 11,
              fontWeight: 700,
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: 0.5,
              pointerEvents: "none",
            }}
          >
            {data.ghostDir === "up"
              ? `↑ ${data.ghostFloor === 0 ? "Ground" : data.ghostFloor > 0 ? `F${data.ghostFloor}` : `B${Math.abs(data.ghostFloor)}`}`
              : `↓ ${data.ghostFloor === 0 ? "Ground" : data.ghostFloor > 0 ? `F${data.ghostFloor}` : `B${Math.abs(data.ghostFloor)}`}`}
          </span>
          <div style={{ display: "flex", gap: 4 }}>
            {!data.ghostLinked && (
              <button
                type="button"
                title="Link this stair to a room on the current floor"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => { e.stopPropagation(); data.toolbar?.onStartLink?.(); }}
                style={{
                  fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4, cursor: "pointer",
                  background: data.ghostDir === "up" ? `${COLORS.info}33` : `${COLORS.forge}33`,
                  border: `1px solid ${data.ghostDir === "up" ? COLORS.info : COLORS.forge}`,
                  color: "#fff",
                }}
              >
                ⤢ Link
              </button>
            )}
            <button
              type="button"
              title={data.ghostLinked ? "Unlink stair exit" : "Remove stair exit"}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); data.toolbar?.onToggleExit?.(); }}
              style={{
                fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4, cursor: "pointer",
                background: `${COLORS.danger}22`,
                border: `1px solid ${COLORS.danger}66`,
                color: COLORS.danger,
              }}
            >
              ✕
            </button>
          </div>
        </div>
      ) : null}

      <DoorPort canvasPlacement={lay.north} position={Position.Top} id="north" linked={linked.includes("north")} unlinked={unlinked.includes("north")} />
      <DoorPort canvasPlacement={lay.south} position={Position.Bottom} id="south" linked={linked.includes("south")} unlinked={unlinked.includes("south")} />
      <DoorPort canvasPlacement={lay.west} position={Position.Left} id="west" linked={linked.includes("west")} unlinked={unlinked.includes("west")} />
      <DoorPort canvasPlacement={lay.east} position={Position.Right} id="east" linked={linked.includes("east")} unlinked={unlinked.includes("east")} />
      <DoorPort canvasPlacement={lay.nw} variant="corner" position={Position.Top} id="northwest" linked={linked.includes("northwest")} unlinked={unlinked.includes("northwest")} />
      <DoorPort canvasPlacement={lay.ne} variant="corner" position={Position.Top} id="northeast" linked={linked.includes("northeast")} unlinked={unlinked.includes("northeast")} />
      <DoorPort canvasPlacement={lay.sw} variant="corner" position={Position.Bottom} id="southwest" linked={linked.includes("southwest")} unlinked={unlinked.includes("southwest")} />
      <DoorPort canvasPlacement={lay.se} variant="corner" position={Position.Bottom} id="southeast" linked={linked.includes("southeast")} unlinked={unlinked.includes("southeast")} />
      <DoorPort
        canvasPlacement={lay.up} variant="stairs-up" position={Position.Top} id="up"
        linked={linked.includes("up")} unlinked={unlinked.includes("up")}
        onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); tb.onToggleStair?.("up"); }}
      />
      <DoorPort
        canvasPlacement={lay.down} variant="stairs-down" position={Position.Bottom} id="down"
        linked={linked.includes("down")} unlinked={unlinked.includes("down")}
        onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); tb.onToggleStair?.("down"); }}
      />
    </div>
  );
});
