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


const OperationsPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [tab, setTab] = useState("sessions");
  const [players, setPlayers] = useState([]);
  const [worldLive, setWorldLive] = useState(null);
  const [serverInfo, setServerInfo] = useState(null);
  const [broadcastText, setBroadcastText] = useState("");
  const [bannerMsg, setBannerMsg] = useState("");
  const [reloadMsg, setReloadMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [metrics, setMetrics] = useState(null);

  const refresh = useCallback(async () => {
    const run = async (fn, fallback) => {
      try {
        return await fn();
      } catch {
        return fallback;
      }
    };
    const pr = await run(() => axios.get(`${API_BASE}/players`), null);
    if (pr) setPlayers(pr.data || []);
    const wl = await run(() => axios.get(`${API_BASE}/world/live`), null);
    if (wl) setWorldLive(wl.data);
    const si = await run(() => axios.get(`${API_BASE}/server/info`), null);
    if (si) setServerInfo(si.data);
    const m = await run(() => axios.get(`${API_BASE}/admin/metrics`), null);
    if (m) setMetrics(m.data);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh]);

  const disconnectSession = async (sessionId, name) => {
    if (!window.confirm(`Disconnect session ${sessionId.slice(0, 8)}… (${name})?`)) return;
    setBusy(true);
    setBannerMsg("");
    try {
      await axios.post(`${API_BASE}/admin/sessions/${sessionId}/disconnect`);
      setBannerMsg("Session disconnected.");
      await refresh();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message || "Failed");
    } finally {
      setBusy(false);
    }
  };

  const sendBroadcast = async () => {
    const t = broadcastText.trim();
    if (!t) return;
    setBusy(true);
    setBannerMsg("");
    try {
      await axios.post(`${API_BASE}/admin/broadcast`, { message: t });
      setBannerMsg("Broadcast sent to playing sessions.");
      setBroadcastText("");
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message || "Failed");
    } finally {
      setBusy(false);
    }
  };

  const doReloadCaches = async () => {
    setBusy(true);
    setReloadMsg("");
    try {
      await axios.post(`${API_BASE}/content/cache/reload`);
      setReloadMsg("Content and prompt caches cleared.");
      await refresh();
    } catch (e) {
      setReloadMsg(e.message || "Failed");
    } finally {
      setBusy(false);
    }
  };

  const sessionsRows = (players || []).map((p) => ({
    id: p.session_id,
    name: p.player_id || "guest",
    state: p.state,
    location: p.room_id || "—",
    peer: typeof p.peer === "string" ? p.peer : JSON.stringify(p.peer ?? "—"),
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Operations</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", maxWidth: 560, lineHeight: 1.5 }}>
            Sessions, server-wide broadcast, content cache reload, and a Redis snapshot of the live world. Every action here needs a staff login with the Operations tool.
          </p>
        </div>
        <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={() => refresh()} disabled={busy}>Refresh</ActionButton>
      </div>
      <TabBar
        tabs={[
          { id: "sessions", label: "Sessions" },
          { id: "broadcast", label: "Broadcast" },
          { id: "reload", label: "Reload caches" },
          { id: "world", label: "World live" },
          { id: "metrics", label: "Metrics" },
        ]}
        active={tab}
        onChange={setTab}
      />
      {bannerMsg && <div style={{ fontSize: 12, color: COLORS.success, fontFamily: "'DM Sans', sans-serif" }}>{bannerMsg}</div>}
      {tab === "sessions" && (
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16, overflow: "hidden" }}>
          <DataTable
            columns={[
              { label: "Player", render: (row) => <span style={{ fontWeight: 600 }}>{row.name}</span> },
              { label: "State", key: "state", mono: true },
              { label: "Location", key: "location", mono: true },
              { label: "Peer", key: "peer", mono: true },
              {
                label: "",
                render: (row) => (
                  <ActionButton small variant="danger" disabled={busy} onClick={() => disconnectSession(row.id, row.name)}>
                    Disconnect
                  </ActionButton>
                ),
              },
            ]}
            rows={sessionsRows}
          />
        </div>
      )}
      {tab === "broadcast" && (
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
          <label style={{ fontSize: 12, color: COLORS.textMuted }}>Message (prefixed with [Server] on the wire)</label>
          <textarea
            value={broadcastText}
            onChange={(e) => setBroadcastText(e.target.value)}
            rows={4}
            placeholder="Maintenance in 5 minutes — please find a safe room."
            style={{
              width: "100%", padding: 12, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`,
              borderRadius: 8, color: COLORS.text, fontSize: 13, fontFamily: "'DM Sans', sans-serif", resize: "vertical",
            }}
          />
          <ActionButton variant="primary" icon={<Icons.Terminal />} disabled={busy || !broadcastText.trim()} onClick={sendBroadcast}>Send broadcast</ActionButton>
        </div>
      )}
      {tab === "reload" && (
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
          <p style={{ margin: 0, fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
            Clears in-memory content loader cache and reloads prompts. Does not restart the process.
          </p>
          {serverInfo?.last_content_reload_at && (
            <div style={{ fontSize: 12, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>
              Last reload (UTC): {serverInfo.last_content_reload_at}
            </div>
          )}
          {reloadMsg && <div style={{ fontSize: 12, color: reloadMsg.includes("Failed") ? COLORS.danger : COLORS.success }}>{reloadMsg}</div>}
          <ActionButton variant="primary" icon={<Icons.Refresh />} disabled={busy} onClick={doReloadCaches}>Reload content + prompt caches</ActionButton>
        </div>
      )}
      {tab === "world" && (
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          {!worldLive && <div style={{ color: COLORS.textMuted, fontSize: 13 }}>Could not load /world/live</div>}
          {worldLive && (
            <>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "12px 24px", fontSize: 13, fontFamily: "'JetBrains Mono', monospace", color: COLORS.textMuted }}>
                <span>Redis: <strong style={{ color: COLORS.text }}>{worldLive.redis_connected ? "up" : "down"}</strong></span>
                <span title="Rooms whose occupant set is not empty, counting players and agents">Occupied rooms (players and agents): <strong style={{ color: COLORS.text }}>{worldLive.rooms_with_players ?? "—"}</strong></span>
                <span>Combat keys: <strong style={{ color: COLORS.text }}>{worldLive.combat_keys ?? "—"}</strong></span>
                <span>Entity state keys: <strong style={{ color: COLORS.text }}>{worldLive.entity_state_keys ?? "—"}</strong></span>
                <span>Item state keys: <strong style={{ color: COLORS.text }}>{worldLive.item_state_keys ?? "—"}</strong></span>
              </div>
              {worldLive.error && <div style={{ color: COLORS.danger, fontSize: 12 }}>{worldLive.error}</div>}
              {worldLive.note && <div style={{ fontSize: 11, color: COLORS.textDim }}>{worldLive.note}</div>}
              {(worldLive.rooms_with_players_detail || []).length > 0 && (
                <div style={{ maxHeight: 280, overflow: "auto" }}>
                  <DataTable
                    columns={[
                      { label: "Room", key: "room_id", mono: true },
                      { label: "Players", key: "player_count", mono: true },
                    ]}
                    rows={worldLive.rooms_with_players_detail}
                  />
                </div>
              )}
            </>
          )}
        </div>
      )}
      {tab === "metrics" && (
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18 }}>
          <pre style={{ margin: 0, fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
            {metrics ? JSON.stringify(metrics, null, 2) : "Could not load /admin/metrics"}
          </pre>
        </div>
      )}
    </div>
  );
};

export default OperationsPage;
