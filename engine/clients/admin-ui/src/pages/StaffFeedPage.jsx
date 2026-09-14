import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { ActionButton, FetchErrorBanner } from "../adminCommon.jsx";

// Live › Staff feed: what is happening in the world as it happens (GET /admin/feed, polled).
// Kept in server memory since the last start; staff actions are in the audit log instead.

const mono = "'JetBrains Mono', monospace";
const KIND_LABELS = {
  signin: "Sign-ins",
  signout: "Sign-outs",
  death: "Deaths",
  kill: "Kills",
  character: "New characters",
  report: "Reports",
  server: "Server",
};
const DEFAULT_ON = ["signin", "signout", "death", "character", "report", "server"];
const KEEP = 500;

export default function StaffFeedPage() {
  const { colors: COLORS } = useAdminTheme();
  const [entries, setEntries] = useState([]);
  const [shown, setShown] = useState(() => new Set(DEFAULT_ON));
  const [agents, setAgents] = useState(false);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState(null);
  const lastId = useRef(0);

  useEffect(() => {
    if (paused) return undefined;
    let alive = true;
    const load = () => axios.get(`${API_BASE}/admin/feed`, { params: { after: lastId.current, limit: 500 } })
      .then(({ data }) => {
        if (!alive) return;
        setError(null);
        if (data.entries.length) {
          lastId.current = data.entries[data.entries.length - 1].id;
          setEntries((prev) => [...prev, ...data.entries].slice(-KEEP));
        }
      })
      .catch((e) => alive && setError(e?.response?.data?.detail || e.message));
    load();
    const id = setInterval(load, 3000);
    return () => { alive = false; clearInterval(id); };
  }, [paused]);

  const toggle = (kind) => setShown((s) => {
    const next = new Set(s);
    if (next.has(kind)) next.delete(kind); else next.add(kind);
    return next;
  });
  const visible = entries.filter((e) => shown.has(e.kind) && (agents || !e.agent)).slice().reverse();
  const tone = { death: COLORS.danger, report: COLORS.warning, server: COLORS.info, character: COLORS.success };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Staff feed</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", maxWidth: 820 }}>
          What is happening in the world as it happens: who comes and goes, deaths, new characters, player reports and restarts. It covers the time since the server last started. Staff changes are in the audit log.
        </p>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {Object.entries(KIND_LABELS).map(([kind, label]) => {
          const on = shown.has(kind);
          return (
            <button key={kind} type="button" aria-pressed={on} onClick={() => toggle(kind)}
              style={{ padding: "4px 10px", borderRadius: 999, fontSize: 12, cursor: "pointer", color: on ? COLORS.accent : COLORS.textMuted, background: on ? COLORS.accentGlow : COLORS.bgInput, border: `1px solid ${on ? COLORS.accent : COLORS.border}` }}>{label}</button>
          );
        })}
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: COLORS.textMuted, marginLeft: 8, cursor: "pointer" }}>
          <input id="feed-agents" type="checkbox" checked={agents} onChange={(e) => setAgents(e.target.checked)} />
          Include agents
        </label>
        <span style={{ marginLeft: "auto" }}>
          <ActionButton small variant="ghost" onClick={() => setPaused((p) => !p)}>{paused ? "Resume" : "Pause"}</ActionButton>
        </span>
      </div>
      <FetchErrorBanner error={error} label="staff feed" />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        {visible.length === 0 && <div style={{ padding: 16, fontSize: 13, color: COLORS.textMuted }}>Nothing yet. New events appear here within a few seconds.</div>}
        {visible.map((e) => (
          <div key={e.id} style={{ display: "flex", gap: 12, alignItems: "baseline", padding: "7px 14px", borderBottom: `1px solid ${COLORS.border}33`, fontSize: 13 }}>
            <span style={{ fontFamily: mono, fontSize: 11, color: COLORS.textDim, minWidth: 70 }}>{new Date(e.at).toLocaleTimeString()}</span>
            <span style={{ fontFamily: mono, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: tone[e.kind] || COLORS.textMuted, minWidth: 80 }}>{KIND_LABELS[e.kind] || e.kind}</span>
            <span style={{ color: COLORS.text, flex: 1, minWidth: 0 }}>{e.text}{e.agent && <span style={{ color: COLORS.textDim }}> (agent)</span>}</span>
            {e.href && <a href={e.href} style={{ color: COLORS.accent, fontFamily: mono, fontSize: 11, whiteSpace: "nowrap" }}>{e.room_id || "open"}</a>}
          </div>
        ))}
      </div>
    </div>
  );
}
