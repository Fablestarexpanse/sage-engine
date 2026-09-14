import { useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";
import { Badge, ActionButton, SearchBar, DataTable } from "./adminCommon.jsx";
import Pager from "./pager.jsx";
import { useDebounced, useHashParts } from "./listHooks.js";

// Find a character and act on it: move, set money, give or take items, kick.
// The server writes live state as well as the saved row, so a change to a character who has
// logged in is not undone by the next save cycle, and a connected player is told what changed.

const mono = "'JetBrains Mono', monospace";
const sans = "'DM Sans', sans-serif";

function errorText(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => `${(x.loc || []).slice(1).join(".")}: ${x.msg}`).join("; ");
  return e?.message || "Request failed";
}

function Section({ title, children }) {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, fontFamily: mono, textTransform: "uppercase", letterSpacing: "0.06em" }}>{title}</div>
      {children}
    </div>
  );
}

function CharacterDetail({ characterId, onChanged }) {
  const { colors: COLORS } = useAdminTheme();
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [roomId, setRoomId] = useState("");
  const [amounts, setAmounts] = useState({});
  const [template, setTemplate] = useState("");
  const [rooms, setRooms] = useState([]);
  const [items, setItems] = useState([]);
  const input = { padding: "7px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13, fontFamily: sans };

  const reload = async () => {
    const { data } = await axios.get(`${API_BASE}/admin/characters/${characterId}`);
    setDetail(data);
    setAmounts(Object.fromEntries(data.currencies.map((c) => [c.key, String(c.balance)])));
    return data;
  };

  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/admin/characters/${characterId}`)
      .then(({ data }) => {
        if (!alive) return;
        setDetail(data);
        setRoomId(data.room_id || "");
        setAmounts(Object.fromEntries(data.currencies.map((c) => [c.key, String(c.balance)])));
      })
      .catch((e) => alive && setError(errorText(e)));
    // Pickers are conveniences: staff without the content tools can still type ids.
    axios.get(`${API_BASE}/content/zones`)
      .then(async ({ data: zones }) => {
        const lists = await Promise.all(zones.map((z) => axios.get(`${API_BASE}/content/zones/${z.id}/rooms`).then((r) => r.data).catch(() => [])));
        if (alive) setRooms(lists.flat().map((r) => r.id).sort());
      })
      .catch(() => {});
    axios.get(`${API_BASE}/content/items`).then(({ data }) => alive && setItems(data)).catch(() => {});
    return () => { alive = false; };
  }, [characterId]);

  const act = async (label, fn) => {
    setBusy(true);
    setError("");
    setNote("");
    try {
      await fn();
      await reload();
      setNote(label);
      onChanged?.();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  if (error && !detail) return <div role="alert" style={{ color: COLORS.danger, fontSize: 13 }}>{error}</div>;
  if (!detail) return <div style={{ color: COLORS.textMuted, fontSize: 13 }}>Loading…</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, borderTop: `1px solid ${COLORS.border}`, paddingTop: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 17, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{detail.name}</span>
        <Badge color={detail.online ? COLORS.success : COLORS.textDim}>{detail.online ? "connected" : "offline"}</Badge>
        {detail.suspended && <Badge color={COLORS.danger}>account suspended</Badge>}
        <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: mono }}>
          account {detail.account} · {detail.room_id} · hp {detail.hp ?? "—"}/{detail.max_hp ?? "—"}
        </span>
        {detail.online && (
          <span style={{ marginLeft: "auto" }}>
            <ActionButton small variant="danger" disabled={busy} onClick={() => {
              if (window.confirm(`Disconnect ${detail.name}?`)) act("Disconnected.", () => axios.post(`${API_BASE}/admin/characters/${characterId}/kick`));
            }}>Kick</ActionButton>
          </span>
        )}
      </div>
      {error && <div role="alert" style={{ color: COLORS.danger, fontSize: 12, fontFamily: mono }}>Not done: {error}</div>}
      {note && <div style={{ color: COLORS.success, fontSize: 12, fontFamily: sans }}>{note}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 18 }}>
        <Section title="Move to room">
          <div style={{ display: "flex", gap: 8 }}>
            <input id={`char-${characterId}-room`} list={`char-${characterId}-rooms`} value={roomId} onChange={(e) => setRoomId(e.target.value)} placeholder="zone:room" style={{ ...input, flex: 1, fontFamily: mono }} aria-label="Room id" />
            <datalist id={`char-${characterId}-rooms`}>{rooms.map((r) => <option key={r} value={r} />)}</datalist>
            <ActionButton small variant="primary" disabled={busy || !roomId || roomId === detail.room_id} onClick={() => act(`Moved to ${roomId}.`, () => axios.post(`${API_BASE}/admin/characters/${characterId}/move`, { room_id: roomId }))}>Move</ActionButton>
          </div>
        </Section>

        <Section title="Money">
          {detail.currencies.length === 0 && <div style={{ fontSize: 12, color: COLORS.textMuted }}>This world has no currencies.</div>}
          {detail.currencies.map((c) => (
            <div key={c.key} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <label htmlFor={`char-${characterId}-wallet-${c.key}`} style={{ fontSize: 13, color: COLORS.text, minWidth: 70 }}>{c.name}</label>
              <input id={`char-${characterId}-wallet-${c.key}`} type="number" min="0" step="1" value={amounts[c.key] ?? ""} onChange={(e) => setAmounts((a) => ({ ...a, [c.key]: e.target.value }))} style={{ ...input, width: 120, fontFamily: mono }} />
              <ActionButton small variant="primary" disabled={busy || String(c.balance) === amounts[c.key] || !/^\d+$/.test(amounts[c.key] || "")} onClick={() => act(`${c.name} set to ${amounts[c.key]}.`, () => axios.post(`${API_BASE}/admin/characters/${characterId}/wallet`, { currency: c.key, amount: Number(amounts[c.key]) }))}>Set</ActionButton>
            </div>
          ))}
        </Section>
      </div>

      <Section title={`Inventory (${detail.inventory.length})`}>
        {detail.inventory.length === 0 && <div style={{ fontSize: 12, color: COLORS.textMuted }}>Carrying nothing.</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {detail.inventory.map((it) => (
            <div key={it.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: COLORS.text }}>
              <span>{it.name || it.template}</span>
              <span style={{ fontFamily: mono, fontSize: 11, color: COLORS.textDim }}>{it.id}</span>
              <span style={{ marginLeft: "auto" }}>
                <ActionButton small variant="ghost" disabled={busy} onClick={() => {
                  if (window.confirm(`Remove ${it.name || it.template} from ${detail.name}?`)) act(`Removed ${it.name || it.template}.`, () => axios.delete(`${API_BASE}/admin/characters/${characterId}/items/${encodeURIComponent(it.id)}`));
                }}>Remove</ActionButton>
              </span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <input id={`char-${characterId}-give`} list={`char-${characterId}-items`} value={template} onChange={(e) => setTemplate(e.target.value)} placeholder="item template id" style={{ ...input, flex: 1, fontFamily: mono }} aria-label="Item template to give" />
          <datalist id={`char-${characterId}-items`}>{items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}</datalist>
          <ActionButton small variant="primary" disabled={busy || !template} onClick={() => act(`Gave ${template}.`, () => axios.post(`${API_BASE}/admin/characters/${characterId}/items`, { template }))}>Give</ActionButton>
        </div>
      </Section>
      <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: sans }}>Every change here is recorded in the audit log, and a connected player sees a notice.</div>
    </div>
  );
}

const PAGE = 25;

export default function CharacterTools() {
  const { colors: COLORS } = useAdminTheme();
  // #/characters/<id> opens that character.
  const [parts, go] = useHashParts();
  const selected = Number(parts[0]) > 0 ? Number(parts[0]) : null;
  const [query, setQuery] = useState("");
  const q = useDebounced(query);
  const [zone, setZone] = useState("");
  const [online, setOnline] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [zones, setZones] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const params = { q, zone, limit: PAGE, offset, ...(online ? { online: online === "yes" } : {}) };
    axios.get(`${API_BASE}/admin/characters`, { params })
      .then(({ data: d }) => { if (alive) { setData(d); setError(""); } })
      .catch((e) => alive && setError(errorText(e)));
    return () => { alive = false; };
  }, [q, zone, online, offset]);

  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/content/zones`).then(({ data: d }) => alive && setZones(d)).catch(() => {});
    return () => { alive = false; };
  }, []);

  const select = { padding: "7px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 8, color: COLORS.text, fontSize: 13 };
  const rows = data?.rows || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <SearchBar placeholder="Find a character or account…" value={query} onChange={(v) => { setQuery(v); setOffset(0); }} />
        <select id="characters-zone" aria-label="Zone" value={zone} onChange={(e) => { setZone(e.target.value); setOffset(0); }} style={select}>
          <option value="">every zone</option>
          {zones.map((z) => <option key={z.id} value={z.id}>{z.id}</option>)}
        </select>
        <select id="characters-online" aria-label="Connected" value={online} onChange={(e) => { setOnline(e.target.value); setOffset(0); }} style={select}>
          <option value="">online or not</option>
          <option value="yes">online now</option>
          <option value="no">offline</option>
        </select>
        <span style={{ marginLeft: "auto" }}><Pager offset={offset} limit={PAGE} total={data?.total || 0} onOffset={setOffset} /></span>
      </div>
      {error && <div role="alert" style={{ color: COLORS.danger, fontSize: 12 }}>{error}</div>}
      {selected != null && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div><ActionButton small variant="ghost" onClick={() => go()}>Close</ActionButton></div>
          <CharacterDetail key={selected} characterId={selected} />
        </div>
      )}
      <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, overflow: "hidden" }}>
        <DataTable columns={[
          { label: "Character", render: (r) => <span style={{ fontWeight: 600 }}>{r.name}</span> },
          { label: "Account", render: (r) => <a href={`#/accounts/${r.account_id}`} onClick={(e) => e.stopPropagation()} style={{ color: COLORS.accent, fontFamily: mono, fontSize: 12 }}>{r.account}</a> },
          { label: "Room", key: "room_id", mono: true },
          { label: "", render: (r) => (
            <span style={{ display: "inline-flex", gap: 6 }}>
              {r.online && <Badge color={COLORS.success}>online</Badge>}
              {r.suspended && <Badge color={COLORS.danger}>suspended</Badge>}
            </span>
          ) },
        ]} rows={rows} onRowClick={(r) => go(r.id)} />
        {data && rows.length === 0 && <div style={{ padding: 14, fontSize: 12, color: COLORS.textMuted }}>No characters match.</div>}
      </div>
    </div>
  );
}
