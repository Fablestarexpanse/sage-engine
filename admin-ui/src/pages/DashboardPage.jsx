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


const MiniMap = () => {
  const { colors: COLORS } = useAdminTheme();
  const rooms = [
    { x: 50, y: 10, type: "hub", label: "Entry" }, { x: 30, y: 30, type: "chamber" },
    { x: 70, y: 30, type: "chamber" }, { x: 20, y: 50, type: "corridor" },
    { x: 50, y: 45, type: "boss", label: "Archive" }, { x: 80, y: 50, type: "corridor" },
    { x: 10, y: 70, type: "dead_end" }, { x: 40, y: 70, type: "hazard" },
    { x: 60, y: 65, type: "chamber" }, { x: 90, y: 70, type: "dead_end" },
    { x: 30, y: 85, type: "corridor" }, { x: 50, y: 90, type: "hub", label: "Depths" }, { x: 70, y: 85, type: "corridor" },
  ];
  const connections = [[0,1],[0,2],[1,3],[1,4],[2,4],[2,5],[3,6],[3,7],[4,7],[4,8],[5,8],[5,9],[7,10],[8,12],[10,11],[11,12]];
  const tc = { hub: COLORS.accent, chamber: COLORS.info, corridor: COLORS.textMuted, boss: COLORS.warning, hazard: COLORS.danger, dead_end: COLORS.textDim };
  return (
    <svg viewBox="0 0 100 100" style={{ width: "100%", height: 200 }}>
      <defs><filter id="glow"><feGaussianBlur stdDeviation="2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      {connections.map(([a, b], i) => <line key={i} x1={rooms[a].x} y1={rooms[a].y} x2={rooms[b].x} y2={rooms[b].y} stroke={COLORS.border} strokeWidth="0.5" strokeDasharray="2,2" />)}
      {rooms.map((r, i) => (
        <g key={i}>
          <circle cx={r.x} cy={r.y} r={r.type === "hub" || r.type === "boss" ? 4 : 2.5} fill={tc[r.type]} opacity={0.8} filter={r.type === "hub" ? "url(#glow)" : undefined} />
          {r.label && <text x={r.x} y={r.y + 9} textAnchor="middle" fill={COLORS.textMuted} fontSize="4" fontFamily="'DM Sans', sans-serif">{r.label}</text>}
        </g>
      ))}
    </svg>
  );
};

const DashboardPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [time, setTime] = useState(new Date());
  const [serverStatus, setServerStatus] = useState({
    is_running: false, tick_count: 0, active_sessions: 0, uptime_seconds: 0,
  });
  const [sessions, setSessions] = useState([]);
  const [activityLog, setActivityLog] = useState([]);
  const [overview, setOverview] = useState(null);

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
            { time: new Date().toLocaleTimeString(), type: "info", msg: data.content },
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

  const onlineFromApi = sessions.map((p) => ({
    id: p.session_id,
    name: p.player_id || "guest",
    level: "—",
    class: p.state ?? "playing",
    status: "online",
    location: p.room_id || "—",
    peer: typeof p.peer === "string" ? p.peer : JSON.stringify(p.peer ?? "—"),
    glyphs: 0,
    lastSeen: "now",
    adaptiveLevel: 0,
  }));

  const onlineTableRows = onlineFromApi;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>World Overview</h2>
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
          <span style={{ fontSize: 11, color: COLORS.textDim, padding: "0 8px", fontFamily: "'JetBrains Mono', monospace" }}>v0.4.1-dev</span>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
        <StatCard label="Players Online" value={String(serverStatus.active_sessions)} color={COLORS.success} icon={<Icons.Players />} />
        <StatCard label="Rooms w/ players" value={String(occupiedRooms)} color={COLORS.accent} icon={<Icons.Map />} title="Distinct room_id values from Redis for authenticated sessions" />
        <StatCard label="Zones / Rooms" value={overview ? `${overview.zone_count} / ${overview.room_count}` : "—"} color={COLORS.info} icon={<Icons.World />} />
        <StatCard label="Entity templates" value={overview ? String(overview.entity_templates ?? 0) : "—"} color={COLORS.warning} icon={<Icons.Entities />} title="Distinct spawn definitions across room YAML" />
        <StatCard label="Spawn placements" value={overview ? String(overview.entity_spawn_references ?? 0) : "—"} color={COLORS.warning} icon={<Icons.Activity />} title="Total entity spawn reference counts summed from rooms" />
        <StatCard label="Items / Glyphs" value={overview ? `${overview.item_count} / ${overview.glyph_count}` : "—"} color={COLORS.cyan} icon={<Icons.Items />} />
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
                No log lines yet. With the engine running, connect to Nexus and watch this feed when the server broadcasts to <code style={{ color: COLORS.textDim }}>/ws/logs</code>.
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
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif", display: "flex", alignItems: "center", gap: 8 }}><Icons.Map /> Labyrinth Topology</h3>
          <MiniMap />
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", justifyContent: "center" }}>
            {[{ label: "Hub", color: COLORS.accent }, { label: "Chamber", color: COLORS.info }, { label: "Boss", color: COLORS.warning }, { label: "Hazard", color: COLORS.danger }].map(l => (
              <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <StatusDot color={l.color} /><span style={{ fontSize: 10, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>{l.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: "16px 18px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Online Players</h3>
        </div>
        <DataTable columns={[
          { label: "Player", render: row => (<div style={{ display: "flex", alignItems: "center", gap: 8 }}><StatusDot color={row.status === "online" ? COLORS.success : COLORS.warning} pulse={row.status === "online"} /><span style={{ fontWeight: 600 }}>{row.name}</span></div>) },
          { label: "State", key: "class", mono: true },
          { label: "Location", key: "location", mono: true, title: "room_id from Redis when logged in" },
          { label: "Peer", key: "peer", mono: true },
          { label: "Adaptive", render: row => <Badge color={row.adaptiveLevel > 7 ? COLORS.danger : row.adaptiveLevel > 4 ? COLORS.warning : COLORS.success}>{typeof row.adaptiveLevel === "number" ? row.adaptiveLevel.toFixed(1) : "—"}</Badge> },
        ]} rows={onlineTableRows} />
      </div>
    </div>
  );
};

export default DashboardPage;
