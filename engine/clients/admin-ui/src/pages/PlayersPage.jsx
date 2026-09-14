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
import PlayerAccountsTab from "../PlayerAccountsTab.jsx";

const PlayersPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const accountsSectionRef = useRef(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [liveSessions, setLiveSessions] = useState(null);
  const [accountsFocus, setAccountsFocus] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/players`);
        setLiveSessions(data);
      } catch {
        setLiveSessions(null);
      }
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const disconnectSession = async (sessionId, name) => {
    if (!window.confirm(`Disconnect session ${sessionId.slice(0, 8)}… (${name})?`)) return;
    try {
      await axios.post(`${API_BASE}/admin/sessions/${sessionId}/disconnect`);
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message || "Disconnect failed");
    }
  };

  const tableRows = (liveSessions ?? []).map((p) => ({
    id: p.session_id,
    name: p.player_id || "guest",
    accountId: p.account_id ?? null,
    characterId: p.character_id ?? null,
    level: "—",
    class: p.state ?? "playing",
    status: "online",
    location: p.room_id || "—",
    zone: typeof p.peer === "string" ? p.peer : JSON.stringify(p.peer ?? "—"),
    glyphs: 0,
    lastSeen: "now",
    adaptiveLevel: 0,
  }));

  const filtered = tableRows.filter((p) =>
    (filter === "all" || p.status === filter) && String(p.name).toLowerCase().includes(search.toLowerCase())
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 style={{ margin: "0 0 8px", fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Player Management</h2>
        <p style={{ margin: 0, fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.55, maxWidth: 920 }}>
          <strong style={{ color: COLORS.info }}>Live sessions</strong> refresh every few seconds. <strong style={{ color: COLORS.forge }}>Game accounts</strong> below: pixels, bundles, in-game GM crown, <strong style={{ color: COLORS.text }}>Nexus console access</strong> for this play username, and characters. Team tab is for staff-only tools.
        </p>
      </div>

      <section style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Live sessions</h3>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <SearchBar placeholder="Search sessions..." value={search} onChange={setSearch} />
            <TabBar tabs={[{ id: "all", label: "All" }, { id: "online", label: "Online" }, { id: "offline", label: "Offline" }]} active={filter} onChange={setFilter} />
          </div>
        </div>
        <div style={{ borderRadius: 8, overflow: "auto", maxHeight: 360, border: `1px solid ${COLORS.border}` }}>
          <DataTable columns={[
            { label: "Status", render: row => <StatusDot color={row.status === "online" ? COLORS.success : row.status === "idle" ? COLORS.warning : COLORS.textDim} pulse={row.status === "online"} /> },
            { label: "Name", render: row => <span style={{ fontWeight: 600 }}>{row.name}</span> },
            { label: "State", key: "class", mono: true },
            { label: "Location", key: "location", mono: true, title: "room_id from Redis" },
            { label: "Level", key: "level", mono: true }, { label: "Glyphs", key: "glyphs", mono: true }, { label: "Peer", key: "zone", mono: true },
            { label: "Adaptive", render: row => (<div style={{ display: "flex", alignItems: "center", gap: 6 }}><div style={{ width: 60, height: 4, borderRadius: 2, background: COLORS.bgInput }}><div style={{ width: `${Math.min(100, (Number(row.adaptiveLevel) || 0) / 10 * 100)}%`, height: "100%", borderRadius: 2, background: row.adaptiveLevel > 7 ? COLORS.danger : row.adaptiveLevel > 4 ? COLORS.warning : COLORS.success }} /></div><span style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>{typeof row.adaptiveLevel === "number" ? row.adaptiveLevel.toFixed(1) : "—"}</span></div>) },
            { label: "Last Seen", key: "lastSeen", mono: true },
            { label: "", render: row => (
              <div style={{ display: "flex", gap: 4 }}>
                <ActionButton small variant="ghost" title="Force disconnect" onClick={(e) => { e.stopPropagation(); disconnectSession(row.id, row.name); }}><Icons.Alert /></ActionButton>
                <ActionButton
                  small
                  variant="ghost"
                  title="Open game account"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (row.accountId == null) {
                      window.alert("No Postgres account is linked to this session (guest, or character name not found in the database).");
                      return;
                    }
                    setAccountsFocus({ accountId: row.accountId, nonce: Date.now() });
                    accountsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                >
                  <Icons.Eye />
                </ActionButton>
              </div>
            ) },
          ]} rows={filtered} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
          <StatCard label="Live sessions" value={String(tableRows.length)} color={COLORS.info} icon={<Icons.Players />} />
          <StatCard label="Matches filter" value={String(filtered.length)} color={COLORS.accent} icon={<Icons.Search />} />
          <StatCard label="Players API" value={liveSessions === null ? "offline" : "ok"} color={liveSessions === null ? COLORS.danger : COLORS.success} icon={<Icons.Server />} />
        </div>
      </section>

      <section ref={accountsSectionRef}>
        <h3 style={{ margin: "0 0 14px", fontSize: 15, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Game accounts</h3>
        <PlayerAccountsTab focusTarget={accountsFocus} />
      </section>
    </div>
  );
};

export default PlayersPage;
