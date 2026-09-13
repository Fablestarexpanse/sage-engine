import { useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  addEdge,
  ConnectionMode,
  MarkerType,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import axios from "axios";
import RoomNode from "./RoomNode.jsx";
import ExitEdge from "./ExitEdge.jsx";
import { layoutGraph } from "./AutoLayout.js";
import ValidationPanel, { runZoneValidation } from "./ValidationPanel.jsx";
import RoomPropertyPanel from "./RoomPropertyPanel.jsx";
import { API_BASE } from "./builderConstants.js";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import "./builder.css";

const nodeTypes = { room: RoomNode };
const edgeTypes = { exit: ExitEdge };

function ShipEditorInner({ shipId, onSync }) {
  const { colors: COLORS } = useAdminTheme();
  const rf = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selected, setSelected] = useState(null);
  const [issues, setIssues] = useState([]);
  const [loadErr, setLoadErr] = useState("");
  const [syncMsg, setSyncMsg] = useState("");
  const [extExits, setExtExits] = useState([]);

  const neighborSlugs = nodes.map((n) => n.data?.slug).filter(Boolean);

  const loadGraph = useCallback(
    async (opts) => {
      const keepSlug = opts?.keepSlug;
      if (!shipId) return;
      setLoadErr("");
      try {
        const { data } = await axios.get(`${API_BASE}/content/ships/${encodeURIComponent(shipId)}/graph`);
        const n = (data.nodes || []).map((x) => ({ ...x, type: "room" }));
        const e = (data.edges || []).map((x) => ({
          ...x,
          type: "exit",
          markerEnd: { type: MarkerType.ArrowClosed, color: COLORS.borderActive, width: 18, height: 18 },
        }));
        setNodes(n);
        setEdges(e);
        setExtExits(data.external_exits || []);
        setIssues(runZoneValidation(n, e, data.external_exits || []));
        if (keepSlug) {
          const found = n.find((node) => node.data?.slug === keepSlug);
          setSelected(found || null);
        }
      } catch (e) {
        setLoadErr(String(e.response?.data?.detail || e.message));
      }
    },
    [shipId, setNodes, setEdges, COLORS]
  );

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  const onConnect = useCallback(
    async (p) => {
      const ns = rf.getNodes();
      const sourceNode = ns.find((n) => n.id === p.source);
      const targetNode = ns.find((n) => n.id === p.target);
      if (!sourceNode || !targetNode || !p.sourceHandle) return;
      const raw = { ...(sourceNode.data.raw || {}) };
      const exits = { ...(raw.exits || {}) };
      const destSlug = targetNode.data.slug;
      exits[p.sourceHandle] = {
        destination: `self:${destSlug}`,
        description: "",
      };
      raw.exits = exits;
      try {
        await axios.put(`${API_BASE}/content/ships/${encodeURIComponent(shipId)}/rooms/${encodeURIComponent(sourceNode.data.slug)}`, {
          room: raw,
        });
        setEdges((eds) =>
          addEdge(
            {
              ...p,
              type: "exit",
              markerEnd: { type: MarkerType.ArrowClosed, color: COLORS.borderActive, width: 18, height: 18 },
              data: { direction: p.sourceHandle },
            },
            eds
          )
        );
        await loadGraph({ keepSlug: sourceNode.data?.slug });
        setSyncMsg("Synced ✓");
        onSync?.();
      } catch (e) {
        window.alert(e.response?.data?.detail || e.message);
      }
    },
    [rf, shipId, setEdges, loadGraph, onSync, COLORS]
  );

  const runLayout = async () => {
    const ns = rf.getNodes();
    const es = rf.getEdges();
    const laid = await layoutGraph(ns, es, "layered");
    setNodes(laid);
  };

  const validate = () => {
    setIssues(runZoneValidation(rf.getNodes(), rf.getEdges(), extExits));
  };

  const btn = {
    padding: "6px 10px",
    fontSize: 11,
    fontWeight: 600,
    borderRadius: 6,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgCard,
    color: COLORS.text,
    cursor: "pointer",
    fontFamily: "'DM Sans', sans-serif",
  };

  if (!shipId) {
    return <div style={{ color: COLORS.textMuted, padding: 16 }}>Pick a ship from the system view or tab.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%", minHeight: 480 }}>
      <div style={{ fontSize: 12, color: COLORS.textMuted }}>
        Ship interior graph. Positions are not persisted (grid layout from content). Exits use <code style={{ color: COLORS.textDim }}>self:room_id</code> for in-ship links.
      </div>
      {loadErr && <div style={{ color: COLORS.danger, fontSize: 12 }}>{loadErr}</div>}
      {syncMsg && <div style={{ fontSize: 11, color: COLORS.success, fontFamily: "'JetBrains Mono', monospace" }}>{syncMsg}</div>}

      <div style={{ display: "flex", flex: 1, gap: 12, minHeight: 420 }}>
        <div
          className="world-builder-flow"
          style={{
            flex: 1,
            position: "relative",
            borderRadius: 10,
            border: `1px solid ${COLORS.border}`,
            minHeight: 400,
          }}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodeDoubleClick={(_, n) => setSelected(n)}
            onSelectionChange={({ nodes: ns }) => setSelected(ns[0] || null)}
            fitView
            connectionMode={ConnectionMode.Loose}
          >
            <Background color={COLORS.border} gap={22} />
            <Controls />
            <MiniMap pannable zoomable />
            <Panel position="top-left">
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 6,
                  background: COLORS.bgPanel,
                  padding: 8,
                  borderRadius: 8,
                  border: `1px solid ${COLORS.border}`,
                }}
              >
                <button type="button" style={btn} onClick={runLayout}>
                  Auto layout
                </button>
                <button type="button" style={btn} onClick={validate}>
                  Validate
                </button>
                <button type="button" style={btn} onClick={() => loadGraph()}>
                  Reload
                </button>
              </div>
            </Panel>
          </ReactFlow>
        </div>
        <div
          style={{
            width: 328,
            flexShrink: 0,
            background: COLORS.bgCard,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 10,
            padding: 12,
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: "uppercase" }}>Validation</div>
          <ValidationPanel issues={issues} />
          <div style={{ fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: "uppercase", marginTop: 8 }}>Properties</div>
          <RoomPropertyPanel
            mode="ship"
            shipId={shipId}
            node={selected}
            neighborSlugs={neighborSlugs}
            onSaved={() => {
              const s = selected?.data?.slug;
              loadGraph({ keepSlug: s });
              setSyncMsg("Synced ✓");
              onSync?.();
            }}
            onRevertRequest={() => {
              const s = selected?.data?.slug;
              loadGraph({ keepSlug: s });
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default function ShipEditor(props) {
  return (
    <ReactFlowProvider>
      <ShipEditorInner {...props} />
    </ReactFlowProvider>
  );
}
