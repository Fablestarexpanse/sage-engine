import { useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";
import { Badge, ActionButton, SearchBar } from "./adminCommon.jsx";

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

export default function CharacterTools() {
  const { colors: COLORS } = useAdminTheme();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      axios.get(`${API_BASE}/admin/characters`, { params: { q: query, limit: 25 } })
        .then(({ data }) => { if (alive) { setResults(data); setError(""); } })
        .catch((e) => alive && setError(errorText(e)));
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [query]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Characters</h3>
        <SearchBar placeholder="Find a character or account…" value={query} onChange={setQuery} />
      </div>
      {error && <div role="alert" style={{ color: COLORS.danger, fontSize: 12 }}>{error}</div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {results.map((r) => (
          <button key={r.id} type="button" onClick={() => setSelected(r.id)} aria-pressed={selected === r.id}
            style={{ padding: "6px 10px", borderRadius: 6, cursor: "pointer", fontSize: 13, fontFamily: sans, color: COLORS.text, background: selected === r.id ? COLORS.accentGlow : COLORS.bgInput, border: `1px solid ${selected === r.id ? COLORS.accent : COLORS.border}` }}>
            {r.name}
            <span style={{ color: COLORS.textDim, fontFamily: mono, fontSize: 11 }}> {r.account}{r.online ? " · online" : ""}{r.suspended ? " · suspended" : ""}</span>
          </button>
        ))}
        {results.length === 0 && !error && <span style={{ fontSize: 12, color: COLORS.textMuted }}>No characters match.</span>}
      </div>
      {selected != null && <CharacterDetail key={selected} characterId={selected} />}
    </div>
  );
}
