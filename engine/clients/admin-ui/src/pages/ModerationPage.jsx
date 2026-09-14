import { useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { ActionButton, DataTable, FetchErrorBanner } from "../adminCommon.jsx";
import Pager from "../pager.jsx";

// Players › Moderation: whether new accounts may be made, whether sign-in addresses are recorded
// (off by default: personal data, rules differ by country), address bans, and sign-in history.
// Mutes and a single account's history are on the account (Players › Accounts).

const mono = "'JetBrains Mono', monospace";
const errorText = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg).join("; ");
  return e?.message || "Request failed";
};

function Card({ title, children }) {
  const { colors: COLORS } = useAdminTheme();
  return (
    <section style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
      <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: COLORS.text }}>{title}</h3>
      {children}
    </section>
  );
}

function Settings() {
  const { colors: COLORS } = useAdminTheme();
  const [rules, setRules] = useState(null);
  const [days, setDays] = useState("");
  const [note, setNote] = useState(null);
  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/admin/moderation/settings`)
      .then(({ data }) => { if (alive) { setRules(data); setDays(String(data.login_history_days)); } })
      .catch((e) => alive && setNote({ ok: false, text: errorText(e) }));
    return () => { alive = false; };
  }, []);
  const save = async (patch, message) => {
    setNote(null);
    try {
      const { data } = await axios.patch(`${API_BASE}/admin/moderation/settings`, patch);
      setRules(data);
      setDays(String(data.login_history_days));
      setNote({ ok: true, text: message });
    } catch (e) {
      setNote({ ok: false, text: errorText(e) });
    }
  };
  if (!rules) return <Card title="Settings">{note ? <div style={{ color: COLORS.danger, fontSize: 12 }}>{note.text}</div> : "Loading…"}</Card>;
  const row = { display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" };
  return (
    <Card title="Settings">
      <div style={row}>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14, color: COLORS.text, cursor: "pointer" }}>
          <input id="moderation-registration" type="checkbox" checked={rules.registration_open}
            onChange={(e) => save({ registration_open: e.target.checked }, e.target.checked ? "New accounts can be made." : "New accounts are closed. Existing players can still sign in.")} />
          New players can create accounts
        </label>
      </div>
      <div style={{ ...row, flexDirection: "column", gap: 6 }}>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14, color: COLORS.text, cursor: "pointer" }}>
          <input id="moderation-record-addresses" type="checkbox" checked={rules.record_login_addresses}
            onChange={(e) => {
              const on = e.target.checked;
              if (on && !window.confirm("Record the network address of every sign-in?\n\nAddresses are personal data in many countries. Check the rules where you and your players are before turning this on. Players will see a notice on the sign-in screen.")) return;
              save({ record_login_addresses: on }, on ? "Sign-in addresses are now recorded. Players see a notice when they sign in." : "Sign-in addresses are no longer recorded. Addresses already stored age out, or erase them below.");
            }} />
          Record sign-in addresses
        </label>
        <div style={{ fontSize: 12, color: COLORS.textMuted, maxWidth: 720, lineHeight: 1.5 }}>
          Off by default. When on, every sign-in stores the address it came from, so staff can see linked accounts and choose what to ban. Players are told on the sign-in screen. Sign-in history (times, and addresses when recorded) is deleted after the number of days below. You are responsible for meeting the privacy rules that apply to you.
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, color: COLORS.text }}>
          <label htmlFor="moderation-days">Keep sign-in history for</label>
          <input id="moderation-days" type="number" min="1" max="3650" value={days} onChange={(e) => setDays(e.target.value)}
            style={{ width: 80, padding: "5px 8px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontFamily: mono }} />
          days
          <ActionButton small variant="primary" disabled={String(rules.login_history_days) === days || !/^\d+$/.test(days)} onClick={() => save({ login_history_days: Number(days) }, `Sign-in history is kept for ${days} days.`)}>Save</ActionButton>
        </div>
      </div>
      {note && <div role="status" style={{ fontSize: 12, color: note.ok ? COLORS.success : COLORS.danger }}>{note.text}</div>}
      <div style={{ fontSize: 11, color: COLORS.textDim }}>Saved to config/moderation.toml.</div>
    </Card>
  );
}

function Bans() {
  const { colors: COLORS } = useAdminTheme();
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ network: "", reason: "", days: "" });
  const [note, setNote] = useState(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/admin/moderation/bans`).then(({ data }) => alive && setRows(data)).catch((e) => alive && setNote({ ok: false, text: errorText(e) }));
    return () => { alive = false; };
  }, [version]);
  const add = async (e) => {
    e.preventDefault();
    setNote(null);
    try {
      const { data } = await axios.post(`${API_BASE}/admin/moderation/bans`, { network: form.network, reason: form.reason, days: form.days ? Number(form.days) : null });
      setNote({ ok: true, text: `Banned ${data.network}.` });
      setForm({ network: "", reason: "", days: "" });
      setVersion((v) => v + 1);
    } catch (err) {
      setNote({ ok: false, text: errorText(err) });
    }
  };
  const remove = async (ban) => {
    if (!window.confirm(`Lift the ban on ${ban.network}?`)) return;
    try {
      await axios.delete(`${API_BASE}/admin/moderation/bans/${ban.id}`);
      setVersion((v) => v + 1);
    } catch (err) {
      setNote({ ok: false, text: errorText(err) });
    }
  };
  const input = { padding: "7px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13 };
  return (
    <Card title="Address bans">
      <div style={{ fontSize: 12, color: COLORS.textMuted }}>A banned address or range (for example <code>203.0.113.7</code> or <code>203.0.113.0/24</code>) cannot sign in, create accounts or connect to play. Works whether or not addresses are recorded.</div>
      <form onSubmit={add} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input id="ban-network" aria-label="Address or range" placeholder="address or range" value={form.network} onChange={(e) => setForm((f) => ({ ...f, network: e.target.value }))} style={{ ...input, fontFamily: mono, width: 200 }} />
        <input id="ban-reason" aria-label="Reason" placeholder="reason" value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} style={{ ...input, flex: 1, minWidth: 180 }} />
        <input id="ban-days" aria-label="Days (empty for no end)" placeholder="days (empty: no end)" type="number" min="1" value={form.days} onChange={(e) => setForm((f) => ({ ...f, days: e.target.value }))} style={{ ...input, width: 170 }} />
        <button type="submit" disabled={!form.network.trim()} style={{ padding: "7px 14px", background: COLORS.danger, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, fontSize: 12, cursor: "pointer" }}>Ban</button>
      </form>
      {note && <div role="status" style={{ fontSize: 12, color: note.ok ? COLORS.success : COLORS.danger }}>{note.text}</div>}
      {rows.length === 0 ? <div style={{ fontSize: 12, color: COLORS.textDim }}>No bans.</div> : (
        <DataTable columns={[
          { label: "Address or range", key: "network", mono: true },
          { label: "Reason", key: "reason" },
          { label: "By", key: "created_by", mono: true },
          { label: "Ends", render: (b) => <span style={{ fontFamily: mono, fontSize: 12, color: b.active ? COLORS.text : COLORS.textDim }}>{b.expires_at ? new Date(b.expires_at).toLocaleDateString() : "never"}{b.active ? "" : " (ended)"}</span> },
          { label: "", render: (b) => <ActionButton small variant="ghost" onClick={() => remove(b)}>Lift</ActionButton> },
        ]} rows={rows} />
      )}
    </Card>
  );
}

