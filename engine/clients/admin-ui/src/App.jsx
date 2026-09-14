import { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import AgentsTab from "./AgentsTab.jsx";
import ShopsTab from "./ShopsTab.jsx";
import ProficienciesPage from "./ProficienciesPage.jsx";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE, WS_BASE } from "./apiConfig.js";

// ═══════════════════════════════════════════════════════════════
// SAGE NEXUS — WORLD ADMINISTRATION CONSOLE v2
// Backend management interface with integrated AI Forge
// ═══════════════════════════════════════════════════════════════
import { LS_ADMIN_TOKEN, ALL_ADMIN_TOOLS, adminPresenceWsUrl, sendWsAuthToken, Icons } from "./adminCommon.jsx";
import AiForgePage from "./pages/AiForgePage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import OnlinePage from "./pages/OnlinePage.jsx";
import LiveWorldPage from "./pages/LiveWorldPage.jsx";
import CharactersPage from "./pages/CharactersPage.jsx";
import AccountsPage from "./pages/AccountsPage.jsx";
import CreditsPage from "./pages/CreditsPage.jsx";
import ContentLibraryPage from "./pages/ContentLibraryPage.jsx";
import ServerPage from "./pages/ServerPage.jsx";
import OperationsPage from "./pages/OperationsPage.jsx";
import StaffTeamPage from "./pages/StaffTeamPage.jsx";
import LexiconPage from "./pages/LexiconPage.jsx";
import WorldPluginsPage from "./pages/WorldPluginsPage.jsx";
import AuditLogPage from "./pages/AuditLogPage.jsx";

// ═══════════════════════════════════════════════════════════════
// ADMIN AUTH, PRESENCE & TEAM (staff / head admin)
// ═══════════════════════════════════════════════════════════════

const LoginScreen = ({ onLoggedIn }) => {
  const { colors: COLORS } = useAdminTheme();
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // DEV-AUTH:BEGIN — passwordless dev staff login (loopback, dev flags); stripped for release.
  const [devEnabled, setDevEnabled] = useState(false);
  useEffect(() => {
    let alive = true;
    axios
      .get(`${API_BASE}/admin/dev/status`)
      .then(({ data }) => alive && setDevEnabled(Boolean(data?.enabled)))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  const devLogin = async () => {
    setErr("");
    setBusy(true);
    try {
      const { data } = await axios.post(`${API_BASE}/admin/dev/login`);
      if (!data?.access_token) throw new Error(data?.error || "Dev login failed");
      localStorage.setItem(LS_ADMIN_TOKEN, data.access_token);
      onLoggedIn(data.staff);
    } catch (ex) {
      setErr(ex.response?.data?.detail || ex.message || "Dev login failed");
    } finally {
      setBusy(false);
    }
  };
  // DEV-AUTH:END
  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const { data } = await axios.post(`${API_BASE}/admin/auth/login`, {
        username: user.trim(),
        password: pass,
      });
      localStorage.setItem(LS_ADMIN_TOKEN, data.access_token);
      onLoggedIn(data.staff);
    } catch (ex) {
      const status = ex.response?.status;
      if (status === 502 || status === 503) {
        setErr(
          "Cannot reach Nexus (HTTP " +
            status +
            "). Start Docker Desktop, then from the repo root: docker compose up -d redis postgres — then: python -m sage (port 8001 must match this UI)."
        );
      } else {
        setErr(ex.response?.data?.detail || ex.message || "Login failed");
      }
    } finally {
      setBusy(false);
    }
  };
  const inp = {
    width: "100%",
    maxWidth: 320,
    padding: "10px 12px",
    background: COLORS.bgInput,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 8,
    color: COLORS.text,
    fontSize: 14,
  };
  return (
    <div style={{
      minHeight: "100vh", background: COLORS.bg, display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "'DM Sans', sans-serif",
    }}>
      <form onSubmit={submit} style={{
        background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 32, width: "min(400px, 92vw)",
      }}>
        <h1 style={{ margin: "0 0 8px", fontSize: 20, color: COLORS.accent, fontFamily: "'Space Grotesk', sans-serif" }}>SAGE Nexus</h1>
        <p style={{ margin: "0 0 20px", fontSize: 13, color: COLORS.textMuted }}>Sign in with a staff account. Ask a head admin for credentials. Username and password are case-sensitive.</p>
        <label style={{ display: "block", fontSize: 11, color: COLORS.textMuted, marginBottom: 6 }}>Username</label>
        <input autoComplete="username" value={user} onChange={(e) => setUser(e.target.value)} style={{ ...inp, marginBottom: 14 }} />
        <label style={{ display: "block", fontSize: 11, color: COLORS.textMuted, marginBottom: 6 }}>Password</label>
        <input type="password" autoComplete="current-password" value={pass} onChange={(e) => setPass(e.target.value)} style={{ ...inp, marginBottom: 16 }} />
        {err && <div style={{ color: COLORS.danger, fontSize: 12, marginBottom: 12 }}>{typeof err === "string" ? err : JSON.stringify(err)}</div>}
        <button type="submit" disabled={busy} style={{
          width: "100%", padding: "12px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, cursor: busy ? "wait" : "pointer",
        }}>{busy ? "Signing in…" : "Sign in"}</button>
        {/* DEV-AUTH:BEGIN */}
        {devEnabled && (
          <button type="button" data-testid="admin-dev-login" disabled={busy} onClick={devLogin} style={{
            width: "100%", marginTop: 12, padding: "10px", background: COLORS.warningBg, color: COLORS.warning,
            border: `1px dashed ${COLORS.warning}`, borderRadius: 8, fontWeight: 600, cursor: busy ? "wait" : "pointer",
          }}>Dev login as head admin (no password, localhost only)</button>
        )}
        {/* DEV-AUTH:END */}
      </form>
    </div>
  );
};

