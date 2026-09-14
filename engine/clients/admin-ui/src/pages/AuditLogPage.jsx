import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { ActionButton, DataTable, FetchErrorBanner } from "../adminCommon.jsx";

// Audit log: every staff change made through the console (GET /admin/audit), newest first.

const mono = "'JetBrains Mono', monospace";
const sans = "'DM Sans', sans-serif";
const PAGE = 100;

function summary(detail) {
  const parts = [];
  for (const [k, v] of Object.entries(detail || {})) {
    if (v == null || (typeof v === "object" && Object.keys(v).length === 0)) continue;
    parts.push(`${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`);
  }
  return parts.join(" · ");
}

export default function AuditLogPage() {
  const { colors: COLORS } = useAdminTheme();
  const [rows, setRows] = useState([]);
  const [filters, setFilters] = useState({ action: "", staff: "", target: "" });
  const [applied, setApplied] = useState({ action: "", staff: "", target: "" });
  const [error, setError] = useState(null);
  const [more, setMore] = useState(false);
  const [open, setOpen] = useState(null);
  const input = { padding: "7px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13, fontFamily: sans };

  const fetchPage = useCallback((before) =>
    axios.get(`${API_BASE}/admin/audit`, { params: { limit: PAGE, before: before ?? undefined, ...applied } }).then((r) => r.data),
  [applied]);

  useEffect(() => {
    let alive = true;
    fetchPage(null)
      .then((data) => { if (alive) { setRows(data); setMore(data.length === PAGE); setError(null); } })
      .catch((e) => alive && setError(e?.response?.data?.detail || e.message));
    return () => { alive = false; };
  }, [fetchPage]);

  const loadOlder = async () => {
    try {
      const data = await fetchPage(rows[rows.length - 1]?.id);
      setRows((r) => [...r, ...data]);
      setMore(data.length === PAGE);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Audit log</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: sans, maxWidth: 820, lineHeight: 1.5 }}>
          Every change staff make through this console: accounts, characters, staff, lexicon, templates, rooms, spawns and settings. Passwords and tokens are never stored.
        </p>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); setApplied(filters); }} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input id="audit-action" aria-label="Action starts with" placeholder="action (e.g. character. or PATCH)" value={filters.action} onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value }))} style={{ ...input, minWidth: 220 }} />
        <input id="audit-staff" aria-label="Staff login" placeholder="staff login" value={filters.staff} onChange={(e) => setFilters((f) => ({ ...f, staff: e.target.value }))} style={input} />
        <input id="audit-target" aria-label="Target contains" placeholder="target contains" value={filters.target} onChange={(e) => setFilters((f) => ({ ...f, target: e.target.value }))} style={input} />
        <button type="submit" style={{ padding: "7px 14px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, fontSize: 12, cursor: "pointer" }}>Filter</button>
      </form>
      <FetchErrorBanner error={error} label="audit log" />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable
          onRowClick={(r) => setOpen((cur) => (cur === r.id ? null : r.id))}
          columns={[
            { label: "When", render: (r) => <span style={{ fontFamily: mono, fontSize: 12 }}>{r.at ? new Date(r.at).toLocaleString() : "—"}</span> },
            { label: "Staff", key: "staff", mono: true },
            { label: "Action", render: (r) => <span style={{ fontFamily: mono, fontSize: 12 }}>{r.action}</span> },
            { label: "Target", render: (r) => <span style={{ fontFamily: mono, fontSize: 12 }}>{r.target}</span> },
            { label: "Details", render: (r) => (
              <span style={{ display: "inline-block", maxWidth: 420, whiteSpace: open === r.id ? "pre-wrap" : "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontSize: 12, color: COLORS.textMuted, fontFamily: mono, verticalAlign: "top" }}>
                {open === r.id ? JSON.stringify(r.detail, null, 2) : summary(r.detail)}
              </span>
            ) },
          ]}
          rows={rows}
        />
        {rows.length === 0 && !error && <div style={{ padding: 16, fontSize: 13, color: COLORS.textMuted, fontFamily: sans }}>No staff actions recorded{applied.action || applied.staff || applied.target ? " for these filters" : " yet"}.</div>}
      </div>
      {more && <div><ActionButton small variant="ghost" onClick={loadOlder}>Load older</ActionButton></div>}
    </div>
  );
}
