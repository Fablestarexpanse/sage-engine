import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { deepClone } from "../utils/clone.js";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  ConnectionMode,
  useReactFlow,
  ReactFlowProvider,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { joinPaths } from "../utils/paths.js";
import { parsePositionsDoc, serializePositionsDoc } from "../utils/positionsDoc.js";
import { buildShipFlow } from "../utils/shipGraph.js";
import { layoutGraph } from "../utils/autoLayout.js";
import ShipRoomNode from "../nodes/ShipRoomNode.jsx";
import ExitEdge from "../edges/ExitEdge.jsx";
import RoomPanel from "../panels/RoomPanel.jsx";
import { useTheme } from "../ThemeContext.jsx";
import * as fs from "../utils/fsBridge.js";
import { useContent } from "../hooks/useContentStore.js";

const nodeTypes = { shipRoom: ShipRoomNode };
const edgeTypes = { exit: ExitEdge };

function Inner({ shipId, worldRoot, onShipId }) {
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
  const sel = useMemo(() => ({ ...tb, minWidth: 140 }), [tb]);
  const rf = useReactFlow();
  const { ships, shipIds, dispatch, saveShipDoc } = useContent();
  const layoutPath = useMemo(() => joinPaths(worldRoot, "ships", `${shipId}.layout.json`), [worldRoot, shipId]);

  const [posMap, setPosMap] = useState({});
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedLocal, setSelectedLocal] = useState(null);
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);

  const shipDoc = ships[shipId] || { ship: { id: shipId, rooms: [] } };

  const rebuild = useCallback(() => {
    const { nodes: n, edges: e } = buildShipFlow(shipId, shipDoc, { positions: posMap }, { colors: COLORS });
    setNodes(n);
    setEdges(e);
  }, [shipId, shipDoc, posMap, setNodes, setEdges, COLORS]);

  useEffect(() => {
    let c = false;
    (async () => {
      try {
        if (await fs.pathExists(layoutPath)) {
          const raw = JSON.parse(await fs.readText(layoutPath));
          if (!c) setPosMap(parsePositionsDoc(raw).positions || {});
        } else if (!c) setPosMap({});
      } catch {
        if (!c) setPosMap({});
      }
    })();
    return () => {
      c = true;
    };
  }, [layoutPath, shipId]);

  useEffect(() => {
    rebuild();
  }, [rebuild]);

  // Reset the draft when selection changes; on live-watch store refreshes,
  // never clobber in-progress (dirty) edits.
  const lastSelectedRef = useRef(null);
  useEffect(() => {
    if (!selectedLocal) return;
    const switched = lastSelectedRef.current !== selectedLocal;
    lastSelectedRef.current = selectedLocal;
    if (!switched && dirty) return;
    const r = (shipDoc.ship?.rooms || []).find((x) => x.id === selectedLocal);
    setDraft(r ? deepClone(r) : { id: selectedLocal, name: selectedLocal, type: "corridor", description: { base: "" }, exits: {} });
    setDirty(false);
  }, [selectedLocal, shipDoc, dirty]);

  const saveShip = async (doc) => {
    await saveShipDoc(worldRoot, shipId, doc);
  };

  const saveLayout = async () => {
    const pos = { ...posMap };
    for (const n of rf.getNodes()) {
      if (n.type === "shipRoom") pos[n.data.slug] = { x: n.position.x, y: n.position.y };
    }
    const doc = { version: 2, positions: pos, notes: [], muted_edges: [] };
    setPosMap(pos);
    await fs.writeText(layoutPath, serializePositionsDoc(doc));
  };

  const roomIndexForPicker = useMemo(() => {
    const rooms = shipDoc.ship?.rooms || [];
    const map = { [shipId]: {} };
    for (const r of rooms) {
      map[shipId][r.id] = { id: `ship:${shipId}:${r.id}` };
    }
    return map;
  }, [shipDoc, shipId]);

  if (!shipId) return <div style={{ padding: 24, color: COLORS.textMuted }}>No ship selected.</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: COLORS.bg, position: "relative" }}>
      <div style={{ padding: 8, borderBottom: `1px solid ${COLORS.border}`, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <select value={shipId} onChange={(e) => onShipId(e.target.value)} style={sel}>
          {shipIds.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button type="button" style={tb} onClick={() => layoutGraph(rf.getNodes(), rf.getEdges()).then(setNodes)}>
          Auto Layout
        </button>
        <button type="button" style={tb} onClick={() => rf.fitView({ padding: 0.2 })}>
          Fit View
        </button>
        <button type="button" style={tb} onClick={saveLayout}>
          Save layout
        </button>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ReactFlow
          colorMode={colorScheme}
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          connectionMode={ConnectionMode.Loose}
          onNodeClick={(_, n) => {
            if (n.type === "shipRoom") setSelectedLocal(n.data.slug);
          }}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1.5} color={COLORS.textDim} />
          <Controls />
        </ReactFlow>
      </div>
      {selectedLocal && draft ? (
        <div style={{ position: "absolute", top: 48, right: 0, width: 360, bottom: 0, borderLeft: `1px solid ${COLORS.border}`, background: COLORS.bgPanel, zIndex: 10 }}>
          <RoomPanel
            worldRoot={worldRoot}
            zoneId={shipId}
            roomSlug={selectedLocal}
            room={{
              ...draft,
              zone: shipId,
              id: `ship:${shipId}:${draft.id}`,
            }}
            groups={[]}
            onChangeRoom={(d) => {
              const { zone: _z, id: _i, ...rest } = d;
              setDraft(rest);
              setDirty(true);
            }}
            onSave={async () => {
              const rooms = [...(shipDoc.ship?.rooms || [])];
              const idx = rooms.findIndex((r) => r.id === selectedLocal);
              const entry = { ...draft, id: selectedLocal };
              if (idx >= 0) rooms[idx] = entry;
              else rooms.push(entry);
              const next = deepClone(shipDoc);
              next.ship = next.ship || {};
              next.ship.rooms = rooms;
              await saveShip(next);
              setDirty(false);
            }}
            onRevert={() => {
              const r = (shipDoc.ship?.rooms || []).find((x) => x.id === selectedLocal);
              setDraft(r ? deepClone(r) : null);
              setDirty(false);
            }}
            dirty={dirty}
            roomIndexForPicker={roomIndexForPicker}
            shipMode
          />
        </div>
      ) : null}
    </div>
  );
}

export default function ShipEditor({ shipId, worldRoot, onShipId }) {
  return (
    <ReactFlowProvider>
      <Inner shipId={shipId} worldRoot={worldRoot} onShipId={onShipId} />
    </ReactFlowProvider>
  );
}