const PresenceStrip = ({ online }) => {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{
      fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace",
      padding: "8px 12px", background: COLORS.bgInput, borderRadius: 8, border: `1px solid ${COLORS.border}`,
      marginBottom: 12, lineHeight: 1.5,
    }}>
      <strong style={{ color: COLORS.textDim }}>Team online</strong>
      {" · "}
      {!online?.length ? "—" : online.map((p) => `${p.display_name || p.username} (${p.role})`).join(" · ")}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════
// NAVIGATION & MAIN APP
// ═══════════════════════════════════════════════════════════════

// Grouped by the staff job, not by how a page is built. A plugin page (pluginTool) sits in the group
// its job belongs to and appears only when a plugin of the running world mounts that admin tool
// (GET /admin/plugin-pages). The array order is the sidebar order; groups must stay contiguous.
const NAV_ITEMS = [
  { id: "dashboard", group: "Overview", label: "Dashboard", icon: <Icons.Dashboard /> },
  { id: "online", group: "Live", label: "Who's online", icon: <Icons.Players />, anyOf: ["players"] },
  { id: "live", group: "Live", label: "Live world", icon: <Icons.World />, anyOf: ["world", "operations"] },
  { id: "operations", group: "Live", label: "Broadcast & reload", icon: <Icons.Alert /> },
  { id: "characters", group: "Players", label: "Characters", icon: <Icons.Players />, anyOf: ["players"] },
  { id: "accounts", group: "Players", label: "Accounts", icon: <Icons.Players />, anyOf: ["players"] },
  // The running world package, its plugins, content check and migration status.
  { id: "world", group: "World", label: "World & plugins", icon: <Icons.World />, anyOf: ["world", "server", "dashboard"] },
  { id: "content", group: "World", label: "Content Library", icon: <Icons.Content />, anyOf: ["content", "world", "entities", "items"] },
  { id: "skills", group: "World", label: "Skills catalog", icon: <Icons.Skills />, pluginTool: true },
  { id: "lexicon", group: "World", label: "Lexicon & MOTD", icon: <Icons.Content /> },
  { id: "forge", group: "World", label: "AI Forge", icon: <Icons.Forge />, highlight: true },
  { id: "shops", group: "Economy", label: "Shops", icon: <Icons.Items />, pluginTool: true },
  { id: "credits", group: "Economy", label: "AI art credits", icon: <Icons.Items />, anyOf: ["server"] },
  { id: "agents", group: "NPCs", label: "Agents", icon: <Icons.Players />, pluginTool: true },
  { id: "server", group: "System", label: "Server & AI models", icon: <Icons.Server /> },
  { id: "team", group: "System", label: "Team & access", icon: <Icons.Players />, headOnly: true },
  { id: "audit", group: "System", label: "Audit log", icon: <Icons.History />, anyOf: ["team", "operations"] },
];

