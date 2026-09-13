import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API_BASE } from "./builderConstants.js";
import { useAdminTheme } from "../AdminThemeContext.jsx";

export default function BuilderSearchPanel({
  onOpenZone,
  onOpenSystem,
  onOpenShip,
  onOpenRoom,
}) {
  const { colors: COLORS } = useAdminTheme();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState({ zones: [], systems: [], ships: [], rooms: [] });
  const wrapRef = useRef(null);

  const runSearch = useCallback(async (query) => {
    const t = query.trim();
    if (t.length < 2) {
      setData({ zones: [], systems: [], ships: [], rooms: [] });
      return;
    }
    setLoading(true);
    try {
      const { data: d } = await axios.get(`${API_BASE}/content/builder/search`, { params: { q: t, limit: 40 } });
      setData(d || { zones: [], systems: [], ships: [], rooms: [] });
    } catch {
      setData({ zones: [], systems: [], ships: [], rooms: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => runSearch(q), 280);
    return () => clearTimeout(id);
  }, [q, runSearch]);

  useEffect(() => {
    const close = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const total = ["zones", "systems", "ships", "rooms"].reduce((n, k) => n + (data[k]?.length || 0), 0);

  const sectionHead = (title) => (
    <div
      style={{
        padding: "6px 10px",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        color: COLORS.textDim,
        background: COLORS.bgInput,
        borderBottom: `1px solid ${COLORS.border}`,
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      {title}
    </div>
  );

  const row = (item, onPick) => (
    <button
      key={`${item.kind}-${item.id}-${item.zone_id || ""}-${item.room_slug || ""}`}
      type="button"
      onClick={() => {
        onPick();
        setOpen(false);
        setQ("");
      }}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        padding: "8px 10px",
        border: "none",
        borderBottom: `1px solid ${COLORS.border}`,
        background: COLORS.bgCard,
        color: COLORS.text,
        cursor: "pointer",
        fontSize: 12,
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      <span style={{ fontWeight: 600 }}>{item.label}</span>
      <span style={{ color: COLORS.textDim, fontSize: 10, marginLeft: 8, fontFamily: "'JetBrains Mono', monospace" }}>{item.kind}</span>
      {item.detail && <div style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 2 }}>{item.detail}</div>}
    </button>
  );

  return (
    <div ref={wrapRef} style={{ position: "relative", minWidth: 260, maxWidth: 360 }}>
      <input
        type="search"
        placeholder="Search zones, systems, ships, rooms…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        style={{
          width: "100%",
          padding: "8px 12px",
          borderRadius: 8,
          border: `1px solid ${COLORS.border}`,
          background: COLORS.bgInput,
          color: COLORS.text,
          fontSize: 13,
          fontFamily: "'DM Sans', sans-serif",
          boxSizing: "border-box",
        }}
      />
      {open && (q.trim().length >= 2 || total > 0) && (
        <div
          style={{
            position: "absolute",
            zIndex: 50,
            top: "100%",
            left: 0,
            right: 0,
            marginTop: 4,
            maxHeight: 360,
            overflow: "auto",
            background: COLORS.bgPanel,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 10,
            boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
          }}
        >
          {loading && <div style={{ padding: 12, fontSize: 12, color: COLORS.textMuted }}>Searching…</div>}
          {!loading && q.trim().length < 2 && <div style={{ padding: 12, fontSize: 12, color: COLORS.textMuted }}>Type at least 2 characters.</div>}
          {!loading && q.trim().length >= 2 && total === 0 && <div style={{ padding: 12, fontSize: 12, color: COLORS.textMuted }}>No matches.</div>}
          {!loading && (data.zones || []).length > 0 && sectionHead("Zones")}
          {!loading &&
            (data.zones || []).map((it) =>
              row(it, () => onOpenZone?.(it.id, it.label))
            )}
          {!loading && (data.systems || []).length > 0 && sectionHead("Systems")}
          {!loading &&
            (data.systems || []).map((it) =>
              row(it, () => onOpenSystem?.(it.id, it.label))
            )}
          {!loading && (data.ships || []).length > 0 && sectionHead("Ships")}
          {!loading &&
            (data.ships || []).map((it) =>
              row(it, () => onOpenShip?.(it.id, it.label))
            )}
          {!loading && (data.rooms || []).length > 0 && sectionHead("Rooms")}
          {!loading &&
            (data.rooms || []).map((it) =>
              row(it, () => onOpenRoom?.(it.zone_id, it.room_slug, it.label))
            )}
        </div>
      )}
    </div>
  );
}