function History() {
  const { colors: COLORS } = useAdminTheme();
  const [address, setAddress] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/admin/moderation/logins`, { params: { address: query, limit: 50, offset } })
      .then(({ data: d }) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => alive && setError(errorText(e)));
    return () => { alive = false; };
  }, [query, offset, version]);
  const eraseAll = async () => {
    if (!window.confirm("Erase every stored sign-in address? Sign-in times stay. This cannot be undone.")) return;
    try {
      const { data: d } = await axios.post(`${API_BASE}/admin/moderation/erase-addresses`);
      window.alert(`Erased ${d.erased} address${d.erased === 1 ? "" : "es"}.`);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(errorText(e));
    }
  };
  return (
    <Card title="Sign-in history">
      <form onSubmit={(e) => { e.preventDefault(); setOffset(0); setQuery(address.trim()); }} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input id="history-address" aria-label="Address or range" placeholder="filter by address or range" value={address} onChange={(e) => setAddress(e.target.value)}
          style={{ padding: "7px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13, fontFamily: mono, width: 240 }} />
        <button type="submit" style={{ padding: "7px 14px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, fontSize: 12, cursor: "pointer" }}>Filter</button>
        <span style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center" }}>
          <Pager offset={offset} limit={50} total={data?.total || 0} onOffset={setOffset} />
          <ActionButton small variant="danger" onClick={eraseAll}>Erase all addresses</ActionButton>
        </span>
      </form>
      <FetchErrorBanner error={error} label="sign-in history" />
      {data && data.rows.length === 0 && <div style={{ fontSize: 12, color: COLORS.textDim }}>No sign-ins{query ? " from that address" : ""}.</div>}
      {data && data.rows.length > 0 && (
        <DataTable columns={[
          { label: "When", render: (r) => <span style={{ fontFamily: mono, fontSize: 12 }}>{new Date(r.at).toLocaleString()}</span> },
          { label: "Account", render: (r) => <a href={`#/accounts/${r.account_id}`} style={{ color: COLORS.accent }}>{r.account}</a> },
          { label: "How", key: "method", mono: true },
          { label: "Address", render: (r) => r.address ? <button type="button" onClick={() => { setAddress(r.address); setOffset(0); setQuery(r.address); }} style={{ all: "unset", cursor: "pointer", color: COLORS.accent, fontFamily: mono, fontSize: 12 }} title="Show every sign-in from this address">{r.address}</button> : <span style={{ color: COLORS.textDim, fontSize: 12 }}>not recorded</span> },
        ]} rows={data.rows} />
      )}
    </Card>
  );
}

export default function ModerationPage() {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 1100 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Moderation</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>Mute or suspend a player, and see one account&apos;s sign-ins, from Players › Accounts. Player reports are under Players › Reports.</p>
      </div>
      <Settings />
      <Bans />
      <History />
    </div>
  );
}
