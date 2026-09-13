import { useEffect, useState } from "react";
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from "@xyflow/react";
import { useTheme } from "../ThemeContext.jsx";

function linkLabelText(data) {
  const m = String(data?.mapLabel || "").trim();
  return m || data?.direction || "";
}

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
  const { colors: COLORS } = useTheme();
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const [labelDraft, setLabelDraft] = useState(() => linkLabelText(data));
  useEffect(() => {
    setLabelDraft(linkLabelText(data));
  }, [id, data?.mapLabel, data?.direction]);

  const muted = Boolean(data?.muted);
  const oneWay = Boolean(data?.oneWay);
  const strokeColor = muted ? COLORS.textDim : selected ? COLORS.accent : COLORS.borderActive;
  const dash = muted ? "6 4" : oneWay ? "6 4" : undefined;
  const canEditLabel = Boolean(selected && data?.edgeToolbar?.onSetMapLabel);
  const lineLabel = linkLabelText(data);

  const commitLabel = () => {
    const t = labelDraft.trim();
    const fallback = String(data?.direction || "").trim();
    const next = t === "" || t === fallback ? "" : t;
    data?.edgeToolbar?.onSetMapLabel?.(next);
  };

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={muted ? undefined : markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth: selected ? 2.5 : 1.5,
          strokeDasharray: dash,
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
            maxWidth: 160,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={lineLabel}
        >
          {lineLabel}
        </div>
      </EdgeLabelRenderer>
      {selected && data?.edgeToolbar ? (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -120%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
              display: "flex",
              flexDirection: "column",
              gap: 6,
              background: COLORS.bgPanel,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 6,
              padding: "6px 8px",
              minWidth: canEditLabel ? 200 : undefined,
            }}
            className="nodrag nopan"
          >
            {canEditLabel ? (
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 9, color: COLORS.textMuted }}>Link label (map)</span>
                <input
                  type="text"
                  value={labelDraft}
                  onChange={(e) => setLabelDraft(e.target.value)}
                  onBlur={commitLabel}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      commitLabel();
                      e.target.blur();
                    }
                  }}
                  placeholder={data?.direction || "direction"}
                  style={{
                    fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                    padding: "6px 8px",
                    borderRadius: 4,
                    border: `1px solid ${COLORS.border}`,
                    background: COLORS.bgInput,
                    color: COLORS.text,
                  }}
                />
              </label>
            ) : null}
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              <button
                type="button"
                title="Add return exit"
                onClick={() => data.edgeToolbar.onAddReturn?.()}
                style={{ fontSize: 11, background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, color: COLORS.text, borderRadius: 4, cursor: "pointer" }}
              >
                ⇄ Return
              </button>
              <button
                type="button"
                title="Remove exit"
                onClick={() => data.edgeToolbar.onRemove?.()}
                style={{
                  fontSize: 11,
                  color: COLORS.danger,
                  background: COLORS.bgCard,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 4,
                  cursor: "pointer",
                }}
              >
                ✕
              </button>
            </div>
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
