import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { adminRoomTypeColors } from "./builderConstants.js";
import { useAdminTheme } from "../AdminThemeContext.jsx";

function DualHandle({ position, id, style = {}, colors }) {
  const C = colors;
  const base = {
    width: 8,
    height: 8,
    border: `1px solid ${C.borderActive}`,
    background: C.bgPanel,
    ...style,
  };
  return (
    <>
      <Handle type="target" position={position} id={id} style={base} />
      <Handle type="source" position={position} id={id} style={{ ...base, ...style }} />
    </>
  );
}

export default memo(function RoomNode({ data, selected }) {
  const { colors: COLORS } = useAdminTheme();
  const ROOM_TYPE_COLORS = adminRoomTypeColors(COLORS);
  const tc = ROOM_TYPE_COLORS[data.roomType] || ROOM_TYPE_COLORS["?"];
  const w = 176;

  return (
    <div
      style={{
        position: "relative",
        minWidth: w,
        borderRadius: 10,
        border: `2px solid ${selected ? tc : COLORS.border}`,
        background: selected ? `${tc}0d` : COLORS.bgCard,
        fontFamily: "'DM Sans', sans-serif",
        boxShadow: selected ? `0 0 0 1px ${tc}44` : "none",
        overflow: "hidden",
      }}
    >
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: tc, opacity: 0.85, borderRadius: "10px 0 0 10px" }} />

      <DualHandle position={Position.Top} id="north" style={{ left: "50%" }} colors={COLORS} />
      <DualHandle position={Position.Bottom} id="south" style={{ left: "50%" }} colors={COLORS} />
      <DualHandle position={Position.Left} id="west" style={{ top: "50%" }} colors={COLORS} />
      <DualHandle position={Position.Right} id="east" style={{ top: "50%" }} colors={COLORS} />
      <DualHandle position={Position.Top} id="up" style={{ left: "18%", width: 7, height: 7, opacity: 0.9 }} colors={COLORS} />
      <DualHandle position={Position.Bottom} id="down" style={{ left: "18%", width: 7, height: 7, opacity: 0.9 }} colors={COLORS} />

      <div style={{ padding: "10px 12px 10px 14px" }}>
        <div
          style={{
            fontWeight: 700,
            fontSize: 12,
            color: COLORS.text,
            marginBottom: 6,
            fontFamily: "'Space Grotesk', sans-serif",
            lineHeight: 1.25,
            maxWidth: w - 24,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {data.label || data.slug}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
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
  );
});