// Page ids from before the regrouping, so old links and bookmarks still land somewhere sensible.
const RENAMED_PAGES = { players: "characters" };

const AgentsPage = ({ pluginBase }) => (
  <div style={{ display: "grid", gap: 16 }}>
    <AgentsTab pluginBase={pluginBase} />
  </div>
);

const ShopsPage = ({ pluginBase }) => (
  <div style={{ display: "grid", gap: 16 }}>
    <ShopsTab pluginBase={pluginBase} />
  </div>
);

const PAGES = {
  dashboard: DashboardPage,
  world: WorldPluginsPage,
  forge: AiForgePage,
  operations: OperationsPage,
  online: OnlinePage,
  live: LiveWorldPage,
  characters: CharactersPage,
  accounts: AccountsPage,
  credits: CreditsPage,
  content: ContentLibraryPage,
  skills: ProficienciesPage,
  agents: AgentsPage,
  shops: ShopsPage,
  lexicon: LexiconPage,
  server: ServerPage,
  team: StaffTeamPage,
  audit: AuditLogPage,
};

export default function App() {
  const { colors: COLORS, toggleMode, mode } = useAdminTheme();
  // The open page lives in the URL (#/players), so reloading or sharing a link keeps it.
  const pageFromHash = () => {
    const [id = "dashboard", ...rest] = window.location.hash.replace(/^#\/?/, "").split("/");
    if (RENAMED_PAGES[id]) {
      // Rewrite the old address so links a page builds from the URL use the new id.
      window.history.replaceState(null, "", `#/${[RENAMED_PAGES[id], ...rest].join("/")}`);
      return RENAMED_PAGES[id];
    }
    return id || "dashboard";
  };
  const [activePage, setActivePageState] = useState(pageFromHash);
  const setActivePage = useCallback((page) => {
    setActivePageState(page);
    if (window.location.hash.replace(/^#\/?/, "").split("/")[0] !== page) window.location.hash = `/${page}`;
  }, []);
  useEffect(() => {
    const onHash = () => setActivePageState(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const [sidebarHovered, setSidebarHovered] = useState(null);
  const [serverInfo, setServerInfo] = useState(null);
  const [staffProfile, setStaffProfile] = useState(null);
  const [pluginPages, setPluginPages] = useState([]);
  const [booting, setBooting] = useState(true);
  const [presenceOnline, setPresenceOnline] = useState([]);

  useEffect(() => {
    const onAuthLost = () => {
      localStorage.removeItem(LS_ADMIN_TOKEN);
      window.location.reload();
    };
    window.addEventListener("sage-admin-unauthorized", onAuthLost);
    const reqId = axios.interceptors.request.use((cfg) => {
      const t = localStorage.getItem(LS_ADMIN_TOKEN);
      if (t) cfg.headers.Authorization = `Bearer ${t}`;
      return cfg;
    });
    const resId = axios.interceptors.response.use(
      (r) => r,
      (err) => {
        if (err.response?.status === 401) {
          const auth = err.config?.headers?.Authorization;
          if (typeof auth === "string" && auth.startsWith("Bearer ") && localStorage.getItem(LS_ADMIN_TOKEN)) {
            window.dispatchEvent(new Event("sage-admin-unauthorized"));
          }
        }
        return Promise.reject(err);
      }
    );
    return () => {
      window.removeEventListener("sage-admin-unauthorized", onAuthLost);
      axios.interceptors.request.eject(reqId);
      axios.interceptors.response.eject(resId);
    };
  }, []);

  const refreshMe = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/admin/me`);
      setStaffProfile(data);
      try {
        const pages = await axios.get(`${API_BASE}/admin/plugin-pages`);
        setPluginPages(Array.isArray(pages.data) ? pages.data : []);
      } catch {
        setPluginPages([]);
      }
      return data;
    } catch {
      setStaffProfile(null);
      setPluginPages([]);
      return null;
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/admin/bootstrap`);
        setServerInfo({ admin_auth_required: !!data.admin_auth_required });
      } catch {
        setServerInfo({ admin_auth_required: true });
      }
    })();
  }, []);

  useEffect(() => {
    if (!serverInfo) return;
    let cancelled = false;
    (async () => {
      const need = !!serverInfo.admin_auth_required;
      const t = localStorage.getItem(LS_ADMIN_TOKEN);
      if (need && !t) {
        if (!cancelled) {
          setStaffProfile(null);
          setBooting(false);
        }
        return;
      }
      try {
        await refreshMe();
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => { cancelled = true; };
  }, [serverInfo, refreshMe]);

  useEffect(() => {
    if (!serverInfo) return;
    if (serverInfo.admin_auth_required && !localStorage.getItem(LS_ADMIN_TOKEN)) return;
    let ws;
    try {
      ws = new WebSocket(adminPresenceWsUrl());
      ws.onopen = () => sendWsAuthToken(ws);
      ws.onmessage = (ev) => {
        try {
          const j = JSON.parse(ev.data);
          if (j.type === "presence" && Array.isArray(j.online)) setPresenceOnline(j.online);
        } catch { /* ignore */ }
      };
    } catch { /* ignore */ }
    return () => { try { ws?.close(); } catch { /* ignore */ } };
  }, [serverInfo, staffProfile?.staff_id]);

  useEffect(() => {
    const onNav = (ev) => {
      const d = ev.detail || {};
      if (d.page === "forge") {
        setActivePage("forge");
        return;
      }
      // Legacy page ids from before the Content Library consolidation.
      // Legacy page ids, including the retired World Builder (structural editing is WorldForge's).
      if (["entities", "items", "builder"].includes(d.page)) {
        setActivePage("content");
      }
    };
    window.addEventListener("fs-admin-nav", onNav);
    return () => window.removeEventListener("fs-admin-nav", onNav);
  }, [setActivePage]);

  const allowedSet = useMemo(() => {
    if (staffProfile?.tools_effective == null) return new Set(ALL_ADMIN_TOOLS);
    return new Set(staffProfile.tools_effective);
  }, [staffProfile]);

  const navFiltered = useMemo(() => NAV_ITEMS.filter((item) => {
    if (item.headOnly) return staffProfile?.role === "head_admin";
    if (item.anyOf) return item.anyOf.some((t) => allowedSet.has(t));
    // The server already filtered plugin pages by the staff member's tools.
    if (item.pluginTool) return pluginPages.some((p) => p.tool === item.id);
    return allowedSet.has(item.id);
  }), [staffProfile, allowedSet, pluginPages]);

  const resolvedPage = navFiltered.some((n) => n.id === activePage)
    ? activePage
    : (navFiltered[0]?.id ?? "dashboard");

  const PageComponent = PAGES[resolvedPage] || PAGES.dashboard;

  useEffect(() => {
    const label = NAV_ITEMS.find((n) => n.id === resolvedPage)?.label;
    document.title = label ? `${label} · SAGE Nexus` : "SAGE Nexus";
  }, [resolvedPage]);

  const logout = () => {
    localStorage.removeItem(LS_ADMIN_TOKEN);
    setStaffProfile(null);
    window.location.reload();
  };

  if (!serverInfo || booting) {
    return (
      <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", background: COLORS.bg, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
        Loading…
      </div>
    );
  }

  if (serverInfo.admin_auth_required && !localStorage.getItem(LS_ADMIN_TOKEN)) {
    return <LoginScreen onLoggedIn={(s) => { setStaffProfile(s); setBooting(false); }} />;
  }

  return (
    <div style={{ display: "flex", height: "100vh", background: COLORS.bg, color: COLORS.text, fontFamily: "'DM Sans', sans-serif", overflow: "hidden" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${COLORS.border}; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: ${COLORS.borderActive}; }
        select option { background: ${COLORS.bgPanel}; color: ${COLORS.text}; }
        textarea:focus, select:focus { border-color: ${COLORS.borderActive} !important; }
      `}</style>

      <nav style={{ width: 220, flexShrink: 0, background: COLORS.bgPanel, borderRight: `1px solid ${COLORS.border}`, display: "flex", flexDirection: "column", padding: "16px 0", overflow: "hidden" }}>
        <div style={{ padding: "8px 20px 24px", borderBottom: `1px solid ${COLORS.border}`, marginBottom: 12 }}>
          <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "'Space Grotesk', sans-serif", color: COLORS.accent, letterSpacing: "-0.02em", display: "flex", alignItems: "center", gap: 8 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L2 7v10l10 5 10-5V7L12 2z" stroke={COLORS.accent} strokeWidth="1.5" fill={`${COLORS.accent}15`} />
              <circle cx="12" cy="12" r="3" stroke={COLORS.accent} strokeWidth="1.5" />
              <path d="M12 2v7M12 15v7M2 7l7 5M15 12l7 5M22 7l-7 5M9 12L2 17" stroke={COLORS.accent} strokeWidth="0.5" opacity="0.4" />
            </svg>
            SAGE NEXUS
          </div>
          <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace", marginTop: 4, letterSpacing: "0.08em", textTransform: "uppercase" }}>Admin Console</div>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2, padding: "0 8px", overflowY: "auto" }}>
          {navFiltered.map((item, index) => {
            const isActive = resolvedPage === item.id;
            const isHovered = sidebarHovered === item.id;
            const isForge = item.highlight;
            const startsGroup = index === 0 || navFiltered[index - 1].group !== item.group;
            return (
              <div key={item.id} style={{ display: "flex", flexDirection: "column" }}>
                {startsGroup && (
                  <div style={{ padding: index === 0 ? "0 12px 4px" : "12px 12px 4px", fontSize: 10, fontWeight: 600, color: COLORS.textDim, textTransform: "uppercase", letterSpacing: "0.1em", fontFamily: "'JetBrains Mono', monospace" }}>{item.group}</div>
                )}
                <button onClick={() => setActivePage(item.id)}
                  onMouseEnter={() => setSidebarHovered(item.id)} onMouseLeave={() => setSidebarHovered(null)}
                  aria-current={isActive ? "page" : undefined}
                  style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", border: "none", borderRadius: 6,
                    background: isActive ? (isForge ? COLORS.forgeGlow : COLORS.accentGlow) : isHovered ? COLORS.bgHover : "transparent",
                    color: isActive ? (isForge ? COLORS.forge : COLORS.accent) : isHovered ? COLORS.text : COLORS.textMuted,
                    cursor: "pointer", fontSize: 13, fontWeight: isActive ? 600 : 400,
                    fontFamily: "'DM Sans', sans-serif", textAlign: "left", transition: "all 0.12s ease", position: "relative",
                  }}
                >
                  {isActive && <div style={{ position: "absolute", left: 0, top: "50%", transform: "translateY(-50%)", width: 3, height: 18, borderRadius: "0 2px 2px 0", background: isForge ? COLORS.forge : COLORS.accent }} />}
                  <span style={{ opacity: isActive ? 1 : 0.6 }}>{item.icon}</span>
                  {item.label}
                </button>
              </div>
            );
          })}
        </div>

        <div style={{ padding: "16px 20px", borderTop: `1px solid ${COLORS.border}`, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: COLORS.accent, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#fff", fontFamily: "'Space Grotesk', sans-serif" }}>
              {(staffProfile?.display_name || "?").slice(0, 1).toUpperCase()}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: COLORS.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{staffProfile?.display_name || "Staff"}</div>
              <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{staffProfile?.role || "—"}</div>
            </div>
          </div>
          {(serverInfo?.admin_auth_required || localStorage.getItem(LS_ADMIN_TOKEN)) && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <button
                type="button"
                onClick={toggleMode}
                title={mode === "dark" ? "Use light theme" : "Use dark theme"}
                style={{ fontSize: 11, padding: "6px 10px", background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.textMuted, cursor: "pointer" }}
              >
                {mode === "dark" ? "Light mode" : "Dark mode"}
              </button>
              <button type="button" onClick={logout} style={{ fontSize: 11, padding: "6px 10px", background: COLORS.bgHover, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.textMuted, cursor: "pointer" }}>Sign out</button>
            </div>
          )}
        </div>
      </nav>

      <main style={{ flex: 1, overflow: "auto", padding: 28 }}>
        <PresenceStrip online={presenceOnline} />
        <PageComponent pluginBase={pluginPages.find((p) => p.tool === resolvedPage)?.base} />
      </main>
    </div>
  );
}
