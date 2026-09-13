import { useEffect, useMemo } from "react";
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { buildZoneFlow, dedupeMutualBidirectionalEdges, mutedEdgeSetFromDoc } from "../utils/zoneGraph.js";
import { STAMP_ZONE_ID } from "../utils/stampBundle.js";
import RoomNode from "../nodes/RoomNode.jsx";
import NoteNode from "../nodes/NoteNode.jsx";
import ExitEdge from "../edges/ExitEdge.jsx";
import { useTheme } from "../ThemeContext.jsx";

const nodeTypes = { room: RoomNode, note: NoteNode };
const edgeTypes = { exit: ExitEdge };

function StampPreviewInner({ roomsMap, positionsDoc }) {
  const { colors: COLORS, colorScheme } = useTheme();
  const { nodes: n0, edges: e0 } = useMemo(() => {
    const muted = mutedEdgeSetFromDoc(positionsDoc);
    const { nodes, edges } = buildZoneFlow(STAMP_ZONE_ID, roomsMap, positionsDoc, {
      mutedEdgeSet: muted,
      colors: COLORS,
    });
    return { nodes, edges: dedupeMutualBidirectionalEdges(edges) };
  }, [roomsMap, positionsDoc, COLORS]);

  const [nodes, setNodes, onNodesChange] = useNodesState(n0);
  const [edges, setEdges, onEdgesChange] = useEdgesState(e0);

  useEffect(() => {
    const muted = mutedEdgeSetFromDoc(positionsDoc);
    const { nodes: n, edges: e } = buildZoneFlow(STAMP_ZONE_ID, roomsMap, positionsDoc, {
      mutedEdgeSet: muted,
      colors: COLORS,
    });
    setNodes(n);
    setEdges(dedupeMutualBidirectionalEdges(e));
  }, [roomsMap, positionsDoc, setNodes, setEdges, COLORS]);

  return (
    <ReactFlow
      colorMode={colorScheme}
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      panOnScroll
      zoomOnScroll
      proOptions={{ hideAttribution: true }}
      minZoom={0.2}
      maxZoom={1.5}
    >
      <Background variant={BackgroundVariant.Dots} gap={24} size={1.5} color={COLORS.textDim} />
    </ReactFlow>
  );
}

/** Read-only map-style preview for a stamp bundle (in-memory rooms + positions). */
export default function StampPreviewMini({ roomsMap, positionsDoc }) {
  const { colors: COLORS } = useTheme();
  return (
    <div
      style={{
        height: 240,
        width: "100%",
        minHeight: 180,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 8,
        overflow: "hidden",
        background: COLORS.bg,
      }}
    >
      <ReactFlowProvider>
        <StampPreviewInner roomsMap={roomsMap} positionsDoc={positionsDoc} />
      </ReactFlowProvider>
    </div>
  );
}
