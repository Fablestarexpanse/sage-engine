import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { deepClone } from "../utils/clone.js";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  useReactFlow,
  ReactFlowProvider,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useTheme } from "../ThemeContext.jsx";
import SystemNode from "../nodes/SystemNode.jsx";
import ConnectionEdge from "../edges/ConnectionEdge.jsx";
import SystemPanel from "../panels/SystemPanel.jsx";
import { layoutGraph } from "../utils/autoLayout.js";
import { useContent } from "../hooks/useContentStore.js";

const nodeTypes = { system: SystemNode };
const edgeTypes = { connection: ConnectionEdge };

function Inner({ worldRoot }) {
  const { colors: COLORS, colorScheme } = useTheme();
  const tb = useMemo(
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
  const rf = useReactFlow();
  const { systems, systemIds, galaxy, dispatch, saveSystem: saveSystemAction, saveGalaxy: saveGalaxyAction } = useContent();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);

  const rebuild = useCallback(() => {
    const ns = [];
    const es = [];
    const seen = new Set();
    for (const sid of systemIds) {
      const doc = systems[sid];
      const sys = doc?.system || doc || {};
      const c = sys.coordinates || { x: 0, y: 0 };
      ns.push({
        id: sid,
        type: "system",
        position: { x: Number(c.x) * 12 || 0, y: Number(c.y) * 12 || 0 },
        data: {
          label: sys.name || sid,
          starType: sys.star?.type || "?",
          faction: sys.faction || "?",
          security: sys.security || "?",
        },
      });
      for (const conn of sys.connections || []) {
        const tgt = conn.target || conn.system || conn.id;
        if (!tgt || seen.has(`${sid}->${tgt}`)) continue;
        seen.add(`${sid}->${tgt}`);
        es.push({
          id: `${sid}|${tgt}`,
          source: sid,
          target: tgt,
          type: "connection",
          markerEnd: { type: MarkerType.ArrowClosed, color: COLORS.cyan, width: 16, height: 16 },
          data: { label: conn.type || "" },
        });
      }
    }
    setNodes(ns);
    setEdges(es);
  }, [systems, systemIds, setNodes, setEdges, COLORS]);

  useEffect(() => {
    rebuild();
  }, [rebuild]);

  // Reset the draft when selection changes; on live-watch store refreshes,
  // never clobber in-progress (dirty) edits.
  const lastSelectedRef = useRef(null);
  useEffect(() => {
    if (!selectedId || !systems[selectedId]) return;
    const switched = lastSelectedRef.current !== selectedId;
    lastSelectedRef.current = selectedId;
    if (!switched && dirty) return;
    setDraft(deepClone(systems[selectedId]));
    setDirty(false);
  }, [selectedId, systems, dirty]);

  const saveSystem = async () => {
    if (!selectedId || !draft) return;
    try {
      await saveSystemAction(worldRoot, selectedId, draft);
    } catch (e) {
      window.alert(`Save failed: ${e}`);
      return;
    }
    setDirty(false);
  };

  const saveGalaxy = async () => {
    try {
      await saveGalaxyAction(worldRoot, galaxy);
    } catch (e) {
      window.alert(`Save failed: ${e}`);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: COLORS.bg, position: "relative" }}>
      <div style={{ padding: 8, borderBottom: `1px solid ${COLORS.border}`, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" style={tb} onClick={() => layoutGraph(rf.getNodes(), rf.getEdges()).then(setNodes)}>
          Auto Layout
        </button>
        <button type="button" style={tb} onClick={() => rf.fitView({ padding: 0.2 })}>
          Fit View
        </button>
        <button type="button" style={tb} onClick={saveGalaxy}>
          Save galaxy.yaml
        </button>
        <button type="button" style={tb} onClick={saveSystem} disabled={!selectedId}>
          Save system
        </button>
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
        <ReactFlow
          colorMode={colorScheme}
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodeClick={(_, n) => setSelectedId(n.id)}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1.5} color={COLORS.textDim} />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
      {selectedId && draft ? (
        <div style={{ position: "absolute", top: 48, right: 0, width: 340, bottom: 0, borderLeft: `1px solid ${COLORS.border}`, background: COLORS.bgPanel, zIndex: 10 }}>
          <SystemPanel
            rawDoc={draft}
            onChangeDoc={(d) => {
              setDraft(d);
              setDirty(true);
            }}
            onSave={saveSystem}
            onRevert={() => {
              setDraft(deepClone(systems[selectedId]));
              setDirty(false);
            }}
            dirty={dirty}
          />
        </div>
      ) : null}
    </div>
  );
}

export default function GalaxyEditor({ worldRoot }) {
  return (
    <ReactFlowProvider>
      <div style={{ position: "relative", height: "100%" }}>
        <Inner worldRoot={worldRoot} />
      </div>
    </ReactFlowProvider>
  );
}
