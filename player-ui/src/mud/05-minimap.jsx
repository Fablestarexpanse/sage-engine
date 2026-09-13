import { useMemo, useState } from "react";
import { usePlayTheme } from "../PlayThemeContext.jsx";

/**
 * MiniMap — renders the zone map the server sends in character_snapshot.map:
 * {zone, current, rooms: [{id, name, x, y, visited}], edges: [[id, id], ...]}.
 * Unvisited rooms show as dim unlabeled markers; the current room pulses.
 */
export function MiniMap({ map = null }) {
  const { T } = usePlayTheme();
  const [hov, setHov] = useState(null);
  const [zoom, setZoom] = useState(1);

  const view = useMemo(() => {
    const rooms = Array.isArray(map?.rooms) ? map.rooms.filter((r) => r && r.id) : [];
    if (!rooms.length) return null;
    // Normalise editor coordinates into a compact viewBox.
    const xs = rooms.map((r) => Number(r.x) || 0);
    const ys = rooms.map((r) => Number(r.y) || 0);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    const spanX = Math.max(1, Math.max(...xs) - minX);
    const spanY = Math.max(1, Math.max(...ys) - minY);
    const W = 320;
    const H = 210;
    const pad = 28;
    const sx = (W - pad * 2) / spanX;
    const sy = (H - pad * 2) / spanY;
    const s = Math.min(sx, sy);
    const placed = rooms.map((r) => ({
      ...r,
      px: pad + ((Number(r.x) || 0) - minX) * s + (W - pad * 2 - spanX * s) / 2,
      py: pad + ((Number(r.y) || 0) - minY) * s + (H - pad * 2 - spanY * s) / 2,
    }));
    const byId = new Map(placed.map((r) => [r.id, r]));
    const edges = (Array.isArray(map?.edges) ? map.edges : [])
      .map(([a, b]) => [byId.get(a), byId.get(b)])
      .filter(([a, b]) => a && b);
    return { placed, edges, W, H };
  }, [map]);

  if (!view) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: T.text.muted, fontSize: 11, fontFamily: T.font.body, padding: 12, textAlign: "center" }}>
        No map data yet — move around and the station will chart itself.
      </div>
    );
  }

  const current = map?.current;
  const roomCol = (r) => {
    if (r.id === current) return T.glyph.violet;
    if (!r.visited) return T.text.muted + "40";
    return T.glyph.cyan;
  };

  return (
    <div style={{ height: "100%", position: "relative", overflow: "hidden" }}>
      <svg width="100%" height="100%" viewBox={`0 0 ${view.W} ${view.H}`} style={{ transform: `scale(${zoom})`, transformOrigin: "center", transition: "transform 0.2s" }}>
        <defs><pattern id="g" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="10" cy="10" r="0.5" fill={T.text.muted+"20"}/></pattern></defs>
        <rect x="0" y="0" width={view.W} height={view.H} fill="url(#g)"/>
        {view.edges.map(([a, b], i) => {
          const lit = a.visited && b.visited;
          return <line key={i} x1={a.px} y1={a.py} x2={b.px} y2={b.py} stroke={lit ? T.text.muted+"50" : T.text.muted+"15"} strokeWidth={lit ? 1.5 : 1} strokeDasharray={lit ? "none" : "4 3"}/>;
        })}
        {view.placed.map((r) => {
          const c = roomCol(r);
          const isCur = r.id === current;
          const h = hov === r.id;
          return (
            <g key={r.id} onMouseEnter={() => setHov(r.id)} onMouseLeave={() => setHov(null)}
              role="img" aria-label={r.visited ? r.name : "Unexplored"}>
              {isCur && <circle cx={r.px} cy={r.py} r={16} fill="none" stroke={T.glyph.violet} strokeWidth={1} opacity={0.3} style={{ animation: "pulse 2s ease-in-out infinite" }}/>}
              <circle cx={r.px} cy={r.py} r={isCur ? 10 : h ? 9 : 7} fill={r.visited ? c + "20" : T.bg.deep} stroke={c} strokeWidth={isCur ? 2 : 1.5} opacity={r.visited ? 1 : 0.35}/>
              {isCur && <circle cx={r.px} cy={r.py} r={3.5} fill={T.glyph.violet}/>}
              {r.visited && (
                <text x={r.px} y={r.py + (isCur ? 20 : 17)} textAnchor="middle" fill={h ? T.text.primary : T.text.muted} fontSize={7} fontFamily={T.font.body}>
                  {r.name}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div style={{ position: "absolute", bottom: 6, right: 6, display: "flex", gap: 3 }}>
        {[0.8, 1, 1.3].map((z) => <button key={z} type="button" onClick={() => setZoom(z)} aria-label={`Zoom ${z}x`} style={{ width: 20, height: 20, borderRadius: T.radius.sm, background: zoom === z ? T.glyph.violetDim : T.bg.surface, border: `1px solid ${zoom === z ? T.border.glyph : T.border.subtle}`, color: zoom === z ? T.text.accent : T.text.muted, cursor: "pointer", fontSize: 9, fontFamily: T.font.mono, display: "flex", alignItems: "center", justifyContent: "center" }}>{z === 0.8 ? "−" : z === 1 ? "○" : "+"}</button>)}
      </div>
    </div>
  );
}
