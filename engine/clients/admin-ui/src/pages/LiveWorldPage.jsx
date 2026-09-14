import { useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { Icons, ActionButton, DataTable, usePolledList, FetchErrorBanner } from "../adminCommon.jsx";

// Live › Live world: what is in Redis right now (occupied rooms, live creatures) and the
// spawn/despawn actions that change it. Templates themselves are under World › Content Library.

const sel = (COLORS) => ({ padding: "6px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 12 });

function Snapshot() {
  const { colors: COLORS } = useAdminTheme();
  const [live, setLive] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => axios.get(`${API_BASE}/world/live`)
      .then(({ data }) => { if (alive) { setLive(data); setError(null); } })
      .catch((e) => alive && setError(e?.response?.data?.detail || e.message));
    load();
    const id = setInterval(load, 8000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
      <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text }}>Redis snapshot</h3>
      <FetchErrorBanner error={error} label="live world" />
      {live && (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "12px 24px", fontSize: 13, fontFamily: "'JetBrains Mono', monospace", color: COLORS.textMuted }}>
            <span>Redis: <strong style={{ color: COLORS.text }}>{live.redis_connected ? "up" : "down"}</strong></span>
            <span title="Rooms whose occupant set is not empty, counting players and agents">Occupied rooms: <strong style={{ color: COLORS.text }}>{live.rooms_with_players ?? "—"}</strong></span>
            <span>Creature states: <strong style={{ color: COLORS.text }}>{live.entity_state_keys ?? "—"}</strong></span>
            <span>Item states: <strong style={{ color: COLORS.text }}>{live.item_state_keys ?? "—"}</strong></span>
            <span>Combat keys: <strong style={{ color: COLORS.text }}>{live.combat_keys ?? "—"}</strong></span>
          </div>
          {live.note && <div style={{ fontSize: 11, color: COLORS.textDim }}>{live.note}</div>}
          {(live.rooms_with_players_detail || []).length > 0 && (
            <div style={{ maxHeight: 280, overflow: "auto" }}>
              <DataTable columns={[
                { label: "Room", key: "room_id", mono: true },
                { label: "Occupants", key: "player_count", mono: true },
              ]} rows={live.rooms_with_players_detail} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Creatures() {
  const { colors: COLORS } = useAdminTheme();
  const { rows: templates } = usePolledList(`${API_BASE}/content/entities`, 60000);
  const { rows: liveEntities, error: liveError } = usePolledList(`${API_BASE}/world/entities`, 8000);
  const { rows: zones } = usePolledList(`${API_BASE}/content/zones`, 60000);
  const [zone, setZone] = useState("");
  const { rows: rooms } = usePolledList(zone ? `${API_BASE}/content/zones/${zone}/rooms` : null, 60000, { enabled: !!zone });
  const [room, setRoom] = useState("");
  const [template, setTemplate] = useState("");
  const [msg, setMsg] = useState(null);

  const spawn = async () => {
    setMsg(null);
    try {
      const { data } = await axios.post(`${API_BASE}/world/rooms/${zone}/${room}/spawn`, { template });
      setMsg({ ok: true, text: `Spawned ${data.entity_id}.` });
    } catch (e) {
      setMsg({ ok: false, text: e.response?.data?.detail || e.message });
    }
  };

  const despawn = async (ent) => {
    if (!window.confirm(`Despawn ${ent.name || ent.id}?`)) return;
    try {
      await axios.delete(`${API_BASE}/world/entities/${ent.id}`);
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    }
  };

  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text }}>Live creatures</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select id="live-spawn-zone" aria-label="Zone" value={zone} onChange={(e) => { setZone(e.target.value); setRoom(""); }} style={sel(COLORS)}>
            <option value="">zone…</option>
            {zones.map((z) => <option key={z.id} value={z.id}>{z.id}</option>)}
          </select>
          <select id="live-spawn-room" aria-label="Room" value={room} onChange={(e) => setRoom(e.target.value)} style={sel(COLORS)}>
            <option value="">room…</option>
            {rooms.map((r) => <option key={r.id} value={r.name}>{r.name}</option>)}
          </select>
          <select id="live-spawn-template" aria-label="Creature template" value={template} onChange={(e) => setTemplate(e.target.value)} style={sel(COLORS)}>
            <option value="">template…</option>
            {templates.map((t) => <option key={t.id} value={t.id}>{t.id}</option>)}
          </select>
          <ActionButton small variant="primary" icon={<Icons.Plus />} disabled={!zone || !room || !template} onClick={spawn}>Spawn</ActionButton>
        </div>
      </div>
      {msg && <div style={{ fontSize: 12, color: msg.ok ? COLORS.success : COLORS.danger, fontFamily: "'JetBrains Mono', monospace" }}>{msg.text}</div>}
      <FetchErrorBanner error={liveError} label="live creatures" />
      {!liveEntities.length && !liveError && <div style={{ fontSize: 12, color: COLORS.textMuted }}>No live creatures in occupied rooms right now.</div>}
      {liveEntities.length > 0 && (
        <DataTable columns={[
          { label: "Creature", render: (row) => (<div><div style={{ fontWeight: 600, fontSize: 13 }}>{row.name}</div><div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{row.id}</div></div>) },
          { label: "Template", key: "template", mono: true },
          { label: "Room", key: "room_id", mono: true },
          { label: "HP", render: (row) => <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{row.hp}/{row.max_hp}</span> },
          { label: "", render: (row) => <ActionButton small variant="danger" onClick={() => despawn(row)}>Despawn</ActionButton> },
        ]} rows={liveEntities} />
      )}
    </div>
  );
}

export default function LiveWorldPage() {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Live world</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>What the running server holds right now, and spawning or removing creatures. Creature templates are edited under World › Content Library.</p>
      </div>
      <Snapshot />
      <Creatures />
    </div>
  );
}
