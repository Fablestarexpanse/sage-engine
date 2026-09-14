import { useState, useEffect } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { Icons, StatusDot, ActionButton, SearchBar, DataTable, FetchErrorBanner } from "../adminCommon.jsx";

// Live › Who's online: connected play sessions, refreshed every few seconds.

const OnlinePage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [search, setSearch] = useState("");
  const [sessions, setSessions] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () => axios.get(`${API_BASE}/players`)
      .then(({ data }) => { if (alive) { setSessions(data); setError(null); } })
      .catch((e) => alive && setError(e?.response?.data?.detail || e.message));
    load();
    const id = setInterval(load, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const disconnect = async (sessionId, name) => {
    if (!window.confirm(`Disconnect ${name}?`)) return;
    try {
      await axios.post(`${API_BASE}/admin/sessions/${sessionId}/disconnect`);
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message || "Disconnect failed");
    }
  };

  const rows = (sessions ?? []).map((p) => ({
    id: p.session_id,
    name: p.player_id || "guest",
    accountId: p.account_id ?? null,
    state: p.state ?? "playing",
    location: p.room_id || "—",
    peer: typeof p.peer === "string" ? p.peer : JSON.stringify(p.peer ?? "—"),
  })).filter((p) => String(p.name).toLowerCase().includes(search.toLowerCase()));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Who&apos;s online</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
            {sessions == null ? "Loading…" : `${sessions.length} connected session${sessions.length === 1 ? "" : "s"}`}. Refreshes every 5 seconds.
          </p>
        </div>
        <SearchBar placeholder="Filter by name…" value={search} onChange={setSearch} />
      </div>
      <FetchErrorBanner error={error} label="sessions" />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "auto" }}>
        <DataTable columns={[
          { label: "", render: () => <StatusDot color={COLORS.success} pulse /> },
          { label: "Name", render: (row) => <span style={{ fontWeight: 600 }}>{row.name}</span> },
          { label: "State", key: "state", mono: true },
          { label: "Room", key: "location", mono: true },
          { label: "Peer", key: "peer", mono: true },
          { label: "", render: (row) => (
            <div style={{ display: "flex", gap: 4 }}>
              {row.accountId != null && (
                <ActionButton small variant="ghost" title="Open game account" onClick={() => { window.location.hash = `/accounts/${row.accountId}`; }}><Icons.Eye /></ActionButton>
              )}
              <ActionButton small variant="ghost" title="Disconnect" onClick={() => disconnect(row.id, row.name)}><Icons.Alert /></ActionButton>
            </div>
          ) },
        ]} rows={rows} />
        {rows.length === 0 && sessions != null && <div style={{ padding: 16, fontSize: 13, color: COLORS.textMuted }}>Nobody is connected{search ? " with that name" : ""}.</div>}
      </div>
    </div>
  );
};

export default OnlinePage;
