import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { useTheme } from "../ThemeContext.jsx";

const CORNER_QUARTER_PX = 16;

const CORNER_QUARTER_RADIUS = {
  northwest: {
    borderTopLeftRadius: CORNER_QUARTER_PX,
    borderTopRightRadius: 0,
    borderBottomLeftRadius: 0,
    borderBottomRightRadius: 0,
  },
  northeast: {
    borderTopRightRadius: CORNER_QUARTER_PX,
    borderTopLeftRadius: 0,
    borderBottomRightRadius: 0,
    borderBottomLeftRadius: 0,
  },
  southwest: {
    borderBottomLeftRadius: CORNER_QUARTER_PX,
    borderTopLeftRadius: 0,
    borderTopRightRadius: 0,
    borderBottomRightRadius: 0,
  },
  southeast: {
    borderBottomRightRadius: CORNER_QUARTER_PX,
    borderTopLeftRadius: 0,
    borderTopRightRadius: 0,
    borderBottomLeftRadius: 0,
  },
};

const CORNER_QUARTER_POS = {
  northwest: { left: 0, top: 0, transform: "translate(-100%, -100%)" },
  northeast: { left: "100%", top: 0, transform: "translate(0, -100%)" },
  southwest: { left: 0, bottom: 0, transform: "translate(-100%, 100%)" },
  southeast: { left: "100%", bottom: 0, transform: "translate(0, 100%)" },
};

const CORNER_HIT_CLIP = {
  northwest: `circle(${CORNER_QUARTER_PX}px at 100% 100%)`,
  northeast: `circle(${CORNER_QUARTER_PX}px at 0% 100%)`,
  southwest: `circle(${CORNER_QUARTER_PX}px at 100% 0%)`,
  southeast: `circle(${CORNER_QUARTER_PX}px at 0% 0%)`,
};

const EXIT_EDGE_LABEL = { north: "N", south: "S", east: "E", west: "W" };
const EXIT_CORNER_LABEL = { northwest: "NW", northeast: "NE", southwest: "SW", southeast: "SE" };

/** @param {'edge' | 'corner' | 'stairs-up' | 'stairs-down'} variant */
function Port({ position, id, style = {}, variant = "edge" }) {
  const { colors: COLORS } = useTheme();
  const doorBorder = COLORS.borderActive;
  const doorBg = COLORS.bgPanel;
  const upBorder = COLORS.info;
  const upBg = `${COLORS.info}2a`;
  const downBorder = COLORS.forge;
  const downBg = `${COLORS.forge}2a`;

  let border;
  let bg;
  let width = 16;
  let height = 16;
  let extra = {};
  let zIndex = 6;
  let borderRadius = 4;

  if (variant === "corner") {
    border = doorBorder;
    bg = doorBg;
    borderRadius = 0;
    width = CORNER_QUARTER_PX;
    height = CORNER_QUARTER_PX;
    zIndex = 7;
    Object.assign(extra, CORNER_QUARTER_RADIUS[id] || CORNER_QUARTER_RADIUS.northwest);
    const clip = CORNER_HIT_CLIP[id] || CORNER_HIT_CLIP.northwest;
    extra.clipPath = clip;
    extra.WebkitClipPath = clip;
  } else if (variant === "stairs-up") {
    border = upBorder;
    bg = upBg;
    borderRadius = 4;
    width = 13;
    height = 15;
    extra = { boxShadow: `inset 0 -3px 0 ${COLORS.info}55`, zIndex: 8 };
  } else if (variant === "stairs-down") {
    border = downBorder;
    bg = downBg;
    borderRadius = 4;
    width = 13;
    height = 15;
    extra = { boxShadow: `inset 0 3px 0 ${COLORS.forge}55`, zIndex: 8 };
  } else {
    border = doorBorder;
    bg = doorBg;
    borderRadius = 4;
  }

  const cornerPos = variant === "corner" && CORNER_QUARTER_POS[id] ? CORNER_QUARTER_POS[id] : null;

  const base = {
    width,
    height,
    border: `2px solid ${border}`,
    background: bg,
    borderRadius,
    zIndex,
    boxSizing: "border-box",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    ...(cornerPos || {}),
    ...extra,
    ...style,
  };

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
    <Handle type="source" position={position} id={id} style={base}>
      {mark}
    </Handle>
  );
}

export default memo(function ShipRoomNode({ data, selected }) {
  const { colors: COLORS, roomTypeColors: ROOM_TYPE_COLORS } = useTheme();
  const tc = ROOM_TYPE_COLORS[data.roomType] || ROOM_TYPE_COLORS["?"];
  const w = 160;
  return (
    <div
      style={{
        position: "relative",
        minWidth: w,
        borderRadius: 10,
        border: `2px solid ${selected ? tc : COLORS.border}`,
        background: selected ? `${tc}0d` : COLORS.bgCard,
        fontFamily: "'DM Sans', sans-serif",
        overflow: "visible",
      }}
    >
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: tc, opacity: 0.85, borderRadius: "10px 0 0 10px" }} />
      <Port position={Position.Top} id="north" style={{ left: "50%", top: -2, transform: "translate(-50%, -50%)" }} />
      <Port position={Position.Bottom} id="south" style={{ left: "50%", bottom: -2, transform: "translate(-50%, 50%)" }} />
      <Port position={Position.Left} id="west" style={{ top: "50%", left: -2, transform: "translate(-50%, -50%)" }} />
      <Port position={Position.Right} id="east" style={{ top: "50%", right: -2, transform: "translate(50%, -50%)" }} />
      <Port variant="corner" position={Position.Top} id="northwest" />
      <Port variant="corner" position={Position.Top} id="northeast" />
      <Port variant="corner" position={Position.Bottom} id="southwest" />
      <Port variant="corner" position={Position.Bottom} id="southeast" />
      <Port variant="stairs-up" position={Position.Top} id="up" style={{ left: "22%", top: -2, transform: "translate(-50%, -50%)" }} />
      <Port variant="stairs-down" position={Position.Bottom} id="down" style={{ left: "22%", bottom: -2, transform: "translate(-50%, 50%)" }} />
      <div style={{ padding: "10px 12px 10px 14px" }}>
        <div style={{ fontWeight: 700, fontSize: 11, color: COLORS.text }}>{data.label}</div>
        <div style={{ fontSize: 9, color: COLORS.textDim, marginTop: 4 }}>{data.roomType}</div>
      </div>
    </div>
  );
});
