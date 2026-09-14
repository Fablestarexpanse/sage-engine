import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API_BASE } from "./builderConstants.js";
import { useAdminTheme } from "../AdminThemeContext.jsx";

const VB_W = 900;
const VB_H = 520;
const PAD = 72;

function securityColor(sec, C) {
  if (sec === "high") return C.success;
  if (sec === "medium") return C.warning;
  return C.danger;
}

/** Bounds + scale shared by layout and click-to-world mapping. */
function computeLayoutTransform(systems) {
  const raw = systems.map((s) => {
    const c = s.coordinates || {};
    const gx = Number(c.x) || 0;
    const gy = Number(c.y) || 0;
    return { ...s, gx, gy };
  });
  let minX;
  let maxX;
  let minY;
  let maxY;
  if (!raw.length) {
    minX = -5;
    maxX = 5;
    minY = -5;
    maxY = 5;
  } else {
    const xs = raw.map((p) => p.gx);
    const ys = raw.map((p) => p.gy);
    minX = Math.min(...xs);
    maxX = Math.max(...xs);
    minY = Math.min(...ys);
    maxY = Math.max(...ys);
    if (minX === maxX) {
      minX -= 1;
      maxX += 1;
    }
    if (minY === maxY) {
      minY -= 1;
      maxY += 1;
    }
  }
  const rw = maxX - minX;
  const rh = maxY - minY;
  const sc = Math.min((VB_W - 2 * PAD) / rw, (VB_H - 2 * PAD) / rh) * 0.92;
  return { raw, minX, maxX, minY, maxY, sc };
}

function layoutPlacedFromGalaxySystems(galaxySystems) {
  const t = computeLayoutTransform(galaxySystems);
  const placed = t.raw.map((p) => ({
    ...p,
    sx: PAD + (p.gx - t.minX) * t.sc,
    sy: PAD + (p.gy - t.minY) * t.sc,
    size: Math.min(16, 9 + Math.min(5, (p.bodies || []).length || 0)),
  }));
  const layoutTransform = { minX: t.minX, maxX: t.maxX, minY: t.minY, maxY: t.maxY, sc: t.sc };
  return { placed, layoutTransform };
}

function worldFromSvgXY(sx, sy, t) {
  if (!t || !t.sc) return { x: 0, y: 0 };
  return {
    x: (sx - PAD) / t.sc + t.minX,
    y: (sy - PAD) / t.sc + t.minY,
  };
}

function svgFromWorldXY(wx, wy, t) {
  if (!t || !t.sc) return { sx: PAD, sy: PAD };
  return {
    sx: PAD + (wx - t.minX) * t.sc,
    sy: PAD + (wy - t.minY) * t.sc,
  };
}

function roundCoord(n) {
  return Math.round(n * 1000) / 1000;
}

function clientPointToSvg(svg, clientX, clientY) {
  if (!svg || typeof svg.createSVGPoint !== "function") return null;
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  return pt.matrixTransform(ctm.inverse());
}

