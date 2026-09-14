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


const RESTART_CHOICES = [
  [60, "1 minute"],
  [300, "5 minutes"],
  [600, "10 minutes"],
  [900, "15 minutes"],
  [1800, "30 minutes"],
];

function fmtLeft(seconds) {
  if (seconds == null) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

// Warn players on a countdown, stop new sign-ins in the last minute, save everyone, and stop.
function RestartCard() {
  const { colors: COLORS } = useAdminTheme();
  const [status, setStatus] = useState(null);
  const [seconds, setSeconds] = useState(300);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/admin/restart`).then(({ data }) => alive && setStatus(data)).catch((e) => alive && setError(e.message));
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  useEffect(() => {
    if (!status?.scheduled || tick % 5 !== 0) return undefined;
    let alive = true;
    axios.get(`${API_BASE}/admin/restart`).then(({ data }) => alive && setStatus(data)).catch(() => {});
    return () => { alive = false; };
  }, [tick, status?.scheduled]);

  const run = async (fn) => {
    setError("");
    try {
      const { data } = await fn();
      setStatus(data);
    } catch (e) {
      const d = e.response?.data?.detail;
      setError(typeof d === "string" ? d : e.message);
    }
  };

  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${status?.scheduled ? COLORS.warning : COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
      <p style={{ margin: 0, fontSize: 13, color: COLORS.textMuted, lineHeight: 1.5, maxWidth: 760 }}>
        Players are warned as the time runs down. In the last minute new sign-ins are refused. At zero every character is saved, players are disconnected with a message, and the server stops. It starts again only if whatever runs it restarts it (for example Docker&apos;s restart policy or a service manager). Otherwise start it again by hand.
      </p>
      {status?.scheduled ? (
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 22, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace", color: COLORS.warning }}>{fmtLeft(Math.max(0, (status.seconds_left ?? 0) - (tick % 5)))}</span>
          <span style={{ fontSize: 13, color: COLORS.text }}>until restart{status.reason ? ` (${status.reason})` : ""}, scheduled by {status.by}.{status.signins_closed ? " New sign-ins are closed." : ""}</span>
          <ActionButton variant="ghost" onClick={() => run(() => axios.delete(`${API_BASE}/admin/restart`))}>Cancel restart</ActionButton>
        </div>
      ) : (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <label htmlFor="restart-when" style={{ fontSize: 13, color: COLORS.text }}>Restart in</label>
          <select id="restart-when" value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}
            style={{ padding: "7px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13 }}>
            {RESTART_CHOICES.map(([s, label]) => <option key={s} value={s}>{label}</option>)}
          </select>
          <input id="restart-reason" aria-label="Reason shown to players" placeholder="Reason shown to players (optional)" value={reason} onChange={(e) => setReason(e.target.value)}
            style={{ flex: 1, minWidth: 220, padding: "7px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13 }} />
          <ActionButton variant="danger" onClick={() => {
            if (window.confirm(`Restart the server in ${RESTART_CHOICES.find(([s]) => s === seconds)?.[1]}? Everyone playing will be warned, saved and disconnected.`)) {
              run(() => axios.post(`${API_BASE}/admin/restart`, { seconds, reason }));
            }
          }}>Schedule restart</ActionButton>
        </div>
      )}
      {error && <div role="alert" style={{ fontSize: 12, color: COLORS.danger }}>{error}</div>}
    </div>
  );
}

const OperationsPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [tab, setTab] = useState("broadcast");
  const [serverInfo, setServerInfo] = useState(null);
  const [broadcastText, setBroadcastText] = useState("");
  const [bannerMsg, setBannerMsg] = useState("");
  const [reloadMsg, setReloadMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const run = async (fn, fallback) => {
      try {
        return await fn();
      } catch {
        return fallback;
      }
    };
    const si = await run(() => axios.get(`${API_BASE}/server/info`), null);
    if (si) setServerInfo(si.data);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh]);

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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Broadcast, reload &amp; restart</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", maxWidth: 560, lineHeight: 1.5 }}>
            Send a message to everyone playing, clear the content and prompt caches, or schedule a restart. The live world snapshot is under Live › Live world, tick metrics under System › Server &amp; AI models.
          </p>
        </div>
        <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={() => refresh()} disabled={busy}>Refresh</ActionButton>
      </div>
      <TabBar
        tabs={[
          { id: "broadcast", label: "Broadcast" },
          { id: "reload", label: "Reload caches" },
          { id: "restart", label: "Restart" },
        ]}
        active={tab}
        onChange={setTab}
      />
      {bannerMsg && <div style={{ fontSize: 12, color: COLORS.success, fontFamily: "'DM Sans', sans-serif" }}>{bannerMsg}</div>}
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
      {tab === "restart" && <RestartCard />}
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
    </div>
  );
};

export default OperationsPage;
