import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { Badge, ActionButton, DataTable } from "../adminCommon.jsx";

// Tool ids the server checks, in sidebar order, with what each one opens.
// entities and items are separate grants that the Content Library combines.
const TOOL_GROUPS = [
  ["Overview", [["dashboard", "Dashboard"]]],
  ["Live", [["operations", "Broadcast, reload, live world, audit log"]]],
  ["Players", [["players", "Who's online, characters, accounts"]]],
  ["World", [["world", "World & plugins, rooms, live world"], ["content", "Content Library"], ["entities", "Creature templates"], ["items", "Item templates"], ["skills", "Skills catalog"], ["lexicon", "Lexicon & MOTD"], ["forge", "AI Forge"]]],
  ["Economy & NPCs", [["shops", "Shops"], ["agents", "Agents"]]],
  ["System", [["server", "Server, AI models, AI art credits"], ["team", "Team & access (head admins)"]]],
];

const parseZones = (raw) => {
  const z = (raw || "").trim();
  return z === "*" || z === "" ? ["*"] : z.split(",").map((x) => x.trim()).filter(Boolean);
};

const sameTools = (a, b) => a.length === b.length && a.every((t) => b.includes(t));

// presets come from GET /admin/staff/tool-presets; choosing one replaces the ticked tools.
function ToolPicker({ tools, onToggle, onPreset, presets = [], idPrefix }) {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ display: "grid", gap: 10 }}>
    {presets.length > 0 && (
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, color: COLORS.textMuted }}>Start from a role:</span>
        {presets.map((p) => {
          const active = sameTools(tools, p.tools);
          return (
            <button key={p.id} type="button" title={p.description} aria-pressed={active} onClick={() => onPreset(p.tools)}
              style={{ padding: "4px 10px", borderRadius: 999, fontSize: 12, cursor: "pointer", color: active ? COLORS.accent : COLORS.text, background: active ? COLORS.accentGlow : COLORS.bgInput, border: `1px solid ${active ? COLORS.accent : COLORS.border}` }}>{p.label}</button>
          );
        })}
      </div>
    )}
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "10px 16px" }}>
      {TOOL_GROUPS.map(([group, items]) => (
        <fieldset key={group} style={{ border: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          <legend style={{ fontSize: 10, fontWeight: 600, color: COLORS.textDim, textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: "'JetBrains Mono', monospace", marginBottom: 2 }}>{group}</legend>
          {items.map(([tid, label]) => (
            <label key={tid} htmlFor={`${idPrefix}-${tid}`} style={{ fontSize: 12, color: COLORS.text, display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }} title={tid}>
              <input id={`${idPrefix}-${tid}`} type="checkbox" checked={tools.includes(tid)} onChange={() => onToggle(tid)} />
              {label}
            </label>
          ))}
        </fieldset>
      ))}
    </div>
    </div>
  );
}

