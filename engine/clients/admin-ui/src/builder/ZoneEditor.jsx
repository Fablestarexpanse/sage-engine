import { useCallback, useEffect, useMemo, useRef, useState, forwardRef, useImperativeHandle } from "react";
import yaml from "js-yaml";
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
  getNodesBounds,
  getViewportForBounds,
} from "@xyflow/react";
import { toPng } from "html-to-image";
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

const CONFLICT_MSG =
  "Room changed on disk since the graph was loaded (edited in WorldForge or another tab?). The graph has been reloaded — redo the change.";

const errDetail = (e) =>
  e.response?.status === 409 ? CONFLICT_MSG : e.response?.data?.detail || e.message;

function ZoneEditorInner({ zoneId, onSync, forwardedRef, navigateRoomSlug, onNavigateRoomDone }) {
  const { colors: COLORS } = useAdminTheme();
  const rf = useReactFlow();
  const panelDirtyRef = useRef(false);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("graph");
  const [tableRows, setTableRows] = useState([]);
  const [issues, setIssues] = useState([]);
  const [loadErr, setLoadErr] = useState("");
  const [syncMsg, setSyncMsg] = useState("");
  const [extExits, setExtExits] = useState([]);
  const [graphFind, setGraphFind] = useState("");
  const [describeProgress, setDescribeProgress] = useState(null);

  const neighborSlugs = nodes.map((n) => n.data?.slug).filter(Boolean);
  const selectedRoomCount = useMemo(() => nodes.filter((n) => n.selected).length, [nodes]);

  const loadGraph = useCallback(
    async (opts) => {
      const keepSlug = opts?.keepSlug;
      if (!zoneId) return;
      setLoadErr("");
      try {
        const { data } = await axios.get(`${API_BASE}/content/zones/${zoneId}/graph`);
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
    [zoneId, setNodes, setEdges, COLORS]
  );

  const savePositions = useCallback(async () => {
    const positions = {};
    rf.getNodes().forEach((n) => {
      if (n.data?.slug) positions[n.data.slug] = { x: n.position.x, y: n.position.y };
    });
    try {
      await axios.put(`${API_BASE}/content/zones/${zoneId}/positions`, { positions });
      setSyncMsg("Positions saved ✓");
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    }
  }, [rf, zoneId]);

  useImperativeHandle(
    forwardedRef,
    () => ({
      savePositions,
      hasUnsavedChanges: () => panelDirtyRef.current,
    }),
    [savePositions]
  );

  useEffect(() => {
    if (!zoneId) return;
    if (navigateRoomSlug) return;
    loadGraph();
  }, [zoneId, loadGraph, navigateRoomSlug]);

  useEffect(() => {
    if (!zoneId || !navigateRoomSlug) return;
    let cancelled = false;
    (async () => {
      await loadGraph({ keepSlug: navigateRoomSlug });
      if (cancelled) return;
      requestAnimationFrame(() => {
        const n = rf.getNodes().find((nd) => nd.data?.slug === navigateRoomSlug);
        if (n) {
          setSelected(n);
          try {
            rf.fitView({ nodes: [n], duration: 450, padding: 0.35, maxZoom: 1.35 });
          } catch {
            /* ignore */
          }
        }
        onNavigateRoomDone?.();
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [zoneId, navigateRoomSlug, loadGraph, rf, onNavigateRoomDone]);

  useEffect(() => {
    if (!zoneId || tab !== "table") return;
    axios
      .get(`${API_BASE}/content/zones/${zoneId}/rooms`)
      .then((r) => setTableRows(r.data))
      .catch(() => setTableRows([]));
  }, [zoneId, tab]);

  const onConnect = useCallback(
    async (p) => {
      const ns = rf.getNodes();
      const sourceNode = ns.find((n) => n.id === p.source);
      const targetNode = ns.find((n) => n.id === p.target);
      if (!sourceNode || !targetNode || !p.sourceHandle) return;
      const raw = { ...(sourceNode.data.raw || {}) };
      const exits = { ...(raw.exits || {}) };
      exits[p.sourceHandle] = {
        destination: targetNode.data.roomId,
        description: "",
      };
      raw.exits = exits;
      try {
        await axios.put(`${API_BASE}/content/zones/${zoneId}/rooms/${sourceNode.data.slug}`, {
          room: raw,
          expected_mtime: sourceNode.data?.mtime ?? null,
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
        window.alert(errDetail(e));
        if (e.response?.status === 409) await loadGraph({ keepSlug: sourceNode.data?.slug });
      }
    },
    [rf, zoneId, setEdges, loadGraph, onSync, COLORS]
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

  const exportPng = async () => {
    // Render the whole graph (not just the visible viewport) to a PNG download.
    const nodes = rf.getNodes();
    if (!nodes.length) return;
    const bounds = getNodesBounds(nodes);
    const pad = 60;
    const width = Math.min(8192, Math.ceil(bounds.width + pad * 2));
    const height = Math.min(8192, Math.ceil(bounds.height + pad * 2));
    const viewport = getViewportForBounds(bounds, width, height, 0.1, 2, pad);
    const el = document.querySelector(".react-flow__viewport");
    if (!el) return;
    try {
      const dataUrl = await toPng(el, {
        width,
        height,
        backgroundColor: COLORS.bgPanel || "#101014",
        style: {
          width: `${width}px`,
          height: `${height}px`,
          transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
        },
        filter: (node) => !node?.classList?.contains("react-flow__minimap"),
      });
      const a = document.createElement("a");
      a.download = `${zoneId || "zone"}-map.png`;
      a.href = dataUrl;
      a.click();
    } catch (e) {
      console.error("PNG export failed", e);
      window.alert(`PNG export failed: ${e?.message || e}`);
    }
  };

  const focusRoomBySearch = () => {
    const q = graphFind.trim().toLowerCase();
    if (!q) return;
    const n = rf.getNodes().find(
      (nd) =>
        String(nd.data?.slug || "")
          .toLowerCase()
          .includes(q) ||
        String(nd.data?.label || "")
          .toLowerCase()
          .includes(q)
    );
    if (n) {
      setSelected(n);
      try {
        rf.fitView({ nodes: [n], duration: 400, padding: 0.35, maxZoom: 1.35 });
      } catch {
        /* ignore */
      }
    } else {
      window.alert("No room matches that substring.");
    }
  };

  const addRoom = () => {
    const slug = window.prompt("New room slug (e.g. alcove_02):", "");
    if (!slug || !/^[a-zA-Z0-9_-]+$/.test(slug)) return;
    axios
      .post(`${API_BASE}/content/zones/${zoneId}/rooms`, { slug, room: {} })
      .then(() => {
        loadGraph();
        setSyncMsg("Room created ✓");
        onSync?.();
      })
      .catch((e) => window.alert(e.response?.data?.detail || e.message));
  };

  const onNodesDelete = useCallback(
    async (deleted) => {
      const slugs = deleted.map((n) => n.data?.slug).filter(Boolean);
      const mtimeBySlug = Object.fromEntries(
        deleted.filter((n) => n.data?.slug).map((n) => [n.data.slug, n.data?.mtime ?? null])
      );
      if (!slugs.length) return;
      // react-flow already removed the nodes locally; on cancel, reload restores them.
      const label = slugs.length === 1 ? `room "${slugs[0]}"` : `${slugs.length} rooms (${slugs.join(", ")})`;
      if (!window.confirm(`Delete ${label}? This removes the YAML file(s) and cannot be undone.`)) {
        await loadGraph();
        return;
      }
      for (const s of slugs) {
        try {
          await axios.delete(`${API_BASE}/content/zones/${zoneId}/rooms/${s}`, {
            params: mtimeBySlug[s] != null ? { expected_mtime: mtimeBySlug[s] } : {},
          });
        } catch (e) {
          window.alert(errDetail(e));
        }
      }
      await loadGraph();
      setSelected(null);
      onSync?.();
    },
    [zoneId, loadGraph, onSync]
  );

  const onEdgesDelete = useCallback(
    async (deletedEdges) => {
      if (!deletedEdges.length) return;
      const what =
        deletedEdges.length === 1
          ? `the "${deletedEdges[0].data?.direction ?? deletedEdges[0].sourceHandle ?? "?"}" exit`
          : `${deletedEdges.length} exits`;
      if (!window.confirm(`Remove ${what} from the room YAML?`)) {
        await loadGraph();
        return;
      }
      for (const edge of deletedEdges) {
        const dirHint = edge.data?.direction ?? edge.sourceHandle;
        if (!dirHint) {
          window.alert("Cannot determine exit direction — remove it manually in the Exits tab.");
          continue;
        }
        const ns = rf.getNodes();
        const sourceNode = ns.find((n) => n.id === edge.source);
        const slug = sourceNode?.data?.slug;
        if (!slug) continue;
        const raw = { ...(sourceNode.data.raw || {}) };
        const exits = { ...(raw.exits && typeof raw.exits === "object" ? raw.exits : {}) };
        const keys = Object.keys(exits);
        const match = keys.find((k) => k.toLowerCase() === String(dirHint).toLowerCase());
        if (!match) {
          window.alert("Cannot determine exit direction — remove it manually in the Exits tab.");
          continue;
        }
        delete exits[match];
        raw.exits = exits;
        try {
          await axios.put(`${API_BASE}/content/zones/${zoneId}/rooms/${slug}`, {
            room: raw,
            expected_mtime: sourceNode.data?.mtime ?? null,
          });
          await loadGraph({ keepSlug: slug });
          setSyncMsg("Exit removed ✓");
          onSync?.();
        } catch (e) {
          window.alert(errDetail(e));
          if (e.response?.status === 409) await loadGraph({ keepSlug: slug });
        }
      }
    },
    [rf, zoneId, loadGraph, onSync]
  );

  const duplicateRoom = useCallback(async () => {
    const sel = rf.getNodes().filter((n) => n.selected);
    if (sel.length !== 1) return;
    const src = sel[0];
    const s = src.data?.slug;
    if (!s) return;
    const suggested = `${s}_copy`;
    const input = window.prompt("New room slug:", suggested);
    if (input === null) return;
    const newSlug = String(input).trim();
    if (!newSlug || !/^[a-zA-Z0-9_-]+$/.test(newSlug)) return;
    let cloned;
    try {
      cloned = JSON.parse(JSON.stringify(src.data.raw || {}));
    } catch {
      window.alert("Could not copy room data.");
      return;
    }
    cloned.exits = {};
    cloned.id = `${zoneId}:${newSlug}`;
    cloned.zone = zoneId;
    try {
      await axios.post(`${API_BASE}/content/zones/${zoneId}/rooms`, { slug: newSlug, room: cloned });
      await loadGraph({ keepSlug: newSlug });
      setSyncMsg("Room duplicated ✓");
      onSync?.();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    }
  }, [rf, zoneId, loadGraph, onSync]);

  const runAiDescribeAll = useCallback(async () => {
    const targets = rf.getNodes().filter((n) => n.data?.hasDescription === false);
    if (!targets.length) {
      window.alert("No rooms with missing descriptions.");
      return;
    }
    if (
      !window.confirm(
        `Generate AI descriptions for ${targets.length} rooms with missing descriptions? This will overwrite blank descriptions.`
      )
    ) {
      return;
    }
    let done = 0;
    const total = targets.length;
    setDescribeProgress({ cur: 0, total });
    try {
      for (let i = 0; i < targets.length; i++) {
        const n = targets[i];
        const slug = n.data?.slug;
        if (!slug) continue;
        setDescribeProgress({ cur: i + 1, total });
        const { data: ywrap } = await axios.get(`${API_BASE}/content/room/${zoneId}/${slug}/yaml`);
        const disk = yaml.load(ywrap.yaml || "{}");
        if (typeof disk !== "object" || !disk) continue;
        const type = disk.type || "chamber";
        const depth = Number(disk.depth) || 1;
        const tags = Array.isArray(disk.tags) ? disk.tags.join(", ") : "";
        const featureNames = Array.isArray(disk.features)
          ? disk.features
              .map((f) => (typeof f === "object" && f ? f.name || f.id : ""))
              .filter(Boolean)
              .join(", ")
          : "";
        const seed = `Write a base description for a ${type} room (depth ${depth}) in zone ${zoneId}. Tags: ${tags}. Features: ${featureNames}.`;
        const { data: forge } = await axios.post(`${API_BASE}/forge/generate-content`, {
          category: "room",
          seed,
          context: { room_type: type, depth },
        });
        let gen = forge.data;
        if (!gen || typeof gen !== "object") {
          try {
            gen = yaml.load(forge.yaml || "");
          } catch {
            gen = null;
          }
        }
        let base =
          gen && typeof gen === "object"
            ? gen.description?.base ?? (typeof gen.description === "string" ? gen.description : null)
            : null;
        if (typeof base === "string" && base.trim()) {
          const prevDesc = disk.description;
          const merged = {
            ...disk,
            description:
              typeof prevDesc === "object" && prevDesc
                ? { ...prevDesc, base: base.trim() }
                : { base: base.trim() },
          };
          await axios.put(`${API_BASE}/content/zones/${zoneId}/rooms/${slug}`, {
            room: merged,
            expected_mtime: ywrap.mtime ?? null,
          });
          done += 1;
        }
      }
      await loadGraph();
      setSyncMsg(`Described ${done} rooms ✓`);
      onSync?.();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    } finally {
      setDescribeProgress(null);
    }
  }, [rf, zoneId, loadGraph, onSync]);

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

  if (!zoneId) {
    return <div style={{ color: COLORS.textMuted, padding: 16 }}>Pick a zone from the breadcrumb or surface view.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%", minHeight: 480 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <button type="button" style={{ ...btn, background: tab === "graph" ? COLORS.accentGlow : COLORS.bgCard }} onClick={() => setTab("graph")}>
          Graph
        </button>
        <button type="button" style={{ ...btn, background: tab === "table" ? COLORS.accentGlow : COLORS.bgCard }} onClick={() => setTab("table")}>
          Table
        </button>
        {syncMsg && (
          <span style={{ fontSize: 11, color: COLORS.success, fontFamily: "'JetBrains Mono', monospace" }}>{syncMsg}</span>
        )}
      </div>

      {loadErr && <div style={{ color: COLORS.danger, fontSize: 12 }}>{loadErr}</div>}

      {tab === "table" && (
        <div
          style={{
            background: COLORS.bgCard,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 8,
            padding: 12,
            fontSize: 12,
            color: COLORS.textMuted,
            fontFamily: "'JetBrains Mono', monospace",
            maxHeight: 400,
            overflow: "auto",
          }}
        >
          {(tableRows || []).map((r) => (
            <div key={r.id} style={{ padding: "4px 0", borderBottom: `1px solid ${COLORS.border}` }}>
              {r.id} · {r.type} · exits {String(r.exits || [])}
            </div>
          ))}
        </div>
      )}

      {tab === "graph" && (
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
              onNodesDelete={onNodesDelete}
              onEdgesDelete={onEdgesDelete}
              fitView
              connectionMode={ConnectionMode.Loose}
              deleteKeyCode={["Backspace", "Delete"]}
            >
              <Background color={COLORS.border} gap={22} />
              <Controls />
              <MiniMap pannable zoomable />
              <Panel position="top-left">
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, background: COLORS.bgPanel, padding: 8, borderRadius: 8, border: `1px solid ${COLORS.border}`, alignItems: "center" }}>
                  {describeProgress && (
                    <span style={{ fontSize: 10, color: COLORS.warning, fontFamily: "'JetBrains Mono', monospace", width: "100%" }}>
                      Describing rooms… {describeProgress.cur}/{describeProgress.total}
                    </span>
                  )}
                  <input
                    type="search"
                    placeholder="Find room…"
                    value={graphFind}
                    onChange={(e) => setGraphFind(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && focusRoomBySearch()}
                    style={{
                      width: 120,
                      padding: "5px 8px",
                      fontSize: 11,
                      borderRadius: 6,
                      border: `1px solid ${COLORS.border}`,
                      background: COLORS.bgInput,
                      color: COLORS.text,
                    }}
                  />
                  <button type="button" style={btn} onClick={focusRoomBySearch}>
                    Go
                  </button>
                  <button type="button" style={btn} onClick={savePositions}>
                    Save positions
                  </button>
                  <button type="button" style={btn} onClick={runLayout}>
                    Auto layout
                  </button>
                  <button type="button" style={btn} onClick={validate}>
                    Validate
                  </button>
                  <button type="button" style={btn} onClick={addRoom}>
                    Add room
                  </button>
                  <button type="button" style={btn} onClick={duplicateRoom} disabled={selectedRoomCount !== 1}>
                    Duplicate
                  </button>
                  <button type="button" style={btn} onClick={runAiDescribeAll} disabled={!!describeProgress}>
                    AI Describe All
                  </button>
                  <button type="button" style={btn} onClick={() => loadGraph()}>
                    Reload
                  </button>
                  <button type="button" style={btn} onClick={exportPng}>
                    Export PNG
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
              zoneId={zoneId}
              mode="zone"
              node={selected}
              neighborSlugs={neighborSlugs}
              onDirtyChange={(d) => {
                panelDirtyRef.current = d;
              }}
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
              onDeleted={() => {
                setSelected(null);
                loadGraph();
                onSync?.();
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

const ZoneEditor = forwardRef(function ZoneEditor(props, ref) {
  return (
    <ReactFlowProvider>
      <ZoneEditorInner {...props} forwardedRef={ref} />
    </ReactFlowProvider>
  );
});

export default ZoneEditor;
