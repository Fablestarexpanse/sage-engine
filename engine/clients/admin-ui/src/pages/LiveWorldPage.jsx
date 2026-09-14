import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { Icons, ActionButton, Badge, DataTable, SearchBar, StatCard, usePolledList, FetchErrorBanner } from "../adminCommon.jsx";

// Live › Live world: what the running server holds in Redis right now. Who stands in each room
// (players, agents, and names left behind that are not connected), every live creature, and every
// item lying on a floor, with the actions that change them. Templates are under World › Content Library.

const mono = "'JetBrains Mono', monospace";
const sel = (COLORS) => ({ padding: "6px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 12 });
const card = (COLORS) => ({ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 });
const errorText = (e) => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : e?.message || "Request failed";
};

// GET a {rows,total} (or any object) endpoint every intervalMs; reload() refetches now.
function usePolled(url, intervalMs) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = () => axios.get(url)
      .then(({ data: d }) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => alive && setError(errorText(e)));
    load();
    const id = setInterval(load, intervalMs);
    return () => { alive = false; clearInterval(id); };
  }, [url, intervalMs, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, reload };
}

const Names = ({ names, color }) => (
  <span style={{ fontFamily: mono, fontSize: 12, color }}>{names.length ? names.join(", ") : "—"}</span>
);

function Rooms({ snapshot, error, reload }) {
  const { colors: COLORS } = useAdminTheme();
  const [note, setNote] = useState(null);
  const totals = snapshot?.totals || {};
  const occupied = (snapshot?.rooms || []).filter((r) => r.players.length || r.agents.length || r.offline.length);

  const clearOffline = async () => {
    if (!window.confirm(`Remove ${totals.offline_occupants} name(s) that are not connected from the rooms they appear in?`)) return;
    try {
      const { data } = await axios.post(`${API_BASE}/world/occupants/clear-offline`);
      setNote({ ok: true, text: `Removed ${data.removed.map((r) => `${r.name} (${r.room_id})`).join(", ") || "nothing"}.` });
      reload();
    } catch (e) {
      setNote({ ok: false, text: errorText(e) });
    }
  };

  return (
    <div style={card(COLORS)}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text }}>Who is in which room</h3>
        {totals.offline_occupants > 0 && (
          <ActionButton small variant="danger" onClick={clearOffline}>Clear {totals.offline_occupants} left behind</ActionButton>
        )}
      </div>
      <FetchErrorBanner error={error || snapshot?.error} label="live world" />
      {totals.offline_occupants > 0 && (
        <div role="note" style={{ fontSize: 12, color: COLORS.warning, background: COLORS.warningBg, border: `1px solid ${COLORS.warning}44`, borderRadius: 6, padding: "8px 10px" }}>
          Left behind: characters listed in a room but not connected. Players in that room see them as present. A server crash (which skips the logout clean-up) leaves these.
        </div>
      )}
      {note && <div style={{ fontSize: 12, color: note.ok ? COLORS.success : COLORS.danger, fontFamily: mono }}>{note.text}</div>}
      {occupied.length === 0 && snapshot && <div style={{ fontSize: 12, color: COLORS.textMuted }}>Nobody is in any room.</div>}
      {occupied.length > 0 && (
        <div style={{ maxHeight: 320, overflow: "auto" }}>
          <DataTable columns={[
            { label: "Room", key: "room_id", mono: true },
            { label: "Players", render: (r) => <Names names={r.players} color={COLORS.text} /> },
            { label: "Agents", render: (r) => <Names names={r.agents} color={COLORS.textMuted} /> },
            { label: "Left behind", render: (r) => <Names names={r.offline} color={r.offline.length ? COLORS.warning : COLORS.textDim} /> },
          ]} rows={occupied.map((r) => ({ id: r.room_id, ...r }))} />
        </div>
      )}
    </div>
  );
}

