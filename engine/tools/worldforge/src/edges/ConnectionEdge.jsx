import { BaseEdge, EdgeLabelRenderer, getBezierPath } from "@xyflow/react";
import { useTheme } from "../ThemeContext.jsx";

export default function ConnectionEdge({
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
  const { colors: COLORS } = useTheme();
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
          stroke: selected ? COLORS.cyan : COLORS.borderActive,
          strokeWidth: selected ? 2 : 1.5,
        }}
      />
      <EdgeLabelRenderer>
        <div
          className="nodrag nopan"
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            fontSize: 9,
            color: COLORS.textDim,
            pointerEvents: "none",
          }}
        >
          {data?.label || ""}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
