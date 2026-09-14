import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE, WS_BASE } from "../apiConfig.js";
import { useWorldSummary } from "../useWorldSummary.js";
import {
  LS_ADMIN_TOKEN, ALL_ADMIN_TOOLS, adminWsBase, adminPresenceWsUrl, adminLogsWsUrl,
  sendWsAuthToken, parseLeadingInt, parseRoomType, extractYamlRoomId, Icons,
  Badge, StatusDot, Pill, ActionButton, PlannedAction, SearchBar, TabBar,
  DataTable, StatCard, usePolledList, FetchErrorBanner,
} from "../adminCommon.jsx";


const DashboardPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [time, setTime] = useState(new Date());
  const [serverStatus, setServerStatus] = useState({
    is_running: false, tick_count: 0, active_sessions: 0, uptime_seconds: 0,
  });
  const [sessions, setSessions] = useState([]);
  const [activityLog, setActivityLog] = useState([]);
  const [overview, setOverview] = useState(null);
  const { summary } = useWorldSummary();

  const syncNexus = useCallback(async () => {
    try {
      const [statusRes, playersRes] = await Promise.all([
        axios.get(`${API_BASE}/status`),
        axios.get(`${API_BASE}/players`),
      ]);
      setServerStatus(statusRes.data);
      setSessions(playersRes.data);
    } catch {
      /* keep last good values */
    }
  }, []);

  const syncOverview = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/content/overview`);
      setOverview(data);
    } catch {
      setOverview(null);
    }
  }, []);

  useEffect(() => {
    syncNexus();
    const id = setInterval(syncNexus, 5000);
    return () => clearInterval(id);
  }, [syncNexus]);

  useEffect(() => {
    syncOverview();
    const id = setInterval(syncOverview, 15000);
    return () => clearInterval(id);
  }, [syncOverview]);

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const ws = new WebSocket(adminLogsWsUrl());
    ws.onopen = () => sendWsAuthToken(ws);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "log") {
          setActivityLog((prev) => [
            { time: new Date().toLocaleTimeString(), type: data.level === "error" || data.level === "critical" ? "danger" : data.level === "warning" ? "warning" : "info", msg: data.content },
            ...prev.slice(0, 120),
          ]);
        }
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, []);

  const occupiedRooms = new Set((sessions || []).map((p) => p.room_id).filter(Boolean)).size;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{summary?.world?.name || "World overview"}</h2>
          {summary?.world && (
            <p style={{ margin: "2px 0 0", fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>
              world {summary.world.id} {summary.world.version} · {summary.world.path} · {summary.plugins?.length ?? 0} plugins
            </p>
          )}
          <p style={{ margin: "4px 0 0", fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>
            Local time {time.toLocaleTimeString()} · ticks {serverStatus.tick_count}
            {typeof serverStatus.uptime_seconds === "number" && serverStatus.uptime_seconds > 0 && (
              <span style={{ color: COLORS.textDim }}>
                {" "}· sim uptime {Math.floor(serverStatus.uptime_seconds / 60)}m
              </span>
            )}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <StatusDot color={serverStatus.is_running ? COLORS.success : COLORS.danger} pulse={serverStatus.is_running} />
          <span style={{ fontSize: 12, color: serverStatus.is_running ? COLORS.success : COLORS.danger, fontWeight: 600, fontFamily: "'DM Sans', sans-serif" }}>
            {serverStatus.is_running ? "Engine online" : "Nexus unreachable"}
          </span>
          {summary?.engine?.version && (
            <span style={{ fontSize: 11, color: COLORS.textDim, padding: "0 8px", fontFamily: "'JetBrains Mono', monospace" }} title="SAGE engine version">SAGE {summary.engine.version}</span>
          )}
        </div>
      </div>
      {/* DEV-AUTH:BEGIN */}
      {summary?.dev_login && (
        <div style={{ padding: "10px 14px", borderRadius: 8, border: `1px dashed ${COLORS.warning}`, background: COLORS.warningBg, color: COLORS.warning, fontSize: 12, fontFamily: "'DM Sans', sans-serif" }}>
          Passwordless dev logins are on (server.dev_login). Local development only: turn it off on any shared or networked host.
        </div>
      )}
      {/* DEV-AUTH:END */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
        <StatCard label="Players online" value={String(summary?.online?.players ?? serverStatus.active_sessions)} color={COLORS.success} icon={<Icons.Players />} />
        {(summary?.online?.agents ?? 0) > 0 && (
          <StatCard label="Agents online" value={String(summary.online.agents)} color={COLORS.info} icon={<Icons.Players />} title="Computer-controlled characters (agents plugin)" />
        )}
        <StatCard label="Rooms w/ players" value={String(occupiedRooms)} color={COLORS.accent} icon={<Icons.Map />} title="Distinct room_id values from Redis for authenticated sessions" />
        <StatCard label="Zones / Rooms" value={overview ? `${overview.zone_count} / ${overview.room_count}` : "—"} color={COLORS.info} icon={<Icons.World />} />
        <StatCard label="Entity templates" value={overview ? String(overview.entity_templates ?? 0) : "—"} color={COLORS.warning} icon={<Icons.Entities />} title="Distinct spawn definitions across room YAML" />
        <StatCard label="Spawn placements" value={overview ? String(overview.entity_spawn_references ?? 0) : "—"} color={COLORS.warning} icon={<Icons.Activity />} title="Total entity spawn reference counts summed from rooms" />
        <StatCard label="Items" value={overview ? String(overview.item_count) : "—"} color={COLORS.cyan} icon={<Icons.Items />} />
      </div>

      {overview?.zones?.length > 0 && (
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: "14px 16px" }}>
          <h3 style={{ margin: "0 0 10px", fontSize: 13, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Largest zones (by room files)</h3>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 20px", fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: COLORS.textMuted }}>
            {[...overview.zones].sort((a, b) => (b.rooms || 0) - (a.rooms || 0)).slice(0, 8).map((z) => (
              <span key={z.id} title={z.name || z.id}><strong style={{ color: COLORS.text }}>{z.id}</strong> · {z.rooms ?? 0} rooms</span>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif", display: "flex", alignItems: "center", gap: 8 }}><Icons.Terminal /> Live Activity</h3>
            <Badge color={activityLog.length ? COLORS.success : COLORS.textDim}>{activityLog.length ? "live" : "waiting"}</Badge>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 280, overflowY: "auto", fontFamily: "'JetBrains Mono', monospace", fontSize: 11.5 }}>
            {activityLog.length === 0 && (
              <div style={{ padding: "12px 8px", color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", fontSize: 12, lineHeight: 1.5 }}>
                No warnings or errors since you opened this page. Server log lines at WARNING and above appear here as they happen.
              </div>
            )}
            {activityLog.map((entry, i) => (
              <div key={i} style={{ display: "flex", gap: 10, padding: "6px 8px", borderRadius: 4, background: i === 0 ? `${COLORS.accent}08` : "transparent" }}>
                <span style={{ color: COLORS.textDim, flexShrink: 0 }}>{entry.time}</span>
                <StatusDot color={entry.type === "success" ? COLORS.success : entry.type === "warning" ? COLORS.warning : entry.type === "danger" ? COLORS.danger : COLORS.info} />
                <span style={{ color: COLORS.text, lineHeight: 1.5 }}>{entry.msg}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif", display: "flex", alignItems: "center", gap: 8 }}><Icons.Content /> Plugins loaded</h3>
          {!summary && <div style={{ fontSize: 12, color: COLORS.textMuted }}>Loading…</div>}
          {summary && summary.plugins.length === 0 && (
            <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>This world enables no plugins. Enable them in its world.toml [plugins].</div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 280, overflowY: "auto" }}>
            {(summary?.plugins || []).map((pl) => (
              <div key={pl.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontFamily: "'JetBrains Mono', monospace", padding: "4px 2px" }} title={pl.path}>
                <span style={{ color: COLORS.text, fontWeight: 600 }}>{pl.id}</span>
                <span style={{ color: COLORS.textDim }}>{pl.version}</span>
                <span style={{ marginLeft: "auto" }}>
                  <Badge color={pl.source === "world" ? COLORS.accent : COLORS.info}>{pl.source === "world" ? "world plugin" : "shared"}</Badge>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div style={{ fontSize: 13, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>
          <strong>{sessions.length}</strong> player session{sessions.length === 1 ? "" : "s"} online
          {sessions.length > 0 && (
            <span style={{ color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
              {" · "}{sessions.slice(0, 6).map((p) => p.player_id || "guest").join(", ")}{sessions.length > 6 ? "…" : ""}
            </span>
          )}
        </div>
        <a href="#/players" style={{ fontSize: 12, color: COLORS.accent, fontFamily: "'DM Sans', sans-serif" }}>Open Players &amp; sessions</a>
      </div>
    </div>
  );
};

export default DashboardPage;