function StaffEditor({ row, presets, onCancel, onSaved }) {
  const { colors: COLORS } = useAdminTheme();
  const [displayName, setDisplayName] = useState(row.display_name || "");
  const [role, setRole] = useState(row.role);
  const [zones, setZones] = useState((row.permissions?.zones || ["*"]).join(", "));
  const [tools, setTools] = useState(row.permissions?.tools || []);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const input = { padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text };

  const toggle = (tid) => setTools((t) => (t.includes(tid) ? t.filter((x) => x !== tid) : [...t, tid]));

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const patch = { display_name: displayName.trim(), role, permissions: { ...(row.permissions || {}), tools, zones: parseZones(zones) } };
    if (password) patch.password = password;
    try {
      await axios.patch(`${API_BASE}/admin/staff/${row.id}`, patch);
      onSaved();
    } catch (ex) {
      const d = ex.response?.data?.detail;
      setError(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : ex.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={save} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.borderActive}`, borderRadius: 10, padding: 18, marginBottom: 20, display: "grid", gap: 12 }}>
      <h3 style={{ margin: 0, fontSize: 14, color: COLORS.text }}>Edit {row.display_name} <span style={{ fontFamily: "'JetBrains Mono', monospace", color: COLORS.textDim, fontWeight: 400 }}>{row.username}</span></h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
        <label style={{ display: "grid", gap: 4, fontSize: 11, color: COLORS.textMuted }}>Display name
          <input id={`staff-${row.id}-name`} value={displayName} onChange={(e) => setDisplayName(e.target.value)} style={input} />
        </label>
        <label style={{ display: "grid", gap: 4, fontSize: 11, color: COLORS.textMuted }}>Role
          <select id={`staff-${row.id}-role`} value={role} onChange={(e) => setRole(e.target.value)} style={input}>
            <option value="gm">GM</option>
            <option value="admin">Admin</option>
            <option value="head_admin">Head admin (every tool and zone)</option>
          </select>
        </label>
        <label style={{ display: "grid", gap: 4, fontSize: 11, color: COLORS.textMuted }}>Zones (* or ids, comma-separated)
          <input id={`staff-${row.id}-zones`} value={zones} onChange={(e) => setZones(e.target.value)} style={input} />
        </label>
        <label style={{ display: "grid", gap: 4, fontSize: 11, color: COLORS.textMuted }}>New password (leave empty to keep)
          <input id={`staff-${row.id}-password`} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} style={input} />
        </label>
      </div>
      {role === "head_admin"
        ? <div style={{ fontSize: 12, color: COLORS.textMuted }}>Head admins can use every tool, so the tool list does not apply.</div>
        : <ToolPicker tools={tools} onToggle={toggle} onPreset={(t) => setTools([...t])} presets={presets} idPrefix={`staff-${row.id}-tool`} />}
      {error && <div role="alert" style={{ color: COLORS.danger, fontSize: 12 }}>Not saved: {error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" disabled={busy} style={{ padding: "6px 14px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, fontSize: 12, cursor: busy ? "wait" : "pointer" }}>{busy ? "Saving…" : "Save changes"}</button>
        <ActionButton small variant="ghost" onClick={onCancel}>Cancel</ActionButton>
      </div>
    </form>
  );
}


const StaffTeamPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [rows, setRows] = useState([]);
  const [loadErr, setLoadErr] = useState("");
  const [form, setForm] = useState({
    username: "", password: "", display_name: "", role: "gm", tools: ["dashboard", "players"], zones: "*",
  });
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [presets, setPresets] = useState([]);

  const load = useCallback(async () => {
    setLoadErr("");
    try {
      const { data } = await axios.get(`${API_BASE}/admin/staff`);
      setRows(data);
    } catch (e) {
      setLoadErr(e.response?.data?.detail || e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    axios.get(`${API_BASE}/admin/staff/tool-presets`).then(({ data }) => setPresets(Array.isArray(data) ? data : [])).catch(() => {});
  }, []);

  const toggleTool = (id) => {
    setForm((f) => {
      const s = new Set(f.tools);
      if (s.has(id)) s.delete(id); else s.add(id);
      return { ...f, tools: [...s] };
    });
  };

  const createStaff = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const zones = parseZones(form.zones);
      await axios.post(`${API_BASE}/admin/staff`, {
        username: form.username.trim(),
        password: form.password,
        display_name: form.display_name.trim() || form.username.trim(),
        role: form.role,
        permissions: { tools: form.tools, zones },
      });
      setForm({ username: "", password: "", display_name: "", role: "gm", tools: ["dashboard", "players"], zones: "*" });
      await load();
    } catch (ex) {
      window.alert(ex.response?.data?.detail || ex.message);
    } finally {
      setBusy(false);
    }
  };

  const patchStaff = async (id, patch) => {
    try {
      await axios.patch(`${API_BASE}/admin/staff/${id}`, patch);
      await load();
    } catch (ex) {
      window.alert(ex.response?.data?.detail || ex.message);
    }
  };

  return (
    <div style={{ maxWidth: 960 }}>
      <h2 style={{ margin: "0 0 8px", fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Team &amp; access</h2>
      <p style={{ margin: "0 0 16px", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
        Head admins can add staff, assign roles (admin / GM), and restrict <strong>tools</strong> (sidebar areas) and <strong>zones</strong> (world regions for room edits / forge inject / live spawns).
        Use zones <code style={{ color: COLORS.textDim }}>*</code> for all zones, or comma-separated ids e.g. <code style={{ color: COLORS.textDim }}>test_zone</code>.
        {" "}Staff accounts are for this admin console only. A staff account whose name matches a <strong>play</strong> login that wears the <strong>GM crown</strong> (Players › Accounts) also gives that player in-game staff commands, limited by the tools and zones set here.
      </p>
      {loadErr && <div style={{ color: COLORS.danger, marginBottom: 12 }}>{loadErr}</div>}

      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, marginBottom: 20 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Add staff</h3>
        <form onSubmit={createStaff} style={{ display: "grid", gap: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
            <input placeholder="username" value={form.username} onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }} />
            <input type="password" placeholder="password" value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }} />
            <input placeholder="display name" value={form.display_name} onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }} />
            <select value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }}>
              <option value="gm">GM</option>
              <option value="admin">Admin</option>
              <option value="head_admin">Head admin</option>
            </select>
          </div>
          <input placeholder="Zones (* or zone_id, zone_id2)" value={form.zones} onChange={(e) => setForm((f) => ({ ...f, zones: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }} />
          <ToolPicker tools={form.tools} onToggle={toggleTool} onPreset={(t) => setForm((f) => ({ ...f, tools: [...t] }))} presets={presets} idPrefix="new-staff-tool" />
          <button type="submit" disabled={busy} style={{ alignSelf: "start", padding: "8px 16px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}>Create</button>
        </form>
      </div>

      {editingId != null && rows.some((r) => r.id === editingId) && (
        <StaffEditor
          key={editingId}
          row={rows.find((r) => r.id === editingId)}
          presets={presets}
          onCancel={() => setEditingId(null)}
          onSaved={async () => { setEditingId(null); await load(); }}
        />
      )}
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable
          columns={[
            { label: "User", render: (r) => <span style={{ fontWeight: 600 }}>{r.display_name}</span> },
            { label: "Login", key: "username", mono: true },
            { label: "Role", key: "role", mono: true },
            { label: "Active", render: (r) => <Badge color={r.is_active ? COLORS.success : COLORS.danger}>{r.is_active ? "yes" : "no"}</Badge> },
            { label: "Tools", render: (r) => <span style={{ fontSize: 10, color: COLORS.textDim }}>{r.role === "head_admin" ? "all" : (r.permissions?.tools || []).join(", ") || "—"}</span> },
            { label: "Zones", render: (r) => <span style={{ fontSize: 10, color: COLORS.textDim }}>{(r.permissions?.zones || []).join(", ") || "*"}</span> },
            { label: "", render: (r) => (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <ActionButton small variant="ghost" onClick={() => setEditingId(r.id)}>Edit</ActionButton>
                <ActionButton small variant="ghost" onClick={() => patchStaff(r.id, { is_active: !r.is_active })}>{r.is_active ? "Deactivate" : "Activate"}</ActionButton>
              </div>
            ) },
          ]}
          rows={rows}
        />
      </div>
    </div>
  );
};

export default StaffTeamPage;
