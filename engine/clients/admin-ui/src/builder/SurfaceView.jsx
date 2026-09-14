import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { API_BASE } from "./builderConstants.js";
import { useAdminTheme } from "../AdminThemeContext.jsx";

const ZONE_ID_RE = /^[a-zA-Z0-9_-]+$/;

export default function SurfaceView({ onSelectZone }) {
  const { colors: COLORS } = useAdminTheme();
  const inp = {
    padding: "8px 12px",
    borderRadius: 8,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgInput,
    color: COLORS.text,
    fontSize: 13,
    fontFamily: "'DM Sans', sans-serif",
    width: "100%",
    maxWidth: 360,
    boxSizing: "border-box",
  };
  const [zones, setZones] = useState([]);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("");
  const [showNewZone, setShowNewZone] = useState(false);
  const [newZoneId, setNewZoneId] = useState("");
  const [newZoneName, setNewZoneName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createErr, setCreateErr] = useState("");

  const loadZones = useCallback(() => {
    axios
      .get(`${API_BASE}/content/zones`)
      .then((r) => setZones(r.data || []))
      .catch((e) => setErr(String(e.response?.data?.detail || e.message)));
  }, []);

  useEffect(() => {
    loadZones();
  }, [loadZones]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return zones;
    return zones.filter(
      (z) =>
        String(z.id || "")
          .toLowerCase()
          .includes(q) ||
        String(z.name || "")
          .toLowerCase()
          .includes(q) ||
        String(z.type || "")
          .toLowerCase()
          .includes(q)
    );
  }, [zones, filter]);

  const submitNewZone = async (e) => {
    e.preventDefault();
    setCreateErr("");
    const id = newZoneId.trim();
    if (!id || !ZONE_ID_RE.test(id)) {
      setCreateErr("Zone ID must use only letters, numbers, underscore, or hyphen.");
      return;
    }
    setCreating(true);
    const displayName = newZoneName.trim();
    try {
      await axios.post(`${API_BASE}/content/zones`, { id, name: displayName });
      setNewZoneId("");
      setNewZoneName("");
      setShowNewZone(false);
      loadZones();
      onSelectZone(id, displayName || id);
    } catch (ex) {
      const d = ex.response?.data?.detail;
      setCreateErr(typeof d === "string" ? d : ex.message || "Create failed");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ fontFamily: "'DM Sans', sans-serif" }}>
      {err && <div style={{ color: COLORS.danger, marginBottom: 12 }}>{err}</div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 14 }}>
        <button
          type="button"
          onClick={() => {
            setShowNewZone((s) => !s);
            setCreateErr("");
          }}
          style={{
            padding: "8px 14px",
            borderRadius: 8,
            border: `1px solid ${COLORS.borderActive}`,
            background: COLORS.accentGlow,
            color: COLORS.accent,
            fontWeight: 600,
            fontSize: 13,
            cursor: "pointer",
            fontFamily: "'DM Sans', sans-serif",
          }}
        >
          + New Zone
        </button>
      </div>

      {showNewZone && (
        <form
          onSubmit={submitNewZone}
          style={{
            marginBottom: 16,
            padding: 14,
            background: COLORS.bgCard,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 10,
            maxWidth: 420,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, color: COLORS.text, marginBottom: 10 }}>Create zone</div>
          <label style={{ fontSize: 10, color: COLORS.textMuted, display: "block", marginBottom: 4 }}>Zone ID</label>
          <input
            value={newZoneId}
            onChange={(e) => setNewZoneId(e.target.value)}
            placeholder="e.g. archive_depths"
            style={{ ...inp, marginBottom: 10, maxWidth: "100%" }}
          />
          <label style={{ fontSize: 10, color: COLORS.textMuted, display: "block", marginBottom: 4 }}>Zone name</label>
          <input
            value={newZoneName}
            onChange={(e) => setNewZoneName(e.target.value)}
            placeholder="Display name"
            style={{ ...inp, marginBottom: 10, maxWidth: "100%" }}
          />
          {createErr && <div style={{ color: COLORS.danger, fontSize: 12, marginBottom: 8 }}>{createErr}</div>}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="submit"
              disabled={creating}
              style={{
                padding: "8px 14px",
                background: COLORS.accent,
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontWeight: 600,
                cursor: creating ? "wait" : "pointer",
              }}
            >
              {creating ? "Creating…" : "Create"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowNewZone(false);
                setCreateErr("");
              }}
              style={{
                padding: "8px 14px",
                background: COLORS.bgHover,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 6,
                color: COLORS.text,
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <input
        type="search"
        placeholder="Filter zones by id, name, or type…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{ ...inp, marginBottom: 14, maxWidth: "100%" }}
      />
      <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 14 }}>
        Pick a zone to edit its room graph. Zones live under <code style={{ color: COLORS.textDim }}>content/world/zones/</code>.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
        {filtered.map((z) => (
          <button
            key={z.id}
            type="button"
            onClick={() => onSelectZone(z.id, z.name || z.id)}
            style={{
              textAlign: "left",
              padding: 14,
              background: COLORS.bgCard,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 10,
              color: COLORS.text,
              cursor: "pointer",
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 14 }}>{z.name}</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 4 }}>{z.id}</div>
          </button>
        ))}
      </div>
      {zones.length === 0 && !err && <div style={{ color: COLORS.textMuted }}>No zones found.</div>}
      {zones.length > 0 && filtered.length === 0 && <div style={{ color: COLORS.textMuted }}>No zones match this filter.</div>}
    </div>
  );
}