function Creatures() {
  const { colors: COLORS } = useAdminTheme();
  const { data, error, reload } = usePolled(`${API_BASE}/world/entities`, 8000);
  const { rows: templates } = usePolledList(`${API_BASE}/content/entities`, 60000);
  const { rows: zones } = usePolledList(`${API_BASE}/content/zones`, 60000);
  const [zone, setZone] = useState("");
  const { rows: rooms } = usePolledList(zone ? `${API_BASE}/content/zones/${zone}/rooms` : null, 60000, { enabled: !!zone });
  const [room, setRoom] = useState("");
  const [template, setTemplate] = useState("");
  const [search, setSearch] = useState("");
  const [msg, setMsg] = useState(null);

  const spawn = async () => {
    setMsg(null);
    try {
      const { data: d } = await axios.post(`${API_BASE}/world/rooms/${zone}/${room}/spawn`, { template });
      setMsg({ ok: true, text: `Spawned ${d.entity_id}.` });
      reload();
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    }
  };

  const despawn = async (ent) => {
    if (!window.confirm(`Despawn ${ent.name || ent.id}?`)) return;
    try {
      await axios.delete(`${API_BASE}/world/entities/${ent.id}`);
      reload();
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    }
  };

  const q = search.toLowerCase();
  const rows = (data?.rows || []).filter((r) => `${r.name} ${r.id} ${r.template} ${r.room_id}`.toLowerCase().includes(q));

  return (
    <div style={card(COLORS)}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text }}>Live creatures {data && <span style={{ color: COLORS.textMuted, fontWeight: 400 }}>({data.total})</span>}</h3>
        <SearchBar placeholder="Filter by name, template or room…" value={search} onChange={setSearch} />
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, color: COLORS.textMuted }}>Spawn</span>
        <select id="live-spawn-template" aria-label="Creature template" value={template} onChange={(e) => setTemplate(e.target.value)} style={sel(COLORS)}>
          <option value="">template…</option>
          {templates.map((t) => <option key={t.id} value={t.id}>{t.id}</option>)}
        </select>
        <span style={{ fontSize: 12, color: COLORS.textMuted }}>in</span>
        <select id="live-spawn-zone" aria-label="Zone" value={zone} onChange={(e) => { setZone(e.target.value); setRoom(""); }} style={sel(COLORS)}>
          <option value="">zone…</option>
          {zones.map((z) => <option key={z.id} value={z.id}>{z.id}</option>)}
        </select>
        <select id="live-spawn-room" aria-label="Room" value={room} onChange={(e) => setRoom(e.target.value)} style={sel(COLORS)}>
          <option value="">room…</option>
          {rooms.map((r) => <option key={r.id} value={r.name}>{r.name}</option>)}
        </select>
        <ActionButton small variant="primary" icon={<Icons.Plus />} disabled={!zone || !room || !template} onClick={spawn}>Spawn</ActionButton>
      </div>
      {msg && <div style={{ fontSize: 12, color: msg.ok ? COLORS.success : COLORS.danger, fontFamily: mono }}>{msg.text}</div>}
      <FetchErrorBanner error={error} label="live creatures" />
      {data && rows.length === 0 && <div style={{ fontSize: 12, color: COLORS.textMuted }}>{data.total ? "No creatures match." : "No live creatures."}</div>}
      {rows.length > 0 && (
        <div style={{ maxHeight: 420, overflow: "auto" }}>
          <DataTable columns={[
            { label: "Creature", render: (r) => (<div><div style={{ fontWeight: 600, fontSize: 13 }}>{r.name}</div><div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: mono }}>{r.id}</div></div>) },
            { label: "Template", key: "template", mono: true },
            { label: "Room", render: (r) => (
              <span style={{ display: "inline-flex", gap: 6, alignItems: "center", fontFamily: mono, fontSize: 12 }}>
                {r.room_id || "—"}{!r.room_known && <Badge color={COLORS.warning}>room not in world</Badge>}
              </span>
            ) },
            { label: "HP", render: (r) => <span style={{ fontFamily: mono }}>{r.hp}/{r.max_hp}</span> },
            { label: "", render: (r) => <ActionButton small variant="danger" onClick={() => despawn(r)}>Despawn</ActionButton> },
          ]} rows={rows} />
        </div>
      )}
      {data && data.total > (data.rows || []).length && <div style={{ fontSize: 11, color: COLORS.textDim }}>Showing the first {data.rows.length} of {data.total}.</div>}
    </div>
  );
}

