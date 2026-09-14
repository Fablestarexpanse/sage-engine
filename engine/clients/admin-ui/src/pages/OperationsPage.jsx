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
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Broadcast &amp; reload</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", maxWidth: 560, lineHeight: 1.5 }}>
            Send a message to everyone playing, or clear the content and prompt caches. The live world snapshot is under Live › Live world, tick metrics under System › Server &amp; AI models.
          </p>
        </div>
        <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={() => refresh()} disabled={busy}>Refresh</ActionButton>
      </div>
      <TabBar
        tabs={[
          { id: "broadcast", label: "Broadcast" },
          { id: "reload", label: "Reload caches" },
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
