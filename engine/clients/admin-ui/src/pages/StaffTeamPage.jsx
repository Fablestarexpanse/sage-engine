import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE, WS_BASE } from "../apiConfig.js";
import {
  LS_ADMIN_TOKEN, ALL_ADMIN_TOOLS, adminWsBase, adminPresenceWsUrl, adminLogsWsUrl,
  sendWsAuthToken, parseLeadingInt, parseRoomType, extractYamlRoomId, Icons,
  Badge, StatusDot, Pill, ActionButton, PlannedAction, SearchBar, TabBar,
  DataTable, StatCard, usePolledList, FetchErrorBanner,
} from "../adminCommon.jsx";


const StaffTeamPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [rows, setRows] = useState([]);
  const [loadErr, setLoadErr] = useState("");
  const [form, setForm] = useState({
    username: "", password: "", display_name: "", role: "gm", tools: ["dashboard", "players"], zones: "*",
  });
  const [busy, setBusy] = useState(false);

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
      const zonesRaw = (form.zones || "").trim();
      const zones = zonesRaw === "*" || zonesRaw === "" ? ["*"] : zonesRaw.split(",").map((z) => z.trim()).filter(Boolean);
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
        {" "}Staff accounts are for this admin console only. To give a <strong>play</strong> login the in-game pink <strong>GM</strong> crown, use <strong>Players → Game accounts</strong> and enable <em>Game Master play account</em> on that row.
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
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {ALL_ADMIN_TOOLS.map((tid) => (
              <label key={tid} style={{ fontSize: 11, color: COLORS.textMuted, display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
                <input type="checkbox" checked={form.tools.includes(tid)} onChange={() => toggleTool(tid)} />
                {tid}
              </label>
            ))}
          </div>
          <button type="submit" disabled={busy} style={{ alignSelf: "start", padding: "8px 16px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}>Create</button>
        </form>
      </div>

      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable
          columns={[
            { label: "User", render: (r) => <span style={{ fontWeight: 600 }}>{r.display_name}</span> },
            { label: "Login", key: "username", mono: true },
            { label: "Role", key: "role", mono: true },
            { label: "Active", render: (r) => <Badge color={r.is_active ? COLORS.success : COLORS.danger}>{r.is_active ? "yes" : "no"}</Badge> },
            { label: "Tools", render: (r) => <span style={{ fontSize: 10, color: COLORS.textDim }}>{(r.permissions?.tools || []).join(", ") || "—"}</span> },
            { label: "Zones", render: (r) => <span style={{ fontSize: 10, color: COLORS.textDim }}>{(r.permissions?.zones || []).join(", ") || "*"}</span> },
            { label: "", render: (r) => (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
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