export default function GalaxyView({ onSelectSystem }) {
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
  const svgRef = useRef(null);
  const [systems, setSystems] = useState([]);
  const [err, setErr] = useState("");
  const [hovered, setHovered] = useState(null);
  const [mapFilter, setMapFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [newId, setNewId] = useState("");
  const [newName, setNewName] = useState("");
  const [nx, setNx] = useState("0");
  const [ny, setNy] = useState("0");
  const [nz, setNz] = useState("0");
  const [nfaction, setNfaction] = useState("neutral");
  const [nsec, setNsec] = useState("low");
  const [placeHint, setPlaceHint] = useState("");

  const reloadGalaxy = () => {
    axios
      .get(`${API_BASE}/content/galaxy`)
      .then((r) => setSystems(r.data.systems || []))
      .catch((e) => setErr(String(e.response?.data?.detail || e.message)));
  };

  useEffect(() => {
    reloadGalaxy();
  }, []);

  useEffect(() => {
    if (showCreate) {
      setPlaceHint("Click or right-click empty space on the map to set X / Y (stars stay clickable on top).");
    } else {
      setPlaceHint("");
    }
  }, [showCreate]);

  const galaxySystems = useMemo(() => systems.filter((s) => !s.error), [systems]);

  const { placed: placedBase, layoutTransform } = useMemo(() => layoutPlacedFromGalaxySystems(galaxySystems), [galaxySystems]);

  const placed = useMemo(() => {
    const q = mapFilter.trim().toLowerCase();
    if (!q) return placedBase.map((p) => ({ ...p, dim: false }));
    return placedBase.map((p) => ({
      ...p,
      dim: !(
        String(p.id).toLowerCase().includes(q) ||
        String(p.name || "").toLowerCase().includes(q) ||
        String(p.faction || "").toLowerCase().includes(q)
      ),
    }));
  }, [placedBase, mapFilter]);

  const draftWorld = useMemo(() => {
    const x = parseFloat(nx);
    const y = parseFloat(ny);
    if (Number.isNaN(x) || Number.isNaN(y)) return null;
    return { x, y };
  }, [nx, ny]);

  const draftSvg = draftWorld ? svgFromWorldXY(draftWorld.x, draftWorld.y, layoutTransform) : null;

  const applyClickToWorld = (clientX, clientY) => {
    const svg = svgRef.current;
    const p = clientPointToSvg(svg, clientX, clientY);
    if (!p) return;
    const w = worldFromSvgXY(p.x, p.y, layoutTransform);
    const rx = roundCoord(w.x);
    const ry = roundCoord(w.y);
    setNx(String(rx));
    setNy(String(ry));
    setPlaceHint(`Position ${rx}, ${ry} (Z unchanged — edit below if needed)`);
  };

  const posById = useMemo(() => {
    const m = new Map();
    placed.forEach((p) => m.set(p.id, p));
    return m;
  }, [placed]);

  const jumpSegments = useMemo(() => {
    const out = [];
    const seen = new Set();
    placed.forEach((sys) => {
      const conns = sys.connections || [];
      conns.forEach((c) => {
        const target = typeof c === "string" ? c : c.target;
        if (!target) return;
        const a = sys.id;
        const b = target;
        const key = [a, b].sort().join("|");
        if (seen.has(key)) return;
        const pa = posById.get(a);
        const pb = posById.get(b);
        if (!pa || !pb) return;
        seen.add(key);
        const typ = (typeof c === "object" && c.type) || "jump_gate";
        const worm = String(typ).includes("worm");
        out.push({ a: pa, b: pb, worm, key });
      });
    });
    return out;
  }, [placed, posById]);

  const hov = hovered ? placed.find((p) => p.id === hovered) : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, position: "relative", fontFamily: "'DM Sans', sans-serif" }}>
      {err && <div style={{ color: COLORS.danger, fontSize: 12 }}>{err}</div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <input
          type="search"
          placeholder="Filter map by name, id, or faction…"
          value={mapFilter}
          onChange={(e) => setMapFilter(e.target.value)}
          style={{ ...inp, flex: "1 1 200px", maxWidth: 360 }}
        />
        <button type="button" onClick={() => reloadGalaxy()} style={{ ...inp, background: COLORS.bgCard, cursor: "pointer", fontWeight: 600 }}>
          Reload map
        </button>
        <button type="button" onClick={() => setShowCreate((s) => !s)} style={{ ...inp, background: COLORS.accentGlow, borderColor: COLORS.accent, color: COLORS.accent, cursor: "pointer", fontWeight: 600 }}>
          {showCreate ? "Hide" : "Add system"}
        </button>
      </div>
      {showCreate && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            alignItems: "flex-end",
            padding: 12,
            background: COLORS.bgCard,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 10,
          }}
        >
          <div>
            <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>System id (slug)</div>
            <input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="e.g. deep_rift" style={{ ...inp, width: 140 }} />
          </div>
          <div>
            <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Display name</div>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Deep Rift" style={{ ...inp, width: 160 }} />
          </div>
          <div>
            <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>X / Y (map) · Z</div>
            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <input value={nx} onChange={(e) => setNx(e.target.value)} title="Set by clicking the map or type" style={{ ...inp, width: 64 }} />
              <input value={ny} onChange={(e) => setNy(e.target.value)} title="Set by clicking the map or type" style={{ ...inp, width: 64 }} />
              <input value={nz} onChange={(e) => setNz(e.target.value)} placeholder="z" title="Elevation (optional)" style={{ ...inp, width: 52 }} />
            </div>
          </div>
          <div>
            <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Faction</div>
            <input value={nfaction} onChange={(e) => setNfaction(e.target.value)} style={{ ...inp, width: 120 }} />
          </div>
          <div>
            <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Security</div>
            <select value={nsec} onChange={(e) => setNsec(e.target.value)} style={{ ...inp }}>
              <option value="high">high</option>
              <option value="medium">medium</option>
              <option value="low">low</option>
              <option value="none">none</option>
            </select>
          </div>
          <button
            type="button"
            disabled={createBusy}
            onClick={async () => {
              const id = newId.trim();
              if (!id || !/^[a-zA-Z0-9_-]+$/.test(id)) {
                window.alert("Use letters, numbers, underscores, hyphens only.");
                return;
              }
              setCreateBusy(true);
              try {
                await axios.post(`${API_BASE}/content/systems`, {
                  id,
                  name: newName.trim() || id,
                  x: parseFloat(nx) || 0,
                  y: parseFloat(ny) || 0,
                  z: parseFloat(nz) || 0,
                  faction: nfaction,
                  security: nsec,
                  add_to_galaxy: true,
                });
                setNewId("");
                setNewName("");
                reloadGalaxy();
                setShowCreate(false);
              } catch (e) {
                window.alert(e.response?.data?.detail || e.message);
              } finally {
                setCreateBusy(false);
              }
            }}
            style={{ padding: "8px 14px", borderRadius: 6, border: "none", background: COLORS.accent, color: "#fff", fontWeight: 700, cursor: "pointer" }}
          >
            Create
          </button>
        </div>
      )}
      {showCreate && placeHint && (
        <div style={{ fontSize: 12, color: COLORS.info, background: `${COLORS.info}12`, border: `1px solid ${COLORS.info}35`, borderRadius: 8, padding: "8px 12px" }}>{placeHint}</div>
      )}
      <div style={{ fontSize: 12, color: COLORS.textMuted }}>
        Click a star to open it. <span style={{ color: COLORS.text, fontWeight: 600 }}>Add system</span>: use the map for X/Y (or type). Filter dims non-matches.
      </div>
      <div
        style={{
          height: 440,
          borderRadius: 10,
          border: `1px solid ${COLORS.border}`,
          overflow: "hidden",
          background: COLORS.bg,
          position: "relative",
          cursor: showCreate ? "crosshair" : "default",
        }}
      >
        <svg ref={svgRef} width="100%" height="100%" viewBox={`0 0 ${VB_W} ${VB_H}`} style={{ display: "block" }}>
          <defs>
            <pattern id="galaxyGrid" width="40" height="40" patternUnits="userSpaceOnUse">
              <line x1="0" y1="0" x2="40" y2="0" stroke={COLORS.textDim} strokeWidth="0.2" opacity="0.35" />
              <line x1="0" y1="0" x2="0" y2="40" stroke={COLORS.textDim} strokeWidth="0.2" opacity="0.35" />
            </pattern>
            <filter id="nodeGlow">
              <feGaussianBlur stdDeviation="2" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <rect
            width={VB_W}
            height={VB_H}
            fill="url(#galaxyGrid)"
            style={{ cursor: showCreate ? "crosshair" : "default" }}
            onClick={(e) => {
              if (!showCreate) return;
              e.stopPropagation();
              applyClickToWorld(e.clientX, e.clientY);
            }}
            onContextMenu={(e) => {
              if (!showCreate) return;
              e.preventDefault();
              e.stopPropagation();
              applyClickToWorld(e.clientX, e.clientY);
            }}
          />
          <ellipse cx={680} cy={290} rx={120} ry={80} fill={COLORS.forge} opacity="0.04" pointerEvents="none" />
          <ellipse cx={220} cy={200} rx={100} ry={60} fill={COLORS.accent} opacity="0.05" pointerEvents="none" />

          {jumpSegments.map(({ a, b, worm, key }) => {
            const lit = hovered && (hovered === a.id || hovered === b.id);
            const bothDim = a.dim && b.dim;
            return (
              <g key={key} style={{ pointerEvents: "none" }}>
                <line
                  x1={a.sx}
                  y1={a.sy}
                  x2={b.sx}
                  y2={b.sy}
                  stroke={worm ? COLORS.accent : COLORS.border}
                  strokeWidth={worm ? 1 : 1.4}
                  strokeDasharray={worm ? "6 4" : "none"}
                  opacity={lit ? 0.75 : bothDim ? 0.06 : 0.28}
                />
              </g>
            );
          })}

          {placed.map((sys) => {
            const col = securityColor(sys.security, COLORS);
            const isH = hovered === sys.id;
            const dim = sys.dim;
            return (
              <g
                key={sys.id}
                style={{ cursor: "pointer", opacity: dim ? 0.2 : 1 }}
                onMouseEnter={() => setHovered(sys.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={(ev) => {
                  ev.stopPropagation();
                  onSelectSystem(sys.id, sys.name || sys.id);
                }}
              >
                <circle cx={sys.sx} cy={sys.sy} r={sys.size + 10} fill="none" stroke={col} strokeWidth={0.5} opacity={isH ? 0.45 : 0} />
                <circle
                  cx={sys.sx}
                  cy={sys.sy}
                  r={sys.size}
                  fill={`${col}35`}
                  stroke={col}
                  strokeWidth={isH ? 2 : 1}
                  filter={isH ? "url(#nodeGlow)" : undefined}
                />
                <circle cx={sys.sx} cy={sys.sy} r={sys.size * 0.42} fill={col} opacity={0.85} />
                <text
                  x={sys.sx}
                  y={sys.sy + sys.size + 15}
                  textAnchor="middle"
                  fontSize={11}
                  fontFamily="'Space Grotesk', sans-serif"
                  fill={isH ? COLORS.text : COLORS.textMuted}
                  fontWeight={isH ? 700 : 500}
                >
                  {sys.name || sys.id}
                </text>
                <text x={sys.sx} y={sys.sy + sys.size + 28} textAnchor="middle" fontSize={8} fontFamily="'JetBrains Mono', monospace" fill={COLORS.textDim}>
                  {sys.faction}
                </text>
              </g>
            );
          })}

          {showCreate && draftSvg && (
            <g pointerEvents="none">
              <circle cx={draftSvg.sx} cy={draftSvg.sy} r={14} fill="none" stroke={COLORS.accent} strokeWidth={2} strokeDasharray="4 3" opacity={0.95} />
              <circle cx={draftSvg.sx} cy={draftSvg.sy} r={4} fill={COLORS.accent} opacity={0.9} />
              <line x1={draftSvg.sx - 22} y1={draftSvg.sy} x2={draftSvg.sx + 22} y2={draftSvg.sy} stroke={COLORS.accent} strokeWidth={1} opacity={0.5} />
              <line x1={draftSvg.sx} y1={draftSvg.sy - 22} x2={draftSvg.sx} y2={draftSvg.sy + 22} stroke={COLORS.accent} strokeWidth={1} opacity={0.5} />
            </g>
          )}
        </svg>

        {hov && (
          <div
            style={{
              position: "absolute",
              left: 16,
              bottom: 16,
              background: COLORS.bgPanel,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 10,
              padding: 14,
              minWidth: 200,
              boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{hov.name || hov.id}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 10, fontSize: 12 }}>
              <div>
                <div style={{ fontSize: 9, color: COLORS.textDim, textTransform: "uppercase" }}>Security</div>
                <div style={{ fontWeight: 600, color: securityColor(hov.security, COLORS) }}>{hov.security}</div>
              </div>
              <div>
                <div style={{ fontSize: 9, color: COLORS.textDim, textTransform: "uppercase" }}>Bodies</div>
                <div style={{ fontWeight: 600, color: COLORS.text }}>{(hov.bodies || []).length}</div>
              </div>
            </div>
            <div style={{ marginTop: 8, fontSize: 10, color: COLORS.textDim }}>Click to enter system</div>
          </div>
        )}

        <div style={{ position: "absolute", top: 12, right: 12, display: "flex", gap: 14, alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <svg width="24" height="2">
              <line x1="0" y1="1" x2="24" y2="1" stroke={COLORS.border} strokeWidth="1.5" />
            </svg>
            <span style={{ fontSize: 10, color: COLORS.textMuted }}>Jump</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <svg width="24" height="2">
              <line x1="0" y1="1" x2="24" y2="1" stroke={COLORS.accent} strokeWidth="1.2" strokeDasharray="4 3" />
            </svg>
            <span style={{ fontSize: 10, color: COLORS.textMuted }}>Wormhole</span>
          </div>
        </div>
      </div>
    </div>
  );
}
