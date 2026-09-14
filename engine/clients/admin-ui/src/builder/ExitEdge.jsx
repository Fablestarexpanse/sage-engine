import { BaseEdge, EdgeLabelRenderer, getBezierPath } from "@xyflow/react";
import { useAdminTheme } from "../AdminThemeContext.jsx";

export default function ExitEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
  selected,
}) {
  const { colors: COLORS } = useAdminTheme();
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: selected ? COLORS.accent : COLORS.borderActive,
          strokeWidth: selected ? 2.5 : 1.5,
          strokeDasharray: data?.oneWay ? "6 4" : undefined,
        }}
      />
      <EdgeLabelRenderer>
        <div
          className="nodrag nopan"
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            fontSize: 9,
            fontFamily: "'JetBrains Mono', monospace",
            padding: "2px 6px",
            borderRadius: 4,
            background: COLORS.bgPanel,
            border: `1px solid ${COLORS.border}`,
            color: COLORS.textMuted,
            pointerEvents: "all",
          }}
        >
          {data?.direction || data?.label || ""}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