function FloorItems() {
  const { colors: COLORS } = useAdminTheme();
  const { data, error, reload } = usePolled(`${API_BASE}/world/items`, 15000);
  const [search, setSearch] = useState("");
  const [msg, setMsg] = useState(null);
  const q = search.toLowerCase();
  const rows = (data?.rows || []).filter((r) => `${r.name} ${r.id} ${r.template} ${r.room_id}`.toLowerCase().includes(q));

  const remove = async (item) => {
    if (!window.confirm(`Remove ${item.name || item.id} from ${item.room_id}? It is deleted, not moved.`)) return;
    const [zone, slug] = item.room_id.split(":");
    try {
      await axios.delete(`${API_BASE}/world/rooms/${zone}/${slug}/items/${encodeURIComponent(item.id)}`);
      setMsg({ ok: true, text: `Removed ${item.id}.` });
      reload();
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    }
  };

  return (
    <div style={card(COLORS)}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text }}>Items on floors {data && <span style={{ color: COLORS.textMuted, fontWeight: 400 }}>({data.total})</span>}</h3>
        <SearchBar placeholder="Filter by name, template or room…" value={search} onChange={setSearch} />
      </div>
      {msg && <div style={{ fontSize: 12, color: msg.ok ? COLORS.success : COLORS.danger, fontFamily: mono }}>{msg.text}</div>}
      <FetchErrorBanner error={error} label="floor items" />
      {data && rows.length === 0 && <div style={{ fontSize: 12, color: COLORS.textMuted }}>{data.total ? "No items match." : "No items are lying on any floor."}</div>}
      {rows.length > 0 && (
        <div style={{ maxHeight: 420, overflow: "auto" }}>
          <DataTable columns={[
            { label: "Item", render: (r) => (<div><div style={{ fontWeight: 600, fontSize: 13 }}>{r.name || "—"}</div><div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: mono }}>{r.id}</div></div>) },
            { label: "Template", render: (r) => <span style={{ fontFamily: mono, fontSize: 12 }}>{r.template || "—"}{!r.has_state && <Badge color={COLORS.warning}>no state</Badge>}</span> },
            { label: "Room", render: (r) => (
              <span style={{ display: "inline-flex", gap: 6, alignItems: "center", fontFamily: mono, fontSize: 12 }}>
                {r.room_id}{!r.room_known && <Badge color={COLORS.warning}>room not in world</Badge>}
              </span>
            ) },
            { label: "", render: (r) => <ActionButton small variant="danger" onClick={() => remove(r)}>Remove</ActionButton> },
          ]} rows={rows} />
        </div>
      )}
      {data && data.total > (data.rows || []).length && <div style={{ fontSize: 11, color: COLORS.textDim }}>Showing the first {data.rows.length} of {data.total}.</div>}
    </div>
  );
}

export default function LiveWorldPage() {
  const { colors: COLORS } = useAdminTheme();
  const { data: snapshot, error, reload } = usePolled(`${API_BASE}/world/live`, 8000);
  const t = snapshot?.totals || {};
  const n = (v) => (v == null ? "—" : String(v));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Live world</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>What the running server holds right now. Creature and item templates are edited under World › Content Library.</p>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
        <StatCard label="Rooms with players" value={n(t.rooms_with_players)} color={COLORS.success} icon={<Icons.Players />} />
        <StatCard label="Rooms with agents" value={n(t.rooms_with_agents)} color={COLORS.info} icon={<Icons.Players />} />
        <StatCard label="Left behind" value={n(t.offline_occupants)} color={t.offline_occupants ? COLORS.warning : COLORS.textDim} icon={<Icons.Alert />} />
        <StatCard label="Live creatures" value={n(t.creatures)} color={COLORS.accent} icon={<Icons.World />} />
        <StatCard label="Items on floors" value={n(t.floor_items)} color={COLORS.accent} icon={<Icons.Items />} />
      </div>
      <Rooms snapshot={snapshot} error={error} reload={reload} />
      <Creatures />
      <FloorItems />
    </div>
  );
}
