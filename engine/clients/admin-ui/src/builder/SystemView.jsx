import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import yaml from "js-yaml";
import { API_BASE } from "./builderConstants.js";
import { useAdminTheme } from "../AdminThemeContext.jsx";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "connections", label: "Connections" },
  { id: "bodies", label: "Bodies" },
  { id: "ships", label: "Ships" },
  { id: "yaml", label: "YAML" },
];

function hashAngle(seed) {
  const s = String(seed ?? "");
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 997;
  return (h / 997) * Math.PI * 2;
}

function cloneDoc(obj) {
  return JSON.parse(JSON.stringify(obj || {}));
}

function normalizeDoc(detail) {
  const raw = detail.raw;
  if (raw && typeof raw === "object" && raw.system && typeof raw.system === "object") {
    return cloneDoc(raw);
  }
  return {
    system: {
      id: detail.id,
      name: detail.name,
      coordinates: detail.coordinates || { x: 0, y: 0, z: 0 },
      star: detail.star || {},
      faction: detail.faction,
      security: detail.security,
      connections: detail.connections || [],
      bodies: detail.bodies || [],
    },
  };
}

function connTarget(c) {
  if (typeof c === "string") return c;
  return c?.target || "";
}

function connType(c) {
  if (typeof c === "string") return "jump_gate";
  return c?.type || "jump_gate";
}

function OrbitalSchematic({ detail, onSelectZone }) {
  const { colors: COLORS } = useAdminTheme();
  const bodies = detail.bodies || [];
  const hasHints = bodies.some((b) => b.orbit != null || b.orbits);
  if (!bodies.length || !hasHints) return null;

  const cx = 450;
  const cy = 260;
  const roots = bodies.filter((b) => !b.orbits);
  const orbitRadii = [...new Set(roots.map((b, idx) => (typeof b.orbit === "number" ? 52 + b.orbit * 62 : 88 + idx * 52)))];

  const placed = {};
  roots.forEach((b, idx) => {
    const orbitR = typeof b.orbit === "number" ? 52 + b.orbit * 62 : 88 + idx * 52;
    const key = b.id || b.name || `b${idx}`;
    const ang = hashAngle(key) + idx * 0.35;
    placed[key] = {
      x: cx + Math.cos(ang) * orbitR,
      y: cy + Math.sin(ang) * orbitR * 0.58,
      b,
    };
  });

  bodies.forEach((b) => {
    if (!b.orbits) return;
    const pk = b.orbits;
    const parent = placed[pk];
    if (!parent) return;
    const key = b.id || b.name;
    if (placed[key]) return;
    const ang = hashAngle(`${key}sat`) + 0.9;
    const mr = 36;
    placed[key] = {
      x: parent.x + Math.cos(ang) * mr,
      y: parent.y + Math.sin(ang) * mr,
      b,
    };
  });

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: "uppercase", marginBottom: 8 }}>Orbital map</div>
      <svg
        width="100%"
        height={360}
        viewBox="0 0 900 520"
        style={{ background: COLORS.bg, borderRadius: 10, border: `1px solid ${COLORS.border}`, display: "block" }}
      >
        {orbitRadii.map((r) => (
          <circle key={r} cx={cx} cy={cy} r={r} fill="none" stroke={COLORS.border} strokeWidth="0.5" strokeDasharray="3 5" opacity={0.4} />
        ))}
        <circle cx={cx} cy={cy} r={26} fill={`${COLORS.warning}22`} stroke={COLORS.warning} strokeWidth={1} />
        <text x={cx} y={cy + 48} textAnchor="middle" fontSize={11} fontFamily="'Space Grotesk', sans-serif" fill={COLORS.text} fontWeight={600}>
          {detail.star?.name || detail.name}
        </text>
        {Object.entries(placed).map(([key, p]) => {
          const b = p.b;
          const zones = b.zones || [];
          const r = 12;
          const col = b.type === "station" ? COLORS.success : COLORS.info;
          return (
            <g key={key}>
              <circle
                cx={p.x}
                cy={p.y}
                r={r + (zones.length ? 3 : 0)}
                fill="none"
                stroke={zones.length ? COLORS.accent : "transparent"}
                strokeWidth={1}
                opacity={0.6}
              />
              <circle
                cx={p.x}
                cy={p.y}
                r={r}
                fill={`${col}30`}
                stroke={col}
                strokeWidth={1.2}
                style={{ cursor: zones.length ? "pointer" : "default" }}
                onClick={() => {
                  if (zones.length === 1) {
                    const z = zones[0];
                    const ref = typeof z === "string" ? z : z.zone_ref;
                    if (ref) onSelectZone(ref);
                  }
                }}
              />
              <text x={p.x} y={p.y + r + 14} textAnchor="middle" fontSize={10} fontFamily="'Space Grotesk', sans-serif" fill={COLORS.textMuted}>
                {b.name || b.id}
              </text>
            </g>
          );
        })}
      </svg>
      <div style={{ fontSize: 10, color: COLORS.textDim, marginTop: 6 }}>Bodies with one zone open it on click; use the list below for multiple zones.</div>
    </div>
  );
}

