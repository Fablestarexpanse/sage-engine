import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { useTheme } from "../ThemeContext.jsx";

export default memo(function SystemNode({ data, selected }) {
  const { colors: COLORS } = useTheme();
  return (
    <div
      style={{
        minWidth: 140,
        padding: "10px 12px",
        borderRadius: 10,
        border: `2px solid ${selected ? COLORS.accent : COLORS.border}`,
        background: COLORS.bgCard,
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      <Handle type="target" position={Position.Top} id="t" style={{ opacity: 0.5 }} />
      <Handle type="source" position={Position.Bottom} id="s" style={{ opacity: 0.5 }} />
      <div style={{ fontWeight: 700, fontSize: 12, color: COLORS.text, marginBottom: 4 }}>{data.label}</div>
      <div style={{ fontSize: 9, color: COLORS.textMuted }}>
        {(data.starType || "?") + " · " + (data.faction || "?") + " · " + (data.security || "?")}
      </div>
    </div>
  );
});