function errDetail(e) {
  const d = e?.response?.data?.detail;
  if (d == null) return e?.message || String(e);
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  return JSON.stringify(d);
}

function tabStyle(active, C) {
  return {
    padding: "8px 14px",
    fontSize: 12,
    fontWeight: 600,
    border: "none",
    borderBottom: active ? `2px solid ${C.accent}` : "2px solid transparent",
    marginBottom: -1,
    background: "transparent",
    color: active ? C.accent : C.textMuted,
    cursor: "pointer",
    fontFamily: "'DM Sans', sans-serif",
  };
}

export default function SystemView({ systemId, onSelectZone, onSelectShip }) {
  const { colors: COLORS } = useAdminTheme();
  const inp = {
    padding: "6px 10px",
    borderRadius: 6,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgInput,
    color: COLORS.text,
    fontSize: 12,
    fontFamily: "'DM Sans', sans-serif",
  };
  const [activeTab, setActiveTab] = useState("overview");
  const [detail, setDetail] = useState(null);
  const [doc, setDoc] = useState(null);
  const [ships, setShips] = useState([]);
  const [shipFilter, setShipFilter] = useState("");
  const [peerIds, setPeerIds] = useState([]);
  const [err, setErr] = useState("");
  const [saveMsg, setSaveMsg] = useState("");
  const [saveBusy, setSaveBusy] = useState(false);

  const [newConnTarget, setNewConnTarget] = useState("");
  const [newConnType, setNewConnType] = useState("jump_gate");

  const [bodyId, setBodyId] = useState("");
  const [bodyName, setBodyName] = useState("");
  const [bodyType, setBodyType] = useState("planet");
  const [bodyOrbit, setBodyOrbit] = useState("");
  const [bodyOrbits, setBodyOrbits] = useState("");
  const [bodyZones, setBodyZones] = useState("");

  const [shipNewId, setShipNewId] = useState("");
  const [shipNewName, setShipNewName] = useState("");
  const [shipNewSize, setShipNewSize] = useState("small");
  const [shipCreateBusy, setShipCreateBusy] = useState(false);

  const [yamlText, setYamlText] = useState("");

  const reloadSystem = useCallback(() => {
    if (!systemId) return;
    setErr("");
    axios
      .get(`${API_BASE}/content/systems/${encodeURIComponent(systemId)}`)
      .then((r) => {
        setDetail(r.data);
        setDoc(normalizeDoc(r.data));
        setSaveMsg("");
      })
      .catch((e) => {
        setDetail(null);
        setDoc(null);
        setErr(errDetail(e));
      });
  }, [systemId]);

  useEffect(() => {
    setActiveTab("overview");
  }, [systemId]);

  useEffect(() => {
    reloadSystem();
  }, [reloadSystem]);

  useEffect(() => {
    axios
      .get(`${API_BASE}/content/galaxy`)
      .then((r) => {
        const list = (r.data.systems || []).filter((s) => !s.error).map((s) => s.id);
        setPeerIds(list);
      })
      .catch(() => setPeerIds([]));
  }, []);

  const reloadShips = () => {
    axios
      .get(`${API_BASE}/content/ships`)
      .then((r) => {
        const d = r.data;
        const list = Array.isArray(d) ? d : d?.ships || [];
        setShips(list);
      })
      .catch(() => setShips([]));
  };

  useEffect(() => {
    reloadShips();
  }, []);

  const sys = doc?.system;
  const orbitDetail = useMemo(() => {
    if (!sys) return null;
    return {
      id: sys.id,
      name: sys.name,
      star: sys.star || {},
      bodies: sys.bodies || [],
    };
  }, [sys]);

  const filteredShips = useMemo(() => {
    const q = shipFilter.trim().toLowerCase();
    if (!q) return ships;
    return ships.filter(
      (s) =>
        String(s.id || "")
          .toLowerCase()
          .includes(q) ||
        String(s.name || "")
          .toLowerCase()
          .includes(q)
    );
  }, [ships, shipFilter]);

  const goTab = (id) => {
    setActiveTab(id);
    if (id === "yaml" && doc) {
      try {
        setYamlText(yaml.dump(doc, { lineWidth: 100, noRefs: true }));
      } catch {
        setYamlText("");
      }
    }
  };

  const applyYaml = () => {
    try {
      const parsed = yaml.load(yamlText);
      if (!parsed || typeof parsed !== "object" || !parsed.system || typeof parsed.system !== "object") {
        window.alert("Root must include a `system:` mapping.");
        return;
      }
      if (String(parsed.system.id || systemId) !== systemId) {
        window.alert(`system.id must match this file (${systemId}).`);
        return;
      }
      setDoc(cloneDoc(parsed));
      setSaveMsg("Applied YAML to draft — use Save to write disk.");
    } catch (e) {
      window.alert(errDetail(e));
    }
  };

  const saveSystem = async () => {
    setSaveBusy(true);
    setSaveMsg("");
    try {
      await axios.put(`${API_BASE}/content/systems/${encodeURIComponent(systemId)}`, { document: doc });
      setSaveMsg("Saved.");
      reloadSystem();
    } catch (e) {
      window.alert(errDetail(e));
    } finally {
      setSaveBusy(false);
    }
  };

  if (!systemId) {
    return <div style={{ color: COLORS.textMuted, padding: 16, fontFamily: "'DM Sans', sans-serif" }}>Select a system from the galaxy map.</div>;
  }

  if (err) {
    return <div style={{ color: COLORS.danger, padding: 16 }}>{err}</div>;
  }

  if (!detail || !doc || !sys) {
    return <div style={{ color: COLORS.textMuted, padding: 16 }}>Loading system…</div>;
  }

  const connections = sys.connections || [];
  const bodies = sys.bodies || [];
  const coords = sys.coordinates || {};
  const cx = Number(coords.x) || 0;
  const cy = Number(coords.y) || 0;
  const cz = Number(coords.z) || 0;
  const star = sys.star || {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0, fontFamily: "'DM Sans', sans-serif" }}>
      <div
        style={{
          background: COLORS.bgCard,
          border: `1px solid ${COLORS.border}`,
          borderRadius: "10px 10px 0 0",
          padding: "14px 16px",
          borderBottom: `1px solid ${COLORS.border}`,
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{sys.name}</div>
            <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 4 }}>
              {sys.id} · {sys.faction} · security {sys.security}
            </div>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <button
              type="button"
              disabled={saveBusy}
              onClick={saveSystem}
              style={{
                padding: "8px 16px",
                borderRadius: 8,
                border: "none",
                background: COLORS.accent,
                color: "#fff",
                fontWeight: 700,
                cursor: saveBusy ? "wait" : "pointer",
              }}
            >
              Save system YAML
            </button>
            {saveMsg && <span style={{ fontSize: 12, color: COLORS.success }}>{saveMsg}</span>}
            <button type="button" onClick={reloadSystem} style={{ ...inp, background: COLORS.bgPanel, cursor: "pointer" }}>
              Reload from disk
            </button>
          </div>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 0,
          padding: "0 8px",
          background: COLORS.bgCard,
          borderLeft: `1px solid ${COLORS.border}`,
          borderRight: `1px solid ${COLORS.border}`,
          borderBottom: `1px solid ${COLORS.border}`,
        }}
      >
        {TABS.map((t) => (
          <button key={t.id} type="button" style={tabStyle(activeTab === t.id, COLORS)} onClick={() => goTab(t.id)}>
            {t.label}
            {t.id === "connections" && connections.length > 0 && (
              <span style={{ marginLeft: 6, fontSize: 10, color: COLORS.textDim, fontWeight: 500 }}>({connections.length})</span>
            )}
            {t.id === "bodies" && bodies.length > 0 && (
              <span style={{ marginLeft: 6, fontSize: 10, color: COLORS.textDim, fontWeight: 500 }}>({bodies.length})</span>
            )}
          </button>
        ))}
      </div>

      <div
        style={{
          padding: 16,
          background: COLORS.bgPanel,
          border: `1px solid ${COLORS.border}`,
          borderTop: "none",
          borderRadius: "0 0 10px 10px",
          minHeight: 200,
        }}
      >
        {activeTab === "overview" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5 }}>
              Summary of this system file. Edit coordinates and star in the{" "}
              <span style={{ color: COLORS.text, fontWeight: 600 }}>YAML</span> tab, or use galaxy map placement when creating new systems.
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
              <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 12 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: COLORS.textDim, textTransform: "uppercase", marginBottom: 8 }}>Coordinates</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: COLORS.text }}>
                  x {cx} · y {cy} · z {cz}
                </div>
              </div>
              <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 12 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: COLORS.textDim, textTransform: "uppercase", marginBottom: 8 }}>Star</div>
                <div style={{ fontSize: 13, color: COLORS.text }}>{star.name || "—"}</div>
                <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>{star.type || "—"}</div>
              </div>
              <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 12 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: COLORS.textDim, textTransform: "uppercase", marginBottom: 8 }}>Content</div>
                <div style={{ fontSize: 13, color: COLORS.text }}>{connections.length} jump connections</div>
                <div style={{ fontSize: 13, color: COLORS.text, marginTop: 4 }}>{bodies.length} bodies</div>
              </div>
            </div>
            {connections.length > 0 && (
              <div style={{ fontSize: 12, color: COLORS.textDim }}>
                Linked to: {connections.map((c) => connTarget(c)).join(", ")}
              </div>
            )}
          </div>
        )}

        {activeTab === "connections" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>Jump gates and wormholes to other systems. Changes are in memory until you save.</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {connections.length === 0 && <div style={{ color: COLORS.textMuted, fontSize: 13 }}>No connections yet.</div>}
              {connections.map((c, idx) => (
                <div
                  key={`${connTarget(c)}-${idx}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    background: COLORS.bgCard,
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: 8,
                    padding: 10,
                  }}
                >
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: COLORS.text }}>{connTarget(c)}</span>
                  <span style={{ fontSize: 11, color: COLORS.textDim }}>{connType(c)}</span>
                  <button
                    type="button"
                    onClick={() => {
                      setDoc((d) => {
                        const next = cloneDoc(d);
                        const conns = [...(next.system.connections || [])];
                        conns.splice(idx, 1);
                        next.system.connections = conns;
                        return next;
                      });
                    }}
                    style={{ marginLeft: "auto", ...inp, background: "transparent", color: COLORS.danger, cursor: "pointer" }}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
              <div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Target system id</div>
                <input list="peer-systems" value={newConnTarget} onChange={(e) => setNewConnTarget(e.target.value)} placeholder="vega_reach" style={{ ...inp, width: 160 }} />
                <datalist id="peer-systems">
                  {peerIds.map((id) => (
                    <option key={id} value={id} />
                  ))}
                </datalist>
              </div>
              <div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Type</div>
                <select value={newConnType} onChange={(e) => setNewConnType(e.target.value)} style={{ ...inp }}>
                  <option value="jump_gate">jump_gate</option>
                  <option value="wormhole">wormhole</option>
                </select>
              </div>
              <button
                type="button"
                onClick={() => {
                  const t = newConnTarget.trim();
                  if (!t || !/^[a-zA-Z0-9_-]+$/.test(t)) {
                    window.alert("Enter a valid target system id.");
                    return;
                  }
                  setDoc((d) => {
                    const next = cloneDoc(d);
                    const conns = [...(next.system.connections || [])];
                    const row =
                      newConnType === "jump_gate"
                        ? { target: t, type: "jump_gate", bidirectional: true }
                        : { target: t, type: "wormhole", stability: "unstable" };
                    conns.push(row);
                    next.system.connections = conns;
                    return next;
                  });
                  setNewConnTarget("");
                }}
                style={{ padding: "8px 14px", borderRadius: 6, border: "none", background: COLORS.info, color: "#fff", fontWeight: 600, cursor: "pointer" }}
              >
                Add connection
              </button>
            </div>
          </div>
        )}

        {activeTab === "bodies" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>Planets, stations, and moons with optional zone links. Orbital diagram appears when orbit data exists.</div>
            {orbitDetail && <OrbitalSchematic detail={orbitDetail} onSelectZone={onSelectZone} />}
            {bodies.length > 0 && !bodies.some((b) => b.orbit != null || b.orbits) && (
              <div style={{ fontSize: 11, color: COLORS.textDim, fontStyle: "italic" }}>
                Add a numeric <code style={{ color: COLORS.textMuted }}>orbit</code> or an <code style={{ color: COLORS.textMuted }}>orbits</code> parent id on bodies to enable the schematic above.
              </div>
            )}
            <div style={{ fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: "uppercase" }}>Bodies & zones</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {bodies.length === 0 && <div style={{ color: COLORS.textMuted, fontSize: 13 }}>No bodies defined.</div>}
              {bodies.map((b, bidx) => {
                const zones = b.zones || [];
                return (
                  <div
                    key={b.id || b.name || bidx}
                    style={{
                      background: COLORS.bgCard,
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: 8,
                      padding: 12,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                      <div>
                        <div style={{ fontWeight: 600, color: COLORS.text }}>{b.name || b.id}</div>
                        <div style={{ fontSize: 11, color: COLORS.textMuted }}>{b.type}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setDoc((d) => {
                            const next = cloneDoc(d);
                            const list = [...(next.system.bodies || [])];
                            list.splice(bidx, 1);
                            next.system.bodies = list;
                            return next;
                          });
                        }}
                        style={{ ...inp, background: "transparent", color: COLORS.danger, cursor: "pointer", flexShrink: 0 }}
                      >
                        Remove body
                      </button>
                    </div>
                    {zones.length === 0 ? (
                      <div style={{ fontSize: 11, color: COLORS.textDim, marginTop: 6 }}>No zone_ref entries</div>
                    ) : (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                        {zones.map((z) => {
                          const ref = typeof z === "string" ? z : z.zone_ref;
                          if (!ref) return null;
                          return (
                            <button
                              key={ref}
                              type="button"
                              onClick={() => onSelectZone(ref)}
                              style={{
                                padding: "6px 10px",
                                background: COLORS.accentGlow,
                                border: `1px solid ${COLORS.borderActive}`,
                                borderRadius: 6,
                                color: COLORS.accent,
                                cursor: "pointer",
                                fontSize: 12,
                                fontWeight: 600,
                              }}
                            >
                              Zone: {ref}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <div
              style={{
                padding: 12,
                background: COLORS.bgCard,
                border: `1px dashed ${COLORS.borderActive}`,
                borderRadius: 8,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div style={{ fontSize: 11, fontWeight: 700, color: COLORS.textMuted }}>Add body</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
                <div>
                  <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Body id</div>
                  <input value={bodyId} onChange={(e) => setBodyId(e.target.value)} placeholder="new_moon" style={{ ...inp, width: 120 }} />
                </div>
                <div>
                  <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Display name</div>
                  <input value={bodyName} onChange={(e) => setBodyName(e.target.value)} placeholder="New Moon" style={{ ...inp, width: 140 }} />
                </div>
                <div>
                  <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Type</div>
                  <select value={bodyType} onChange={(e) => setBodyType(e.target.value)} style={{ ...inp }}>
                    <option value="planet">planet</option>
                    <option value="station">station</option>
                    <option value="moon">moon</option>
                    <option value="asteroid">asteroid</option>
                  </select>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Orbit (number)</div>
                  <input value={bodyOrbit} onChange={(e) => setBodyOrbit(e.target.value)} placeholder="1.0" style={{ ...inp, width: 72 }} />
                </div>
                <div>
                  <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Orbits (parent body id)</div>
                  <input value={bodyOrbits} onChange={(e) => setBodyOrbits(e.target.value)} placeholder="terra" style={{ ...inp, width: 100 }} />
                </div>
                <div style={{ flex: "1 1 200px" }}>
                  <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Zones (comma-separated zone ids)</div>
                  <input value={bodyZones} onChange={(e) => setBodyZones(e.target.value)} placeholder="my_zone, other_zone" style={{ ...inp, width: "100%" }} />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    const id = bodyId.trim();
                    if (!id || !/^[a-zA-Z0-9_-]+$/.test(id)) {
                      window.alert("Body id: letters, numbers, underscores, hyphens only.");
                      return;
                    }
                    const name = bodyName.trim() || id;
                    const row = { id, type: bodyType, name };
                    const o = parseFloat(bodyOrbit);
                    if (!Number.isNaN(o)) row.orbit = o;
                    const par = bodyOrbits.trim();
                    if (par) row.orbits = par;
                    const zparts = bodyZones
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean);
                    row.zones = zparts.map((zone_ref) => ({ zone_ref }));
                    setDoc((d) => {
                      const next = cloneDoc(d);
                      next.system.bodies = [...(next.system.bodies || []), row];
                      return next;
                    });
                    setBodyId("");
                    setBodyName("");
                    setBodyOrbit("");
                    setBodyOrbits("");
                    setBodyZones("");
                  }}
                  style={{ padding: "8px 14px", borderRadius: 6, border: "none", background: COLORS.success, color: "#0a0b0f", fontWeight: 700, cursor: "pointer" }}
                >
                  Add body
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === "ships" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>
              Global ship templates (not stored inside this system file). Open one to edit interior rooms.
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <input
                type="search"
                placeholder="Filter ships…"
                value={shipFilter}
                onChange={(e) => setShipFilter(e.target.value)}
                style={{ ...inp, flex: "1 1 180px", maxWidth: 280 }}
              />
              <button type="button" onClick={reloadShips} style={{ ...inp, background: COLORS.bgCard, cursor: "pointer" }}>
                Refresh list
              </button>
            </div>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                padding: 10,
                background: COLORS.bgCard,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 8,
                alignItems: "flex-end",
              }}
            >
              <div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>New ship id</div>
                <input value={shipNewId} onChange={(e) => setShipNewId(e.target.value)} style={{ ...inp, width: 130 }} />
              </div>
              <div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Name</div>
                <input value={shipNewName} onChange={(e) => setShipNewName(e.target.value)} style={{ ...inp, width: 140 }} />
              </div>
              <div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Size</div>
                <select value={shipNewSize} onChange={(e) => setShipNewSize(e.target.value)} style={{ ...inp }}>
                  <option value="small">small</option>
                  <option value="medium">medium</option>
                  <option value="large">large</option>
                </select>
              </div>
              <button
                type="button"
                disabled={shipCreateBusy}
                onClick={async () => {
                  const id = shipNewId.trim();
                  if (!id || !/^[a-zA-Z0-9_-]+$/.test(id)) {
                    window.alert("Ship id: letters, numbers, underscores, hyphens only.");
                    return;
                  }
                  setShipCreateBusy(true);
                  try {
                    await axios.post(`${API_BASE}/content/ships/create`, {
                      id,
                      name: shipNewName.trim() || id,
                      size: shipNewSize,
                    });
                    setShipNewId("");
                    setShipNewName("");
                    reloadShips();
                  } catch (e) {
                    window.alert(errDetail(e));
                  } finally {
                    setShipCreateBusy(false);
                  }
                }}
                style={{
                  padding: "8px 14px",
                  borderRadius: 6,
                  border: "none",
                  background: COLORS.forge,
                  color: "#fff",
                  fontWeight: 700,
                  cursor: shipCreateBusy ? "wait" : "pointer",
                }}
              >
                Create ship
              </button>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {filteredShips.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => onSelectShip(s.id, s.name)}
                  style={{
                    padding: "8px 12px",
                    background: COLORS.bgPanel,
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: 8,
                    color: COLORS.text,
                    cursor: "pointer",
                    fontSize: 12,
                  }}
                >
                  {s.name || s.id}
                </button>
              ))}
            </div>
            {ships.length > 0 && filteredShips.length === 0 && <div style={{ color: COLORS.textMuted, fontSize: 12 }}>No ships match filter.</div>}
          </div>
        )}

        {activeTab === "yaml" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5 }}>
              Full file content. <span style={{ color: COLORS.text, fontWeight: 600 }}>Apply to draft</span> merges into memory; then use{" "}
              <span style={{ color: COLORS.text, fontWeight: 600 }}>Save system YAML</span> in the header to persist.
            </div>
            <textarea
              value={yamlText}
              onChange={(e) => setYamlText(e.target.value)}
              spellCheck={false}
              style={{
                width: "100%",
                minHeight: 360,
                boxSizing: "border-box",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
                lineHeight: 1.45,
                background: COLORS.bgInput,
                color: COLORS.text,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 8,
                padding: 12,
              }}
            />
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              <button type="button" onClick={applyYaml} style={{ padding: "8px 14px", borderRadius: 6, border: "none", background: COLORS.success, color: "#0a0b0f", fontWeight: 700, cursor: "pointer" }}>
                Apply to draft
              </button>
              <button
                type="button"
                onClick={() => {
                  if (!doc) return;
                  try {
                    setYamlText(yaml.dump(doc, { lineWidth: 100, noRefs: true }));
                  } catch {
                    setYamlText("");
                  }
                }}
                style={{ ...inp, background: COLORS.bgCard, cursor: "pointer" }}
              >
                Reset from draft
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
