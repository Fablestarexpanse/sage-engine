import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import axios from "axios";
import WorldBuilderPage from "./builder/WorldBuilderPage.jsx";
import PlayerAccountsTab from "./PlayerAccountsTab.jsx";
import ProficienciesPage from "./ProficienciesPage.jsx";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE, WS_BASE } from "./apiConfig.js";

// ═══════════════════════════════════════════════════════════════
// FABLESTAR MUD — WORLD ADMINISTRATION CONSOLE v2
// Backend management interface with integrated AI Forge
// ═══════════════════════════════════════════════════════════════

const LS_ADMIN_TOKEN = "fablestar_admin_token";

/** Tool ids enforced by Nexus (see fablestar.admin.admin_security.NAV_TOOL_IDS). */
const ALL_ADMIN_TOOLS = [
  "dashboard", "forge", "operations", "players", "world", "entities",
  "items", "glyphs", "skills", "locations", "builder", "server", "content", "settings", "team",
];

function adminWsBase() {
  return WS_BASE.replace(/\/?$/, "");
}

function adminPresenceWsUrl() {
  return `${adminWsBase()}/ws/admin`;
}

function adminLogsWsUrl() {
  return `${adminWsBase()}/ws/logs`;
}

function sendWsAuthToken(ws) {
  const t = localStorage.getItem(LS_ADMIN_TOKEN);
  if (t) ws.send(JSON.stringify({ type: "auth", token: t }));
}

function parseLeadingInt(val) {
  if (val == null || val === "") return 1;
  const m = String(val).match(/^(\d+)/);
  return m ? parseInt(m[1], 10) : 1;
}

function parseRoomType(val) {
  if (!val) return "chamber";
  const m = String(val).match(/^([a-z_]+)/i);
  return m ? m[1].toLowerCase() : "chamber";
}

function extractYamlRoomId(text) {
  if (!text) return null;
  const m = text.match(/^\s*id:\s*["']?([^"'\n#]+)/m);
  return m ? m[1].trim() : null;
}

// ─── Icon Components ───
const Icons = {
  Dashboard: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="4" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="11" width="7" height="10" rx="1"/>
    </svg>
  ),
  Players: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  ),
  World: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
    </svg>
  ),
  Entities: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
    </svg>
  ),
  Items: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>
    </svg>
  ),
  Glyphs: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
    </svg>
  ),
  Skills: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2l2.4 7.2L22 9.3l-6 4.6 2.3 7.1L12 17.8l-6.3 3.2L8 13.9 2 9.3l7.6-0.1L12 2z" />
      <path d="M8 12h8M12 8v8" opacity="0.35" />
    </svg>
  ),
  Locations: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
    </svg>
  ),
  Server: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>
    </svg>
  ),
  Content: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
    </svg>
  ),
  Settings: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  ),
  Search: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
  ),
  Plus: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  ),
  ChevronRight: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  ),
  Activity: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  ),
  Clock: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  ),
  Terminal: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
    </svg>
  ),
  Eye: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
    </svg>
  ),
  Edit: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  ),
  Trash: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </svg>
  ),
  Zap: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  ),
  Shield: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  Alert: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  Map: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>
    </svg>
  ),
  Forge: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2z"/><path d="M12 8v8"/><path d="M8 12h8"/><circle cx="12" cy="12" r="3" fill="currentColor" opacity="0.2"/>
      <path d="M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" strokeWidth="1" opacity="0.5"/>
    </svg>
  ),
  Send: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
    </svg>
  ),
  Copy: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  ),
  Refresh: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
    </svg>
  ),
  Check: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  Code: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
    </svg>
  ),
  Wand: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 4V2M15 16v-2M8 9h2M20 9h2M17.8 11.8L19 13M17.8 6.2L19 5M12.2 11.8L11 13M12.2 6.2L11 5"/><line x1="15" y1="9" x2="15.01" y2="9"/><path d="M3 21l9-9"/>
    </svg>
  ),
  Sparkles: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/><path d="M5 19l.5 1.5L7 21l-1.5.5L5 23l-.5-1.5L3 21l1.5-.5L5 19z"/><path d="M19 14l.5 1.5L21 16l-1.5.5L19 18l-.5-1.5L17 16l1.5-.5L19 14z"/>
    </svg>
  ),
  Save: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
    </svg>
  ),
  Thermometer: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 1 1 4 0Z"/>
    </svg>
  ),
  Fan: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="2"/><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  ),
  Chip: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="15" x2="23" y2="15"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="15" x2="4" y2="15"/>
    </svg>
  ),
  Ram: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="6" width="20" height="12" rx="2"/><line x1="6" y1="6" x2="6" y2="18"/><line x1="10" y1="6" x2="10" y2="18"/><line x1="14" y1="6" x2="14" y2="18"/><line x1="18" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  History: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/><path d="M2 12h2M20 12h2"/>
    </svg>
  ),
};

// ─── Utility Components ───
const Badge = ({ children, color, bg }) => {
  const { colors: COLORS } = useAdminTheme();
  const ac = color ?? COLORS.accent;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: "4px",
      fontSize: "11px", fontWeight: 600, letterSpacing: "0.03em", color: ac,
      background: bg || `${ac}18`, fontFamily: "'JetBrains Mono', monospace",
    }}>{children}</span>
  );
};

const StatusDot = ({ color, pulse }) => (
  <span style={{
    display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: color,
    boxShadow: pulse ? `0 0 8px ${color}` : "none",
    animation: pulse ? "pulse 2s ease-in-out infinite" : "none",
  }} />
);

const Pill = ({ label, value, color }) => {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, padding: "6px 12px",
      background: COLORS.bgCard, borderRadius: 6, border: `1px solid ${COLORS.border}`,
    }}>
      <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>{label}</span>
      <span style={{ fontSize: 13, color: color || COLORS.text, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace" }}>{value}</span>
    </div>
  );
};

const ActionButton = ({ children, variant = "default", small, onClick, icon, disabled, title }) => {
  const { colors: COLORS } = useAdminTheme();
  const [hovered, setHovered] = useState(false);
  const variants = {
    default: { bg: COLORS.bgCard, border: COLORS.border, color: COLORS.text, hoverBg: COLORS.bgHover },
    primary: { bg: COLORS.accent, border: COLORS.accent, color: "#fff", hoverBg: COLORS.accentSoft },
    danger: { bg: "transparent", border: COLORS.danger, color: COLORS.danger, hoverBg: COLORS.dangerBg },
    success: { bg: "transparent", border: COLORS.success, color: COLORS.success, hoverBg: COLORS.successBg },
    ghost: { bg: "transparent", border: "transparent", color: COLORS.textMuted, hoverBg: COLORS.bgHover },
    forge: { bg: COLORS.forgeGlow, border: COLORS.forge, color: COLORS.forge, hoverBg: `${COLORS.forge}25` },
  };
  const v = variants[variant];
  return (
    <button type="button" title={title} onClick={onClick} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      disabled={disabled}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6, padding: small ? "4px 10px" : "8px 16px",
        fontSize: small ? 12 : 13, fontWeight: 500, fontFamily: "'DM Sans', sans-serif",
        border: `1px solid ${v.border}`, borderRadius: 6,
        background: hovered && !disabled ? v.hoverBg : v.bg, color: disabled ? COLORS.textDim : v.color,
        cursor: disabled ? "not-allowed" : "pointer", transition: "all 0.15s ease", whiteSpace: "nowrap",
        opacity: disabled ? 0.5 : 1,
      }}
    >{icon}{children}</button>
  );
};

const SearchBar = ({ placeholder, value, onChange }) => {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, padding: "8px 14px",
      background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 8, flex: 1, maxWidth: 320,
    }}>
      <Icons.Search />
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        style={{ border: "none", background: "none", outline: "none", color: COLORS.text, fontSize: 13, fontFamily: "'DM Sans', sans-serif", width: "100%" }} />
    </div>
  );
};

const TabBar = ({ tabs, active, onChange }) => {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ display: "flex", gap: 2, padding: 3, background: COLORS.bgInput, borderRadius: 8, border: `1px solid ${COLORS.border}` }}>
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)} style={{
          padding: "6px 14px", fontSize: 12, fontWeight: active === t.id ? 600 : 400, fontFamily: "'DM Sans', sans-serif",
          border: "none", borderRadius: 6, background: active === t.id ? COLORS.bgCard : "transparent",
          color: active === t.id ? COLORS.text : COLORS.textMuted, cursor: "pointer", transition: "all 0.15s ease",
        }}>{t.label}</button>
      ))}
    </div>
  );
};

const DataTable = ({ columns, rows, onRowClick }) => {
  const { colors: COLORS } = useAdminTheme();
  const [hoveredRow, setHoveredRow] = useState(null);
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr>
          {columns.map((col, i) => (
            <th key={i} title={col.title || undefined} style={{
              textAlign: "left", padding: "10px 14px", fontSize: 11, fontWeight: 600,
              color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em",
              borderBottom: `1px solid ${COLORS.border}`, fontFamily: "'JetBrains Mono', monospace", whiteSpace: "nowrap",
            }}>{col.label}</th>
          ))}
        </tr></thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} onClick={() => onRowClick?.(row)}
              onMouseEnter={() => setHoveredRow(ri)} onMouseLeave={() => setHoveredRow(null)}
              style={{ cursor: onRowClick ? "pointer" : "default", background: hoveredRow === ri ? COLORS.bgHover : "transparent", transition: "background 0.1s ease" }}>
              {columns.map((col, ci) => (
                <td key={ci} style={{
                  padding: "10px 14px", fontSize: 13, color: COLORS.text,
                  borderBottom: `1px solid ${COLORS.border}22`,
                  fontFamily: col.mono ? "'JetBrains Mono', monospace" : "'DM Sans', sans-serif", whiteSpace: "nowrap",
                }}>{col.render ? col.render(row) : row[col.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const StatCard = ({ label, value, change, color, icon, sparkData, title }) => {
  const { colors: COLORS } = useAdminTheme();
  return (
  <div title={title || undefined} style={{
    padding: "18px 20px", background: COLORS.bgCard, border: `1px solid ${COLORS.border}`,
    borderRadius: 10, display: "flex", flexDirection: "column", gap: 8, position: "relative", overflow: "hidden",
  }}>
    <div style={{
      position: "absolute", top: 0, right: 0, width: 80, height: 60, opacity: 0.06,
      display: "flex", alignItems: "center", justifyContent: "center", transform: "translate(10px, -5px) scale(3)", color: color || COLORS.accent,
    }}>{icon}</div>
    <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", fontWeight: 500 }}>{label}</div>
    <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
      <span style={{ fontSize: 28, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif", letterSpacing: "-0.02em" }}>{value}</span>
      {change && <span style={{ fontSize: 12, fontWeight: 600, color: change > 0 ? COLORS.success : COLORS.danger, fontFamily: "'JetBrains Mono', monospace" }}>{change > 0 ? "+" : ""}{change}%</span>}
    </div>
    {sparkData && (
      <svg viewBox="0 0 100 24" style={{ width: "100%", height: 24, marginTop: 4 }}>
        <polyline fill="none" stroke={color || COLORS.accent} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
          points={sparkData.map((v, i) => `${(i / (sparkData.length - 1)) * 100},${24 - (v / Math.max(...sparkData)) * 20}`).join(" ")} />
        <linearGradient id={`spark-${label}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color || COLORS.accent} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color || COLORS.accent} stopOpacity="0" />
        </linearGradient>
        <polygon fill={`url(#spark-${label})`}
          points={`0,24 ${sparkData.map((v, i) => `${(i / (sparkData.length - 1)) * 100},${24 - (v / Math.max(...sparkData)) * 20}`).join(" ")} 100,24`} />
      </svg>
    )}
  </div>
  );
};

const HostMachinePanel = ({ host, llmDetected, llmConfigured, llmConnected, llmBackend, llmModelsAlign }) => {
  const { colors: COLORS } = useAdminTheme();
  if (!host) return null;
  const bar = (pct, color) => (
    <div style={{ width: "100%", height: 5, borderRadius: 5, background: COLORS.bgInput, overflow: "hidden" }}>
      <div style={{ width: `${Math.min(100, Math.max(0, pct || 0))}%`, height: "100%", borderRadius: 5, background: color, transition: "width 0.35s ease" }} />
    </div>
  );
  const metricRow = (icon, label, value, icolor) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ color: icolor, flexShrink: 0, display: "flex" }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
        <div style={{ fontSize: 13, fontWeight: 600, color: icolor, fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
      </div>
    </div>
  );

  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20, display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Host machine</h3>
          <p style={{ margin: "6px 0 0", fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>
            {host.hostname || "—"} · {host.os || "—"}
            {host.python_version ? ` · Python ${host.python_version}` : ""}
          </p>
        </div>
        {(llmBackend === "lm_studio" || llmDetected || llmConfigured) && (
          <div style={{ textAlign: "right", maxWidth: 440 }}>
            <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Chat model{llmConnected ? "" : " (LLM offline)"}
            </div>
            <div style={{ fontSize: 12, color: COLORS.forge, fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, wordBreak: "break-word" }}>
              {llmDetected || llmConfigured || "—"}
            </div>
            {llmModelsAlign === false && llmConfigured && llmDetected && (
              <div style={{ fontSize: 10, color: COLORS.warning, marginTop: 4, fontFamily: "'JetBrains Mono', monospace" }}>
                Chat model id not in server list: {llmConfigured}
              </div>
            )}
          </div>
        )}
      </div>

      {!host.ok && host.error && (
        <div style={{ fontSize: 12, color: COLORS.warning, fontFamily: "'DM Sans', sans-serif" }}>{host.error}</div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>CPU load</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace" }}>{host.cpu_percent != null ? `${host.cpu_percent}%` : "—"}</span>
          </div>
          {bar(host.cpu_percent, COLORS.accent)}
          {host.cpu_count != null && (
            <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{host.cpu_count} logical CPUs</div>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>System memory</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: COLORS.info, fontFamily: "'JetBrains Mono', monospace" }}>{host.memory_percent != null ? `${host.memory_percent}%` : "—"}</span>
          </div>
          {bar(host.memory_percent, COLORS.info)}
          <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>
            {host.memory_used_gb != null && host.memory_total_gb != null
              ? `${host.memory_used_gb} GB / ${host.memory_total_gb} GB`
              : ""}
          </div>
        </div>
      </div>

      <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>Graphics</div>

      {host.gpus && host.gpus.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {host.gpus.map((gpu) => (
            <div
              key={gpu.index}
              style={{
                background: COLORS.bgInput,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 10,
                padding: 16,
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                gap: 24,
              }}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{gpu.name}</span>
                  <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999, background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}># {gpu.index}</span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {metricRow(<Icons.Thermometer />, "Temperature", gpu.temperature_c != null ? `${gpu.temperature_c}°C` : "—", COLORS.success)}
                  {metricRow(<Icons.Fan />, "Fan speed", gpu.fan_percent != null ? `${gpu.fan_percent}%` : "N/A", COLORS.info)}
                  {metricRow(<Icons.Clock />, "Clock", gpu.clock_mhz != null ? `${gpu.clock_mhz} MHz` : "—", COLORS.forge)}
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}><Icons.Chip /> GPU load</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace" }}>{gpu.gpu_util_percent ?? 0}%</span>
                  </div>
                  {bar(gpu.gpu_util_percent, COLORS.textMuted)}
                </div>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}><Icons.Ram /> VRAM</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.info, fontFamily: "'JetBrains Mono', monospace" }}>{gpu.memory_percent != null ? `${gpu.memory_percent}%` : "—"}</span>
                  </div>
                  {bar(gpu.memory_percent ?? 0, COLORS.cyan)}
                  <div style={{ fontSize: 10, color: COLORS.textDim, marginTop: 6, fontFamily: "'JetBrains Mono', monospace" }}>
                    {gpu.memory_used_mib != null && gpu.memory_total_mib != null
                      ? `${(gpu.memory_used_mib / 1024).toFixed(1)} GB / ${(gpu.memory_total_mib / 1024).toFixed(1)} GB`
                      : ""}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
                  <span style={{ color: COLORS.warning, display: "flex" }}><Icons.Zap /></span>
                  <span>
                    Power{" "}
                    <span style={{ color: COLORS.text, fontFamily: "'JetBrains Mono', monospace" }}>
                      {gpu.power_draw_w != null ? `${gpu.power_draw_w.toFixed(1)}W` : "—"}
                      {gpu.power_limit_w != null ? ` / ${gpu.power_limit_w.toFixed(1)}W` : ""}
                    </span>
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif" }}>
          No NVIDIA GPU telemetry (nvidia-smi not available or no driver). CPU and system RAM above still reflect this host.
        </div>
      )}
    </div>
  );
};

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

// Shared polled fetch — distinguishes "request failed" from "genuinely empty"
// so an API outage never renders as blank content.

function usePolledList(url, intervalMs, { enabled = true } = {}) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!enabled || !url) {
      setRows([]);
      setError("");
      return undefined;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await axios.get(url);
        if (cancelled) return;
        setRows(Array.isArray(data) ? data : []);
        setError("");
      } catch (e) {
        if (cancelled) return;
        // Keep last known rows; the banner explains the failure.
        setError(e.response?.data?.detail || e.message || "Request failed");
      }
    };
    load();
    const id = setInterval(load, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [url, intervalMs, enabled]);
  return { rows, error };
}

const FetchErrorBanner = ({ error, label }) => {
  const { colors: COLORS } = useAdminTheme();
  if (!error) return null;
  return (
    <div
      style={{
        padding: "10px 14px",
        borderRadius: 8,
        fontSize: 12,
        fontFamily: "'DM Sans', sans-serif",
        color: COLORS.danger,
        background: `${COLORS.danger}12`,
        border: `1px solid ${COLORS.danger}40`,
      }}
    >
      Failed to load {label}: {error} — showing last known data, retrying automatically.
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════
// AI FORGE — LLM Content Generation Studio
// ═══════════════════════════════════════════════════════════════

const FORGE_CATEGORIES = [
  {
    id: "room", label: "Room / Location", icon: <Icons.Locations />, colorKey: "info",
    desc: "Generate room descriptions, exits, ambient messages, and environmental details",
    fields: [
      { key: "zone", label: "Target Zone", type: "select", options: ["Outer Labyrinth", "Archive Depths", "The Crucible", "Shattered Gallery", "Resonance Caverns", "Tutorial Spire", "Pumpkin Fields"] },
      { key: "room_type", label: "Room Type", type: "select", options: ["chamber", "corridor", "hub", "dead_end", "hazard", "boss_arena", "sanctuary", "puzzle"] },
      { key: "depth", label: "Depth Level", type: "select", options: ["0 (Surface)", "1 (Shallow)", "2 (Mid)", "3 (Deep)", "4 (Abyssal)", "5 (Core)"] },
      { key: "mood", label: "Atmosphere", type: "select", options: ["foreboding", "serene", "chaotic", "ancient", "corrupted", "luminous", "decaying", "mechanical"] },
      { key: "details", label: "Additional Context", type: "textarea", placeholder: "Any specific features, lore connections, adjacent room context..." },
    ],
    promptTemplates: [
      "Generate a detailed room with base description, 3 time-of-day variants, and 2 ambient messages",
      "Create a puzzle room with environmental clues and hidden interactions",
      "Design a boss arena with phase-transition descriptions",
      "Write 5 connected corridor rooms with a thematic progression",
    ],
  },
  {
    id: "entity", label: "Entity / NPC", icon: <Icons.Entities />, colorKey: "warning",
    desc: "Create NPCs with dialogue, behavior patterns, combat abilities, and memory templates",
    fields: [
      { key: "entity_type", label: "Entity Type", type: "select", options: ["Hunter", "Watcher", "Guide", "Archivist", "Boss", "Vendor", "Ambient", "Quest NPC"] },
      { key: "zone", label: "Home Zone", type: "select", options: ["Outer Labyrinth", "Archive Depths", "The Crucible", "Shattered Gallery", "Resonance Caverns"] },
      { key: "level_range", label: "Level Range", type: "select", options: ["1-10 (Novice)", "11-25 (Intermediate)", "26-45 (Advanced)", "46-60 (Expert)", "61+ (Legendary)"] },
      { key: "behavior", label: "Behavior Pattern", type: "select", options: ["patrol", "static", "ambient", "scripted", "adaptive", "territorial", "fleeing", "stalking"] },
      { key: "details", label: "Character Concept", type: "textarea", placeholder: "Personality, backstory hooks, unique traits, combat style..." },
    ],
    promptTemplates: [
      "Create a Hunter entity with adaptive combat AI and 3 combat phases",
      "Design a Guide NPC with branching dialogue tree and lore delivery",
      "Generate an Archivist with a knowledge quiz mechanic",
      "Build a Vendor with personality, inventory theming, and bartering dialogue",
    ],
  },
  {
    id: "item", label: "Item", icon: <Icons.Items />, colorKey: "success",
    desc: "Design equipment, consumables, lore objects, and key items with stats and flavor text",
    fields: [
      { key: "item_type", label: "Item Type", type: "select", options: ["Equipment", "Consumable", "Material", "Key", "Lore", "Currency", "Artifact"] },
      { key: "rarity", label: "Rarity", type: "select", options: ["common", "uncommon", "rare", "epic", "legendary"] },
      { key: "theme", label: "Thematic Origin", type: "select", options: ["Labyrinth-forged", "Ancient Conduit tech", "Void-touched", "Resonance crystal", "Organic/living", "Mechanical/construct"] },
      { key: "details", label: "Item Concept", type: "textarea", placeholder: "Function, visual appearance, lore significance..." },
    ],
    promptTemplates: [
      "Generate a set of 5 themed loot drops for a specific zone",
      "Design a legendary artifact with lore, stats, and discovery quest hook",
      "Create a consumable crafting chain with 3 tiers of ingredients",
      "Write flavor text for 10 common materials found in the labyrinth",
    ],
  },
  {
    id: "glyph", label: "Glyph / Ability", icon: <Icons.Glyphs />, colorKey: "accent",
    desc: "Design glyph tattoos with mechanics, visual descriptions, and balance parameters",
    fields: [
      { key: "category", label: "Category", type: "select", options: ["Combat", "Defense", "Utility", "Perception", "Movement", "Social"] },
      { key: "tier", label: "Tier", type: "select", options: ["1 (Initiate)", "2 (Adept)", "3 (Master)", "4 (Transcendent)", "5 (Mythic)"] },
      { key: "body_slot", label: "Body Slot", type: "select", options: ["forearm", "upper arm", "chest", "back", "calf", "thigh", "palm", "temple", "spine", "shoulder"] },
      { key: "details", label: "Ability Concept", type: "textarea", placeholder: "Mechanical effect, visual manifestation, lore origin..." },
    ],
    promptTemplates: [
      "Design a glyph chain: 3 related glyphs that combo together",
      "Create a defensive glyph with scaling based on adaptive level",
      "Generate a utility glyph tree with 5 progression tiers",
      "Design a mythic-tier glyph with dramatic inscription sequence narrative",
    ],
  },
  {
    id: "quest", label: "Quest / Objective", icon: <Icons.Content />, colorKey: "danger",
    desc: "Create quest chains with objectives, branching paths, dialogue, and reward structures",
    fields: [
      { key: "quest_type", label: "Quest Type", type: "select", options: ["Main story", "Side quest", "Discovery", "Repeatable", "Event", "Hidden", "Tutorial"] },
      { key: "difficulty", label: "Difficulty", type: "select", options: ["Trivial", "Easy", "Medium", "Hard", "Legendary"] },
      { key: "zone", label: "Zone", type: "select", options: ["Outer Labyrinth", "Archive Depths", "The Crucible", "Shattered Gallery", "Resonance Caverns", "Multi-zone"] },
      { key: "details", label: "Quest Concept", type: "textarea", placeholder: "Story hook, objectives, key NPCs, reward ideas..." },
    ],
    promptTemplates: [
      "Create a 3-part quest chain with branching outcomes",
      "Design a hidden discovery quest with environmental clue progression",
      "Generate a repeatable hunt quest with adaptive difficulty scaling",
      "Build a tutorial quest that teaches glyph combat mechanics naturally",
    ],
  },
  {
    id: "dialogue", label: "Dialogue Tree", icon: <Icons.Activity />, colorKey: "cyan",
    desc: "Write NPC conversation flows with conditions, personality, and memory integration",
    fields: [
      { key: "npc_type", label: "NPC Type", type: "select", options: ["Guide", "Archivist", "Vendor", "Quest giver", "Lore keeper", "Antagonist", "Fellow Conduit"] },
      { key: "tone", label: "Personality Tone", type: "select", options: ["cryptic", "friendly", "hostile", "melancholic", "manic", "scholarly", "fearful", "ancient"] },
      { key: "context", label: "Conversation Context", type: "select", options: ["First meeting", "Returning player", "Quest delivery", "Lore dump", "Trading", "Warning", "Betrayal"] },
      { key: "details", label: "Dialogue Concept", type: "textarea", placeholder: "Topic, emotional arc, information to convey, branching triggers..." },
    ],
    promptTemplates: [
      "Write a first-meeting dialogue with 3 personality-based response branches",
      "Create a lore-delivery conversation that reveals info through questions",
      "Design a vendor haggling dialogue with price negotiation mechanics",
      "Generate a cryptic warning dialogue with hidden clue integration",
    ],
  },
  {
    id: "zone", label: "Zone / Region", icon: <Icons.World />, colorKey: "forge",
    desc: "Design entire zones with room layouts, entity populations, lore, and progression flow",
    fields: [
      { key: "zone_type", label: "Zone Type", type: "select", options: ["exploration", "dungeon", "boss", "safe", "tutorial", "puzzle", "gauntlet"] },
      { key: "depth", label: "Depth Level", type: "select", options: ["0 (Surface)", "1 (Shallow)", "2 (Mid)", "3 (Deep)", "4 (Abyssal)", "5 (Core)"] },
      { key: "room_count", label: "Approximate Rooms", type: "select", options: ["10-20 (Small)", "20-50 (Medium)", "50-100 (Large)", "100+ (Massive)"] },
      { key: "details", label: "Zone Concept", type: "textarea", placeholder: "Theme, narrative purpose, key landmarks, unique mechanics..." },
    ],
    promptTemplates: [
      "Design a complete zone blueprint with room graph and entity placement",
      "Create a dungeon zone with 3 puzzle rooms leading to a boss encounter",
      "Generate a safe hub zone with vendors, lore NPCs, and social spaces",
      "Build an adaptive gauntlet zone that escalates based on player performance",
    ],
  },
];

// Resolve category colors from the ACTIVE theme so Forge follows light/dark mode
// (a static dark-palette lookup here previously pinned these to dark-mode colors).
function useForgeCategories() {
  const { colors } = useAdminTheme();
  return useMemo(
    () => FORGE_CATEGORIES.map((c) => ({ ...c, color: colors[c.colorKey] || colors.accent })),
    [colors]
  );
}

const ForgePromptTemplateButton = ({ tmpl, cat, onPick }) => {
  const { colors: COLORS } = useAdminTheme();
  const [h, setH] = useState(false);
  return (
    <button type="button" onClick={() => onPick(tmpl)}
      onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
      style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
        background: h ? `${cat.color}10` : "transparent",
        border: `1px solid ${h ? cat.color + "30" : COLORS.border}`,
        borderRadius: 6, cursor: "pointer", textAlign: "left",
        color: COLORS.text, fontSize: 12, fontFamily: "'DM Sans', sans-serif",
        transition: "all 0.12s ease",
      }}
    >
      <span style={{ color: cat.color, flexShrink: 0 }}><Icons.Sparkles /></span>
      {tmpl}
    </button>
  );
};

const ForgeChat = ({ category, onClose }) => {
  const { colors: COLORS } = useAdminTheme();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [yamlPreview, setYamlPreview] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [formValues, setFormValues] = useState({});
  const [showYaml, setShowYaml] = useState(false);
  const [lastInjectId, setLastInjectId] = useState(null);
  const [injectBusy, setInjectBusy] = useState(false);
  const chatRef = useRef(null);
  const forgeCategories = useForgeCategories();
  const cat = forgeCategories.find(c => c.id === category);

  const runGeneration = useCallback(async (prompt) => {
    setIsGenerating(true);
    const contextParts = [];
    Object.entries(formValues).forEach(([k, v]) => {
      if (v && k !== "details") contextParts.push(`${k}: ${v}`);
    });
    const contextStr = contextParts.length > 0 ? `\n\nContext: ${contextParts.join(", ")}` : "";
    const fullSeed = prompt + contextStr;

    setMessages((prev) => [...prev,
      { role: "user", content: fullSeed },
      { role: "assistant", content: null, loading: true },
    ]);

    try {
      let yaml = "";
      let parsedId = null;
      if (category === "room") {
        const { data } = await axios.post(`${API_BASE}/forge/generate`, {
          seed: fullSeed,
          room_type: parseRoomType(formValues.room_type),
          depth: parseLeadingInt(formValues.depth),
        });
        yaml = data.yaml;
        parsedId = data.id ?? null;
      } else {
        const { data } = await axios.post(`${API_BASE}/forge/generate-content`, {
          category,
          seed: fullSeed,
          context: formValues,
        });
        yaml = data.yaml;
        const root = data.data;
        if (root && typeof root === "object" && root.id) parsedId = root.id;
      }
      const responseText =
        `**${cat.label}** generated via Nexus. Review YAML on the right. **Rooms**: deploy writes \`content/world/zones/<zone>/rooms/\` (needs \`id: zone:slug\`). **Entities / items**: use **Deploy** to save under \`content/world/entities/\` or \`items/\`. **Other categories**: copy YAML into the repo manually — no inject route yet.`;
      setMessages((prev) => prev.map((m, i) =>
        (i === prev.length - 1 ? { role: "assistant", content: responseText, loading: false } : m)
      ));
      setYamlPreview(yaml);
      setLastInjectId(parsedId || extractYamlRoomId(yaml));
      setShowYaml(true);
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : (detail ? JSON.stringify(detail) : (e.message || "Request failed"));
      setMessages((prev) => prev.map((m, i) =>
        (i === prev.length - 1 ? { role: "assistant", content: `**Error:** ${msg}`, loading: false } : m)
      ));
      setYamlPreview(null);
      setLastInjectId(null);
    } finally {
      setIsGenerating(false);
    }
  }, [category, formValues, cat]);

  const handleSend = () => {
    if (!input.trim() || isGenerating) return;
    runGeneration(input.trim());
    setInput("");
  };

  const copyYaml = () => {
    if (yamlPreview) navigator.clipboard.writeText(yamlPreview);
  };

  const canDeployYaml = category === "room" || category === "entity" || category === "item";

  const deployContent = async () => {
    if (!yamlPreview || !canDeployYaml) return;
    setInjectBusy(true);
    try {
      if (category === "room") {
        const rid = lastInjectId || extractYamlRoomId(yamlPreview);
        if (!rid || !rid.includes(":")) {
          window.alert("Room YAML needs an id like zone_key:room_slug to deploy.");
          return;
        }
        await axios.post(`${API_BASE}/forge/inject`, { id: rid, yaml_content: yamlPreview });
        window.alert(`Saved room to content/world/zones (${rid}).`);
        return;
      }
      if (category === "entity") {
        let eid = lastInjectId || extractYamlRoomId(yamlPreview);
        if (!eid || !/^[a-zA-Z0-9_]+$/.test(String(eid).trim())) {
          const p = window.prompt("Entity ID (filename without .yaml):", eid ? String(eid).trim() : "");
          if (p === null) return;
          eid = String(p).trim();
        }
        if (!eid || !/^[a-zA-Z0-9_]+$/.test(eid)) {
          window.alert("Invalid entity id (use letters, numbers, underscores).");
          return;
        }
        await axios.put(`${API_BASE}/content/entities/${eid}/yaml`, {
          path: `entities/${eid}`,
          yaml_content: yamlPreview,
        });
        window.alert(`Saved entity to content/world/entities/${eid}.yaml`);
        try {
          await axios.post(`${API_BASE}/content/cache/reload`);
        } catch {
          /* cache reload is optional (may require server tool) */
        }
        return;
      }
      if (category === "item") {
        let iid = lastInjectId || extractYamlRoomId(yamlPreview);
        if (!iid || !/^[a-zA-Z0-9_]+$/.test(String(iid).trim())) {
          const p = window.prompt("Item ID (filename without .yaml):", iid ? String(iid).trim() : "");
          if (p === null) return;
          iid = String(p).trim();
        }
        if (!iid || !/^[a-zA-Z0-9_]+$/.test(iid)) {
          window.alert("Invalid item id (use letters, numbers, underscores).");
          return;
        }
        await axios.put(`${API_BASE}/content/items/${iid}/yaml`, {
          path: `items/${iid}`,
          yaml_content: yamlPreview,
        });
        window.alert(`Saved item to content/world/items/${iid}.yaml`);
        try {
          await axios.post(`${API_BASE}/content/cache/reload`);
        } catch {
          /* optional */
        }
      }
    } catch (e) {
      const detail = e.response?.data?.detail;
      window.alert(typeof detail === "string" ? detail : (e.message || "Deploy failed"));
    } finally {
      setInjectBusy(false);
    }
  };

  const handleTemplateClick = (template) => {
    setSelectedTemplate(template);
    setInput(template);
  };

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages]);

  if (!cat) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 0 }}>
      {/* Forge Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "16px 20px", borderBottom: `1px solid ${COLORS.border}`,
        background: `linear-gradient(135deg, ${COLORS.bgCard} 0%, ${cat.color}08 100%)`,
        borderRadius: "10px 10px 0 0",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: `${cat.color}15`, border: `1px solid ${cat.color}30`,
            display: "flex", alignItems: "center", justifyContent: "center", color: cat.color,
          }}>{cat.icon}</div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif", display: "flex", alignItems: "center", gap: 8 }}>
              AI Forge: {cat.label}
              <Badge color={COLORS.forge}>LLM-Assisted</Badge>
            </div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", marginTop: 2 }}>{cat.desc}</div>
          </div>
        </div>
        <ActionButton small variant="ghost" onClick={onClose}>Close</ActionButton>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left: Context Panel + Chat */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", borderRight: showYaml ? `1px solid ${COLORS.border}` : "none", minWidth: 0 }}>
          {/* Context Fields */}
          <div style={{
            padding: "14px 18px", borderBottom: `1px solid ${COLORS.border}`, background: COLORS.bgCard,
            display: "flex", flexDirection: "column", gap: 10, flexShrink: 0,
          }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>
              Generation Context
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
              {cat.fields.filter(f => f.type === "select").map(field => (
                <div key={field.key}>
                  <label style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", marginBottom: 3, display: "block" }}>{field.label}</label>
                  <select
                    value={formValues[field.key] || ""}
                    onChange={e => setFormValues(prev => ({ ...prev, [field.key]: e.target.value }))}
                    style={{
                      width: "100%", padding: "6px 10px", background: COLORS.bgInput,
                      border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text,
                      fontSize: 12, fontFamily: "'DM Sans', sans-serif",
                    }}
                  >
                    <option value="">Select...</option>
                    {field.options.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
              ))}
            </div>
            {cat.fields.filter(f => f.type === "textarea").map(field => (
              <div key={field.key}>
                <label style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", marginBottom: 3, display: "block" }}>{field.label}</label>
                <textarea
                  value={formValues[field.key] || ""}
                  onChange={e => setFormValues(prev => ({ ...prev, [field.key]: e.target.value }))}
                  placeholder={field.placeholder}
                  rows={2}
                  style={{
                    width: "100%", padding: "8px 10px", background: COLORS.bgInput,
                    border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text,
                    fontSize: 12, fontFamily: "'DM Sans', sans-serif", resize: "vertical",
                  }}
                />
              </div>
            ))}
          </div>

          {/* Quick Templates */}
          {messages.length === 0 && (
            <div style={{ padding: "14px 18px", borderBottom: `1px solid ${COLORS.border}`, flexShrink: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace", marginBottom: 10 }}>
                Prompt Templates
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {cat.promptTemplates.map((tmpl, i) => (
                  <ForgePromptTemplateButton key={i} tmpl={tmpl} cat={cat} onPick={handleTemplateClick} />
                ))}
              </div>
            </div>
          )}

          {/* Chat Messages */}
          <div ref={chatRef} style={{ flex: 1, overflow: "auto", padding: "14px 18px", display: "flex", flexDirection: "column", gap: 14 }}>
            {messages.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, gap: 12, opacity: 0.5 }}>
                <Icons.Forge />
                <span style={{ fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
                  Set your context above, then describe what you want to create
                </span>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} style={{
                display: "flex", flexDirection: "column", gap: 6,
                alignItems: msg.role === "user" ? "flex-end" : "flex-start",
              }}>
                <div style={{
                  maxWidth: "85%", padding: "10px 14px", borderRadius: 10,
                  background: msg.role === "user" ? `${COLORS.accent}20` : COLORS.bgCard,
                  border: `1px solid ${msg.role === "user" ? COLORS.accent + "30" : COLORS.border}`,
                }}>
                  {msg.loading ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, color: COLORS.forge }}>
                      <span style={{ animation: "pulse 1.5s ease-in-out infinite" }}><Icons.Sparkles /></span>
                      <span style={{ fontSize: 12, fontFamily: "'DM Sans', sans-serif" }}>Generating content...</span>
                    </div>
                  ) : (
                    <div style={{ fontSize: 13, color: COLORS.text, lineHeight: 1.6, fontFamily: "'DM Sans', sans-serif", whiteSpace: "pre-wrap" }}>
                      {msg.content?.split("**").map((part, pi) =>
                        pi % 2 === 1 ? <strong key={pi} style={{ color: cat.color }}>{part}</strong> : part
                      )}
                    </div>
                  )}
                </div>
                {msg.role === "assistant" && !msg.loading && (
                  <div style={{ display: "flex", gap: 4, paddingLeft: 4 }}>
                    <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={() => {
                      const lastUserMsg = [...messages].reverse().find(m => m.role === "user");
                      if (lastUserMsg) runGeneration(lastUserMsg.content);
                    }}>Regenerate</ActionButton>
                    <ActionButton small variant="ghost" icon={<Icons.Copy />} onClick={copyYaml}>Copy</ActionButton>
                    {!showYaml && <ActionButton small variant="ghost" icon={<Icons.Code />} onClick={() => setShowYaml(true)}>Show YAML</ActionButton>}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Input Bar */}
          <div style={{
            padding: "12px 18px", borderTop: `1px solid ${COLORS.border}`, background: COLORS.bgCard,
            display: "flex", gap: 10, alignItems: "flex-end", flexShrink: 0,
          }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder={`Describe the ${cat.label.toLowerCase()} you want to create...`}
              rows={2}
              style={{
                flex: 1, padding: "10px 14px", background: COLORS.bgInput,
                border: `1px solid ${COLORS.border}`, borderRadius: 8, color: COLORS.text,
                fontSize: 13, fontFamily: "'DM Sans', sans-serif", resize: "none", outline: "none",
              }}
            />
            <ActionButton variant="forge" onClick={handleSend} disabled={!input.trim() || isGenerating}
              icon={isGenerating ? <span style={{ animation: "pulse 1s infinite" }}><Icons.Sparkles /></span> : <Icons.Send />}>
              {isGenerating ? "Forging..." : "Generate"}
            </ActionButton>
          </div>
        </div>

        {/* Right: YAML Preview Panel */}
        {showYaml && (
          <div style={{ width: "45%", minWidth: 340, display: "flex", flexDirection: "column", background: COLORS.bgPanel }}>
            <div style={{
              padding: "12px 16px", borderBottom: `1px solid ${COLORS.border}`,
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Icons.Code />
                <span style={{ fontSize: 13, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>YAML Output</span>
                <Badge color={COLORS.success}>valid</Badge>
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                <ActionButton small variant="ghost" icon={<Icons.Copy />} onClick={copyYaml}>
                  {canDeployYaml ? "Copy" : "Copy YAML"}
                </ActionButton>
                {canDeployYaml && (
                  <ActionButton small variant="success" icon={<Icons.Save />} onClick={deployContent} disabled={injectBusy}>
                    {category === "room" ? "Accept" : category === "entity" ? "Deploy to entities/" : "Deploy to items/"}
                  </ActionButton>
                )}
                <ActionButton small variant="ghost" onClick={() => setShowYaml(false)}>Hide</ActionButton>
              </div>
            </div>
            {!canDeployYaml && yamlPreview && (
              <div style={{ padding: "8px 16px", fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", borderBottom: `1px solid ${COLORS.border}` }}>
                Save this YAML manually to the appropriate <code style={{ color: COLORS.textDim }}>content/</code> directory — no deploy path for this category yet.
              </div>
            )}
            <pre style={{
              flex: 1, overflow: "auto", padding: "14px 16px", margin: 0,
              fontSize: 11.5, lineHeight: 1.55, color: COLORS.text,
              fontFamily: "'JetBrains Mono', monospace",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {yamlPreview || "# YAML preview will appear here after generation..."}
            </pre>
            <div style={{
              padding: "10px 16px", borderTop: `1px solid ${COLORS.border}`,
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <div style={{ display: "flex", gap: 6 }}>
                {canDeployYaml ? (
                  <ActionButton small variant="success" icon={<Icons.Check />} onClick={deployContent} disabled={injectBusy || !yamlPreview}>
                    {injectBusy
                      ? "Deploying…"
                      : category === "room"
                        ? "Accept & Deploy"
                        : category === "entity"
                          ? "Deploy to entities/"
                          : "Deploy to items/"}
                  </ActionButton>
                ) : (
                  <ActionButton small variant="default" icon={<Icons.Copy />} onClick={copyYaml} disabled={!yamlPreview}>
                    Copy YAML
                  </ActionButton>
                )}
                <ActionButton small variant="default" icon={<Icons.Save />} onClick={copyYaml}>Save Draft</ActionButton>
              </div>
              <ActionButton small variant="danger" icon={<Icons.Trash />}>Discard</ActionButton>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const ForgeCategoryPickCard = ({ cat, onPick }) => {
  const { colors: COLORS } = useAdminTheme();
  const [h, setH] = useState(false);
  return (
    <button
      type="button"
      onClick={() => onPick(cat.id)}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "flex", gap: 14, alignItems: "flex-start", padding: 18,
        background: h ? `${cat.color}08` : COLORS.bgCard,
        border: `1px solid ${h ? cat.color + "40" : COLORS.border}`,
        borderRadius: 10, cursor: "pointer", textAlign: "left",
        transition: "all 0.15s ease",
      }}
    >
      <div style={{
        width: 44, height: 44, borderRadius: 10, flexShrink: 0,
        background: `${cat.color}12`, border: `1px solid ${cat.color}25`,
        display: "flex", alignItems: "center", justifyContent: "center", color: cat.color,
        transition: "all 0.15s ease",
        transform: h ? "scale(1.08)" : "scale(1)",
      }}>{cat.icon}</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif", marginBottom: 4 }}>{cat.label}</div>
        <div style={{ fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5, fontFamily: "'DM Sans', sans-serif" }}>{cat.desc}</div>
        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          {cat.promptTemplates.slice(0, 2).map((t, i) => (
            <span key={i} style={{
              fontSize: 10, color: COLORS.textDim, padding: "2px 6px",
              background: COLORS.bgInput, borderRadius: 3,
              fontFamily: "'JetBrains Mono', monospace", maxWidth: 180,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>{t}</span>
          ))}
        </div>
      </div>
      <span style={{ color: COLORS.textDim, opacity: h ? 1 : 0.4, transition: "opacity 0.15s" }}><Icons.ChevronRight /></span>
    </button>
  );
};

const AiForgePage = () => {
  const { colors: COLORS } = useAdminTheme();
  const forgeCategories = useForgeCategories();
  const [activeCategory, setActiveCategory] = useState(null);
  const [historyFilter, setHistoryFilter] = useState("all");
  const [forgeHistoryRows] = useState([]);
  const [llmSnap, setLlmSnap] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/llm/status`);
        setLlmSnap(data);
      } catch {
        setLlmSnap(null);
      }
    };
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);

  if (activeCategory) {
    return (
      <div style={{
        display: "flex", flexDirection: "column", height: "calc(100vh - 56px)",
        background: COLORS.bgCard, borderRadius: 10, border: `1px solid ${COLORS.border}`, overflow: "hidden",
      }}>
        <ForgeChat category={activeCategory} onClose={() => setActiveCategory(null)} />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif", display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ color: COLORS.forge }}><Icons.Forge /></span>
            AI Forge
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
            LLM-powered content generation for every system in the Fablestar
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <Pill label="Backend" value={llmSnap?.primary_backend || "—"} color={COLORS.info} />
          <Pill label="Chat model" value={llmSnap?.chat_model || "—"} color={COLORS.forge} />
          <Pill
            label="LM link"
            value={llmSnap?.connected ? `${llmSnap.latency_ms ?? "?"} ms` : "offline"}
            color={llmSnap?.connected ? COLORS.success : COLORS.danger}
          />
        </div>
      </div>
      <p style={{ margin: 0, fontSize: 12, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif" }}>
        Forge uses the same OpenAI-compatible client as in-game narration (<code style={{ color: COLORS.textMuted }}>look</code>). Configure it on Server & Performance → LM Studio / LLM.
      </p>

      {/* Category Grid */}
      <div>
        <h3 style={{ margin: "0 0 14px", fontSize: 13, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>
          Choose Content Type
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
          {forgeCategories.map((cat) => (
            <ForgeCategoryPickCard key={cat.id} cat={cat} onPick={setActiveCategory} />
          ))}
        </div>
      </div>

      {/* Generation History */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace", display: "flex", alignItems: "center", gap: 8 }}>
            <Icons.History /> Generation History
          </h3>
          <TabBar tabs={[
            { id: "all", label: "All" },
            { id: "accepted", label: "Accepted" },
            { id: "editing", label: "Editing" },
            { id: "rejected", label: "Rejected" },
          ]} active={historyFilter} onChange={setHistoryFilter} />
        </div>
        <div style={{
          background: COLORS.bgCard, border: `1px solid ${COLORS.border}`,
          borderRadius: 10, overflow: "hidden",
        }}>
          <DataTable
            columns={[
              { label: "Type", render: row => {
                const cat = forgeCategories.find(c => c.id === row.category);
                return <Badge color={cat?.color}>{row.category}</Badge>;
              }},
              { label: "Prompt", render: row => (
                <span style={{ maxWidth: 360, display: "inline-block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {row.prompt}
                </span>
              )},
              { label: "Time", key: "timestamp", mono: true },
              { label: "Status", render: row => (
                <Badge color={
                  row.status === "accepted" ? COLORS.success :
                  row.status === "editing" ? COLORS.warning : COLORS.danger
                }>{row.status}</Badge>
              )},
              { label: "", render: row => (
                <div style={{ display: "flex", gap: 4 }}>
                  <ActionButton small variant="ghost" icon={<Icons.Eye />}>View</ActionButton>
                  <ActionButton small variant="ghost" icon={<Icons.Edit />}>Edit</ActionButton>
                  <ActionButton small variant="ghost" icon={<Icons.Refresh />}>Redo</ActionButton>
                </div>
              )},
            ]}
            rows={forgeHistoryRows.filter((h) => historyFilter === "all" || h.status === historyFilter)}
          />
        </div>
        {forgeHistoryRows.length === 0 && (
          <p style={{ margin: "10px 0 0", fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
            No saved generations yet. History will appear here once the Nexus stores Forge runs (or use session-only workflow for now).
          </p>
        )}
      </div>
    </div>
  );
};


const LmStudioPanel = () => {
  const { colors: COLORS } = useAdminTheme();
  const [llmStatus, setLlmStatus] = useState(null);
  const [llmForm, setLlmForm] = useState({
    primary_backend: "lm_studio",
    lm_studio_url: "http://localhost:1234/v1",
    ollama_url: "http://localhost:11434/v1",
    chat_model: "auto",
    temperature: 0.7,
    timeout_seconds: 10,
    lm_studio_key: "",
  });
  const [persistLlm, setPersistLlm] = useState(true);
  const [llmBusy, setLlmBusy] = useState(false);
  const [testReply, setTestReply] = useState("");
  const [connectResult, setConnectResult] = useState(null);

  const syncLlm = useCallback(async (forceRefresh = false) => {
    try {
      const { data } = await axios.get(`${API_BASE}/llm/status`, {
        params: forceRefresh ? { refresh: true } : undefined,
      });
      setLlmStatus(data);
      setLlmForm((prev) => ({
        ...prev,
        primary_backend: data.primary_backend,
        lm_studio_url: data.lm_studio_url,
        ollama_url: data.ollama_url,
        chat_model: data.chat_model,
        temperature: data.temperature,
        timeout_seconds: data.timeout_seconds,
      }));
    } catch {
      setLlmStatus(null);
    }
  }, []);

  useEffect(() => {
    syncLlm();
    const id = setInterval(() => syncLlm(false), 120000);
    return () => clearInterval(id);
  }, [syncLlm]);

  const connectLlm = async () => {
    setLlmBusy(true);
    setConnectResult(null);
    try {
      const { data } = await axios.patch(`${API_BASE}/llm/settings?persist=false`, {
        primary_backend: llmForm.primary_backend,
        lm_studio_url: llmForm.lm_studio_url,
        ollama_url: llmForm.ollama_url,
      });
      setLlmStatus(data);
      setLlmForm((prev) => ({
        ...prev,
        primary_backend: data.primary_backend,
        lm_studio_url: data.lm_studio_url,
        ollama_url: data.ollama_url,
        chat_model: data.chat_model,
        temperature: data.temperature,
        timeout_seconds: data.timeout_seconds,
      }));
      if (data.connected) {
        const det = data.detected_model ? ` · model: ${data.detected_model.length > 40 ? `${data.detected_model.slice(0, 38)}…` : data.detected_model}` : "";
        setConnectResult({ ok: true, msg: `Connected · ${data.latency_ms ?? "?"}ms · ${data.model_count ?? 0} model(s)${det}` });
      } else {
        setConnectResult({ ok: false, msg: data.error || "Backend unreachable" });
      }
    } catch (e) {
      const d = e.response?.data?.detail;
      setConnectResult({ ok: false, msg: typeof d === "string" ? d : (e.message || "Connection failed") });
    } finally {
      setLlmBusy(false);
    }
  };

  const saveLlmSettings = async () => {
    setLlmBusy(true);
    setTestReply("");
    try {
      const body = {
        primary_backend: llmForm.primary_backend,
        lm_studio_url: llmForm.lm_studio_url,
        ollama_url: llmForm.ollama_url,
        chat_model: llmForm.chat_model,
        temperature: Number(llmForm.temperature),
        timeout_seconds: Number(llmForm.timeout_seconds),
      };
      if (llmForm.lm_studio_key?.trim()) body.lm_studio_key = llmForm.lm_studio_key.trim();
      const { data } = await axios.patch(`${API_BASE}/llm/settings?persist=${persistLlm}`, body);
      setLlmStatus(data);
    } catch (e) {
      const d = e.response?.data?.detail;
      window.alert(typeof d === "string" ? d : (e.message || "Save failed"));
    } finally {
      setLlmBusy(false);
    }
  };

  const runLlmTest = async () => {
    setLlmBusy(true);
    setTestReply("");
    try {
      const { data } = await axios.post(`${API_BASE}/llm/test-completion`);
      setTestReply(data.reply || "");
    } catch (e) {
      setTestReply(e.response?.data?.detail || e.message || "failed");
    } finally {
      setLlmBusy(false);
    }
  };

  const inp = {
    width: "100%",
    padding: "8px 10px",
    background: COLORS.bgInput,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 6,
    color: COLORS.text,
    fontSize: 12,
    fontFamily: "'DM Sans', sans-serif",
  };

  return (
    <div style={{
      background: COLORS.bgCard,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 10,
      padding: 18,
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
      gap: 20,
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif", display: "flex", alignItems: "center", gap: 8 }}>
            <Icons.Zap /> LM Studio / LLM
          </h3>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <StatusDot color={llmStatus?.connected ? COLORS.success : COLORS.danger} pulse={llmStatus?.connected} />
            <span style={{ fontSize: 12, fontWeight: 600, color: llmStatus?.connected ? COLORS.success : COLORS.danger, fontFamily: "'DM Sans', sans-serif" }}>
              {llmStatus?.connected ? "Reachable" : "Not connected"}
            </span>
          </div>
        </div>
        <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.5, wordBreak: "break-all" }}>
          <div><strong style={{ color: COLORS.textDim }}>Base URL</strong> {llmStatus?.base_url || "—"}</div>
          <div>
            <strong style={{ color: COLORS.textDim }}>Detected</strong>{" "}
            <span style={{ color: COLORS.forge, fontWeight: 600 }}>{llmStatus?.detected_model || "—"}</span>
            {llmStatus?.detected_model_source === "loaded" && (
              <span style={{ color: COLORS.textDim, fontWeight: 400 }}> (loaded)</span>
            )}
          </div>
          <div><strong style={{ color: COLORS.textDim }}>Chat model id</strong> {llmStatus?.chat_model || "—"}</div>
          {llmStatus?.chat_model_auto && (
            <div style={{ color: COLORS.textDim, marginTop: 4, fontSize: 11 }}>
              Auto: Nexus sends the model the server lists (loaded / first entry). Set a specific id only if you use Ollama with several models or need to pin one name.
            </div>
          )}
          {llmStatus?.models_align === false && (
            <div style={{ color: COLORS.warning, marginTop: 6 }}>
              That chat model id is not in the server&apos;s model list. Switch to <code style={{ color: COLORS.textMuted }}>auto</code> or type an id from the list below.
            </div>
          )}
          {llmStatus?.model_count != null && (
            <div><strong style={{ color: COLORS.textDim }}>Models listed</strong> {llmStatus.model_count}</div>
          )}
          {llmStatus?.latency_ms != null && (
            <div><strong style={{ color: COLORS.textDim }}>List latency</strong> {llmStatus.latency_ms} ms</div>
          )}
          {llmStatus?.status_cached && (
            <div style={{ fontSize: 11, color: COLORS.textDim, marginTop: 4 }}>Status from cache (use Refresh for live probe)</div>
          )}
          {llmStatus?.error && (
            <div style={{ color: COLORS.danger, marginTop: 6 }}>{llmStatus.error}</div>
          )}
        </div>
        <p style={{ margin: 0, fontSize: 11, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.45 }}>
          Powers: <strong>AI Forge</strong> (room + generic YAML), in-game <strong>look</strong> narration, and the test button below. Start LM Studio, load a model, enable the local server (default <code style={{ color: COLORS.textMuted }}>http://localhost:1234</code>), then set the base URL here (include <code style={{ color: COLORS.textMuted }}>/v1</code>).
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={() => syncLlm(true)} disabled={llmBusy}>Refresh status</ActionButton>
          <ActionButton small variant="primary" icon={<Icons.Terminal />} onClick={runLlmTest} disabled={llmBusy}>Test chat</ActionButton>
        </div>
        {testReply && (
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", padding: 8, background: COLORS.bgInput, borderRadius: 6 }}>
            Test reply: {testReply}
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>Settings</div>
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>Backend</label>
        <select value={llmForm.primary_backend} onChange={(e) => { setLlmForm((p) => ({ ...p, primary_backend: e.target.value })); setConnectResult(null); }} style={inp}>
          <option value="lm_studio">LM Studio (OpenAI-compatible)</option>
          <option value="ollama">Ollama</option>
        </select>
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>LM Studio base URL</label>
        <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
          <input value={llmForm.lm_studio_url} onChange={(e) => { setLlmForm((p) => ({ ...p, lm_studio_url: e.target.value })); setConnectResult(null); }} style={{ ...inp, flex: 1 }} placeholder="http://localhost:1234/v1" />
          <button
            type="button"
            onClick={connectLlm}
            disabled={llmBusy || llmForm.primary_backend !== "lm_studio"}
            title={llmForm.primary_backend !== "lm_studio" ? "Switch backend to LM Studio to connect" : "Test connection to this URL"}
            style={{
              padding: "0 14px",
              background: llmBusy ? COLORS.bgInput : COLORS.accent,
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              fontFamily: "'DM Sans', sans-serif",
              cursor: llmBusy || llmForm.primary_backend !== "lm_studio" ? "not-allowed" : "pointer",
              opacity: llmForm.primary_backend !== "lm_studio" ? 0.35 : 1,
              whiteSpace: "nowrap",
              flexShrink: 0,
              transition: "background 0.15s",
            }}
          >
            {llmBusy ? "…" : "Connect"}
          </button>
        </div>
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>Ollama base URL</label>
        <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
          <input value={llmForm.ollama_url} onChange={(e) => { setLlmForm((p) => ({ ...p, ollama_url: e.target.value })); setConnectResult(null); }} style={{ ...inp, flex: 1 }} placeholder="http://localhost:11434/v1" />
          <button
            type="button"
            onClick={connectLlm}
            disabled={llmBusy || llmForm.primary_backend !== "ollama"}
            title={llmForm.primary_backend !== "ollama" ? "Switch backend to Ollama to connect" : "Test connection to this URL"}
            style={{
              padding: "0 14px",
              background: llmBusy ? COLORS.bgInput : COLORS.accent,
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              fontFamily: "'DM Sans', sans-serif",
              cursor: llmBusy || llmForm.primary_backend !== "ollama" ? "not-allowed" : "pointer",
              opacity: llmForm.primary_backend !== "ollama" ? 0.35 : 1,
              whiteSpace: "nowrap",
              flexShrink: 0,
              transition: "background 0.15s",
            }}
          >
            {llmBusy ? "…" : "Connect"}
          </button>
        </div>
        {connectResult && (
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 12px",
            borderRadius: 6,
            background: connectResult.ok ? COLORS.successBg : COLORS.dangerBg,
            border: `1px solid ${connectResult.ok ? COLORS.success : COLORS.danger}22`,
            fontSize: 11.5,
            fontFamily: "'JetBrains Mono', monospace",
            color: connectResult.ok ? COLORS.success : COLORS.danger,
          }}>
            <StatusDot color={connectResult.ok ? COLORS.success : COLORS.danger} pulse={connectResult.ok} />
            {connectResult.msg}
          </div>
        )}
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>Chat model id</label>
        <input list="llm-model-ids-server" value={llmForm.chat_model} onChange={(e) => setLlmForm((p) => ({ ...p, chat_model: e.target.value }))} style={inp} placeholder="auto — or exact model id from server" />
        <datalist id="llm-model-ids-server">
          <option value="auto" />
          {(llmStatus?.models || []).map((m) => <option key={m.id} value={m.id} />)}
        </datalist>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div>
            <label style={{ fontSize: 11, color: COLORS.textMuted }}>Temperature</label>
            <input type="number" step="0.05" min="0" max="2" value={llmForm.temperature} onChange={(e) => setLlmForm((p) => ({ ...p, temperature: e.target.value }))} style={inp} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: COLORS.textMuted }}>Timeout (s)</label>
            <input type="number" step="1" min="1" value={llmForm.timeout_seconds} onChange={(e) => setLlmForm((p) => ({ ...p, timeout_seconds: e.target.value }))} style={inp} />
          </div>
        </div>
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>API key (optional)</label>
        <input type="password" value={llmForm.lm_studio_key} onChange={(e) => setLlmForm((p) => ({ ...p, lm_studio_key: e.target.value }))} style={inp} placeholder={llmStatus?.lm_studio_key_set ? "Leave blank to keep current key" : "not-needed"} autoComplete="off" />
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: COLORS.textMuted, cursor: "pointer" }}>
          <input type="checkbox" checked={persistLlm} onChange={(e) => setPersistLlm(e.target.checked)} />
          Save to config/llm.toml (survives restart)
        </label>
        <ActionButton variant="primary" icon={<Icons.Save />} onClick={saveLlmSettings} disabled={llmBusy}>{llmBusy ? "Saving…" : "Apply settings"}</ActionButton>
      </div>
    </div>
  );
};


// ─── ComfyUI Workflows & Economy Panel ──────────────────────────────────────

const COMFY_TABS = [
  { id: "status",    label: "Status" },
  { id: "portrait",  label: "Portrait workflow" },
  { id: "scene",     label: "Scene/Area workflow" },
  { id: "economy",   label: "Economy" },
];

const ComfyUIPanel = () => {
  const { colors: COLORS } = useAdminTheme();
  const [tab, setTab] = useState("status");
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({
    enabled: false,
    base_url: "http://127.0.0.1:8188",
    workflow_path: "config/comfyui_character_portrait_workflow.json",
    positive_prompt_node_id: "57",
    output_node_id: "40",
    area_workflow_path: "config/comfyui_scene_workflow.json",
    area_positive_prompt_node_id: "16",
    area_output_node_id: "17",
    checkpoint_name: "",
    timeout_seconds: 600,
    poll_interval_seconds: 0.75,
    economy_enabled: true,
    starting_echo_credits: 50,
    portrait_generation_cost: 3,
    area_generation_cost: 3,
    character_create_portrait_cost: 3,
    currency_display_name: "pixels",
    pixels_per_usd: 100,
  });
  const [persist, setPersist] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saveMsg, setSaveMsg] = useState("");

  const syncStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/comfyui/status`);
      setStatus(data);
      setForm((prev) => ({
        ...prev,
        enabled: data.enabled ?? prev.enabled,
        base_url: data.base_url ?? prev.base_url,
        workflow_path: data.workflow_path ?? prev.workflow_path,
        positive_prompt_node_id: data.positive_prompt_node_id ?? prev.positive_prompt_node_id,
        output_node_id: data.output_node_id ?? prev.output_node_id,
        area_workflow_path: data.area_workflow_path ?? prev.area_workflow_path,
        area_positive_prompt_node_id: data.area_positive_prompt_node_id ?? prev.area_positive_prompt_node_id,
        area_output_node_id: data.area_output_node_id ?? prev.area_output_node_id,
        checkpoint_name: data.checkpoint_name ?? prev.checkpoint_name,
        timeout_seconds: data.timeout_seconds ?? prev.timeout_seconds,
        poll_interval_seconds: data.poll_interval_seconds ?? prev.poll_interval_seconds,
        economy_enabled: data.economy_enabled ?? prev.economy_enabled,
        starting_echo_credits: data.starting_echo_credits ?? prev.starting_echo_credits,
        portrait_generation_cost: data.portrait_generation_cost ?? prev.portrait_generation_cost,
        area_generation_cost: data.area_generation_cost ?? prev.area_generation_cost,
        character_create_portrait_cost: data.character_create_portrait_cost ?? prev.character_create_portrait_cost,
        currency_display_name: data.currency_display_name ?? prev.currency_display_name,
        pixels_per_usd: data.pixels_per_usd ?? prev.pixels_per_usd,
      }));
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    syncStatus();
    const id = setInterval(syncStatus, 120000);
    return () => clearInterval(id);
  }, [syncStatus]);

  const testConnection = async () => {
    setBusy(true);
    setTestResult(null);
    try {
      const { data } = await axios.post(`${API_BASE}/comfyui/test-connection`);
      setTestResult({ ok: data.reachable, msg: data.reachable ? `Reachable · ${data.base_url}` : (data.error || "Not reachable") });
    } catch (e) {
      setTestResult({ ok: false, msg: e.response?.data?.detail || e.message || "Request failed" });
    } finally {
      setBusy(false);
    }
  };

  const saveSettings = async () => {
    setBusy(true);
    setSaveMsg("");
    try {
      const body = { ...form };
      body.timeout_seconds = Number(form.timeout_seconds);
      body.poll_interval_seconds = Number(form.poll_interval_seconds);
      body.starting_echo_credits = Number(form.starting_echo_credits);
      body.portrait_generation_cost = Number(form.portrait_generation_cost);
      body.area_generation_cost = Number(form.area_generation_cost);
      body.character_create_portrait_cost = Number(form.character_create_portrait_cost);
      body.pixels_per_usd = Number(form.pixels_per_usd);
      const { data } = await axios.patch(`${API_BASE}/comfyui/settings?persist=${persist}`, body);
      setStatus(data);
      setSaveMsg(persist ? "Saved to config/comfyui.toml." : "Applied (in-memory only).");
    } catch (e) {
      setSaveMsg(e.response?.data?.detail || e.message || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const inp = {
    width: "100%", padding: "8px 10px",
    background: COLORS.bgInput, border: `1px solid ${COLORS.border}`,
    borderRadius: 6, color: COLORS.text, fontSize: 12,
    fontFamily: "'DM Sans', sans-serif",
  };
  const F = (label, key, type = "text", opts = {}) => (
    <div key={key}>
      <label style={{ fontSize: 11, color: COLORS.textMuted, display: "block", marginBottom: 4 }}>{label}</label>
      <input
        type={type}
        value={form[key] ?? ""}
        onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))}
        style={inp}
        {...opts}
      />
    </div>
  );

  const StatusBadge = ({ ok, yes, no }) => (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "2px 10px", borderRadius: 999, fontSize: 11, fontWeight: 700,
      background: ok ? `${COLORS.success}22` : `${COLORS.danger}22`,
      color: ok ? COLORS.success : COLORS.danger,
      border: `1px solid ${ok ? COLORS.success : COLORS.danger}44`,
    }}>
      <StatusDot color={ok ? COLORS.success : COLORS.danger} pulse={ok} />
      {ok ? yes : no}
    </span>
  );

  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif", display: "flex", alignItems: "center", gap: 8 }}>
          <Icons.Wand /> ComfyUI Workflows
        </h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <StatusBadge ok={status?.enabled} yes="Enabled" no="Disabled" />
          <StatusBadge ok={status?.comfy_reachable} yes="Reachable" no="Offline" />
        </div>
      </div>

      <TabBar tabs={COMFY_TABS} active={tab} onChange={setTab} />

      {tab === "status" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>Connection</div>
            <div style={{ fontSize: 12, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.8 }}>
              <div><span style={{ color: COLORS.textDim }}>Base URL</span> {status?.base_url || "—"}</div>
              <div><span style={{ color: COLORS.textDim }}>Enabled</span> {status?.enabled ? "Yes" : "No"}</div>
              <div><span style={{ color: COLORS.textDim }}>Reachable</span> {status?.comfy_reachable ? "Yes" : "No"}</div>
              {status?.comfy_ping_error && <div style={{ color: COLORS.danger, fontSize: 11 }}>{status.comfy_ping_error}</div>}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={syncStatus} disabled={busy}>Refresh</ActionButton>
              <ActionButton small variant="primary" icon={<Icons.Terminal />} onClick={testConnection} disabled={busy}>Test connection</ActionButton>
            </div>
            {testResult && (
              <div style={{
                display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 6,
                background: testResult.ok ? COLORS.successBg : COLORS.dangerBg,
                border: `1px solid ${testResult.ok ? COLORS.success : COLORS.danger}22`,
                fontSize: 11.5, fontFamily: "'JetBrains Mono', monospace",
                color: testResult.ok ? COLORS.success : COLORS.danger,
              }}>
                <StatusDot color={testResult.ok ? COLORS.success : COLORS.danger} pulse={testResult.ok} />
                {testResult.msg}
              </div>
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>Workflows</div>
            <div style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.8 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: COLORS.textDim }}>Portrait</span>
                <StatusBadge ok={status?.workflow_present} yes="file found" no="missing" />
              </div>
              <div style={{ color: COLORS.textMuted, fontSize: 11, marginBottom: 6, wordBreak: "break-all" }}>{status?.workflow_path || "—"}</div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: COLORS.textDim }}>Scene / Area</span>
                <StatusBadge ok={status?.area_workflow_present} yes="file found" no="missing" />
              </div>
              <div style={{ color: COLORS.textMuted, fontSize: 11, wordBreak: "break-all" }}>{status?.area_workflow_path || "—"}</div>
            </div>
            {status?.suggest_checkpoint_name_in_toml && (
              <div style={{ fontSize: 11, color: COLORS.warning, padding: "6px 10px", background: `${COLORS.warning}11`, border: `1px solid ${COLORS.warning}44`, borderRadius: 6 }}>
                Area workflow uses a CheckpointLoaderSimple node but <strong>checkpoint_name</strong> is not set — set it in the Workflows tab so the server can inject it automatically.
              </div>
            )}
            <div style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.8 }}>
              <div><span style={{ color: COLORS.textDim }}>Economy enabled</span> {status?.economy_enabled ? "Yes" : "No"}</div>
              <div><span style={{ color: COLORS.textDim }}>Currency</span> {status?.currency_display_name || "—"}</div>
              <div><span style={{ color: COLORS.textDim }}>Portrait cost</span> {status?.portrait_generation_cost ?? "—"}</div>
              <div><span style={{ color: COLORS.textDim }}>Scene cost</span> {status?.area_generation_cost ?? "—"}</div>
            </div>
          </div>
        </div>
      )}

      {tab === "portrait" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
            Used for <strong style={{ color: COLORS.text }}>character portraits</strong> — triggered at character creation and from the player client. The JSON must be a ComfyUI API-format workflow.
          </div>
          {F("Workflow JSON path", "workflow_path")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {F("Positive prompt node ID", "positive_prompt_node_id")}
            {F("Output (SaveImage) node ID", "output_node_id")}
          </div>
          {F("Base URL", "base_url")}
          {F("Checkpoint name (optional — injected into CheckpointLoaderSimple nodes)", "checkpoint_name")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {F("Timeout (s)", "timeout_seconds", "number", { min: 10, step: 10 })}
            {F("Poll interval (s)", "poll_interval_seconds", "number", { min: 0.1, step: 0.25 })}
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: COLORS.textMuted, cursor: "pointer" }}>
            <input type="checkbox" checked={form.enabled} onChange={(e) => setForm((p) => ({ ...p, enabled: e.target.checked }))} />
            ComfyUI integration enabled
          </label>
        </div>
      )}

      {tab === "scene" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
            Used for <strong style={{ color: COLORS.text }}>room / area scene images</strong> — triggered by AI Forge and from the player client. Falls back to the portrait workflow JSON if this path is not set.
          </div>
          {F("Area workflow JSON path", "area_workflow_path")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {F("Positive prompt node ID", "area_positive_prompt_node_id")}
            {F("Output (SaveImage) node ID", "area_output_node_id")}
          </div>
          {F("Base URL", "base_url")}
          {F("Checkpoint name (optional)", "checkpoint_name")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {F("Timeout (s)", "timeout_seconds", "number", { min: 10, step: 10 })}
            {F("Poll interval (s)", "poll_interval_seconds", "number", { min: 0.1, step: 0.25 })}
          </div>
        </div>
      )}

      {tab === "economy" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
            Controls the art-credit economy. The currency (e.g. <em>pixels</em>) is separate from the in-world Digi balance — it&apos;s spent only on ComfyUI generation.
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: COLORS.textMuted, cursor: "pointer" }}>
            <input type="checkbox" checked={form.economy_enabled} onChange={(e) => setForm((p) => ({ ...p, economy_enabled: e.target.checked }))} />
            Economy enabled (deduct credits on generation)
          </label>
          {F("Currency display name", "currency_display_name")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
            {F("Portrait cost", "portrait_generation_cost", "number", { min: 0 })}
            {F("Scene cost", "area_generation_cost", "number", { min: 0 })}
            {F("Chargen portrait cost", "character_create_portrait_cost", "number", { min: 0 })}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {F("Starting credits (new accounts)", "starting_echo_credits", "number", { min: 0 })}
            {F("Credits per USD (reference only)", "pixels_per_usd", "number", { min: 1 })}
          </div>
        </div>
      )}

      {tab !== "status" && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, paddingTop: 6, borderTop: `1px solid ${COLORS.border}44` }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: COLORS.textMuted, cursor: "pointer", flexShrink: 0 }}>
            <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
            Save to config/comfyui.toml
          </label>
          <ActionButton variant="primary" icon={<Icons.Save />} onClick={saveSettings} disabled={busy}>{busy ? "Saving…" : "Apply settings"}</ActionButton>
          {saveMsg && <span style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>{saveMsg}</span>}
        </div>
      )}
    </div>
  );
};


// ═══════════════════════════════════════════════════════════════
// EXISTING PAGE COMPONENTS (condensed from v1)
// ═══════════════════════════════════════════════════════════════

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

const WorldPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [filter, setFilter] = useState("all");
  const { rows: zones, error: zonesError } = usePolledList(`${API_BASE}/content/zones`, 10000);
  const typeColors = { tutorial: COLORS.success, exploration: COLORS.info, dungeon: COLORS.accent, boss: COLORS.danger, safe: COLORS.warning };
  const filtered = zones.filter((z) => filter === "all" || z.status === filter);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>World & Zones</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <TabBar tabs={[{ id: "all", label: "All" }, { id: "active", label: "Active" }, { id: "building", label: "Building" }]} active={filter} onChange={setFilter} />
          <ActionButton variant="primary" icon={<Icons.Plus />} onClick={() => window.alert("Create a folder under content/world/zones/<zone_id>/rooms/ or use AI Forge to inject rooms.")}>New Zone</ActionButton>
        </div>
      </div>
      <FetchErrorBanner error={zonesError} label="zones" />
      {filtered.length === 0 && !zonesError && <div style={{ color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>No zones found under content/world/zones.</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
        {filtered.map((zone) => (
          <div key={zone.id} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12, cursor: "pointer" }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = COLORS.borderActive; }} onMouseLeave={(e) => { e.currentTarget.style.borderColor = COLORS.border; }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{zone.name}</div>
                <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 2 }}>{zone.id} · depth {zone.depth}</div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <Badge color={typeColors[zone.type] || COLORS.textMuted}>{zone.type}</Badge>
                <Badge color={zone.status === "active" ? COLORS.success : zone.status === "building" ? COLORS.warning : COLORS.danger}>{zone.status}</Badge>
              </div>
            </div>
            <div style={{ display: "flex", gap: 16 }}>
              {[{ label: "Rooms", value: zone.rooms }, { label: "Entities", value: zone.entities }, { label: "Players", value: zone.players }].map((s) => (
                <div key={s.label}><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{s.value}</div><div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{s.label}</div></div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
              <ActionButton small variant="ghost" icon={<Icons.Eye />} onClick={() => window.alert(`Zone path: content/world/zones/${zone.id}/`)}>View</ActionButton>
              <ActionButton
                small
                variant="primary"
                icon={<Icons.Map />}
                onClick={(e) => {
                  e.stopPropagation();
                  window.dispatchEvent(
                    new CustomEvent("fs-admin-nav", {
                      detail: { page: "builder", zoneId: zone.id, zoneLabel: zone.name },
                    })
                  );
                }}
              >
                World Builder
              </ActionButton>
              <ActionButton small variant="forge" icon={<Icons.Sparkles />} onClick={() => window.alert("Open AI Forge → Room and set Target Zone to match this zone id.")}>AI Expand</ActionButton>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const EntitiesPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [search, setSearch] = useState("");
  const { rows, error: rowsError } = usePolledList(`${API_BASE}/content/entities/spawns`, 12000);
  const typeColors = { Hunter: COLORS.danger, Guide: COLORS.success, Watcher: COLORS.info, Boss: COLORS.warning, Vendor: COLORS.accent, spawn: COLORS.accent };
  const filtered = rows.filter((e) => String(e.name).toLowerCase().includes(search.toLowerCase()));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Entity Management</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <SearchBar placeholder="Search spawn templates..." value={search} onChange={setSearch} />
          <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={() => window.alert("Use AI Forge → Entity / NPC to author YAML, then add entity_spawns to room files.")}>AI Generate</ActionButton>
        </div>
      </div>
      <p style={{ margin: 0, fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>Rows aggregate <code style={{ color: COLORS.textDim }}>entity_spawns</code> entries from all room YAML files.</p>
      <FetchErrorBanner error={rowsError} label="entity spawns" />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable columns={[
          { label: "Template", render: (row) => <span style={{ fontWeight: 600 }}>{row.name}</span> },
          { label: "Kind", render: (row) => <Badge color={typeColors[row.type] || COLORS.textMuted}>{row.type}</Badge> },
          { label: "Zone ref", key: "zone" }, { label: "Level", key: "level", mono: true },
          { label: "Behavior", render: (row) => <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: COLORS.textMuted }}>{row.behavior}</span> },
          { label: "Spawn refs", key: "count", mono: true },
          { label: "Status", render: (row) => <Badge color={row.status === "active" ? COLORS.success : COLORS.textDim}>{row.status}</Badge> },
          { label: "", render: () => <div style={{ display: "flex", gap: 4 }}><ActionButton small variant="ghost"><Icons.Eye /></ActionButton></div> },
        ]} rows={filtered} />
      </div>
    </div>
  );
};

const ItemsPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const rarityColors = { common: COLORS.textMuted, uncommon: COLORS.success, rare: COLORS.info, epic: COLORS.accent, legendary: COLORS.warning };
  const { rows: items, error: itemsError } = usePolledList(`${API_BASE}/content/items`, 15000);
  const display = items;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Item Catalog</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <ActionButton variant="primary" icon={<Icons.Plus />} onClick={() => window.alert("Add YAML files under content/world/items/ (see repo README).")}>New Item</ActionButton>
          <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={() => window.alert("Use AI Forge → Item, then save YAML into content/world/items/.")}>AI Generate</ActionButton>
        </div>
      </div>
      <FetchErrorBanner error={itemsError} label="items" />
      {!items.length && !itemsError && <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>No items found. Add YAML under <code style={{ color: COLORS.textDim }}>content/world/items/</code> or generate with AI Forge.</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 }}>
        {display.map((item) => (
          <div key={item.id} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 10, borderLeft: `3px solid ${rarityColors[item.rarity] || COLORS.border}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div><div style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{item.name}</div><div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 2 }}>{item.id}</div></div>
              {item.rarity && <Badge color={rarityColors[item.rarity]}>{item.rarity}</Badge>}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              {item.type && <Pill label="Type" value={item.type} />}
              {item.value > 0 && <Pill label="Value" value={`${item.value}g`} color={COLORS.warning} />}
            </div>
            {item.zones && <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>Zones: {Array.isArray(item.zones) ? item.zones.join(", ") : item.zones}</div>}
          </div>
        ))}
      </div>
    </div>
  );
};

const GlyphsPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const catColors = { Combat: COLORS.danger, Defense: COLORS.info, Utility: COLORS.success };
  const { rows: glyphs, error: glyphsError } = usePolledList(`${API_BASE}/content/glyphs`, 15000);
  const rows = glyphs.map((g) => ({
    ...g,
    tier: g.tier ?? "—",
    energyCost: g.energyCost ?? "—",
    bodySlot: g.bodySlot ?? g.body_slot ?? "—",
    effect: g.effect ?? "",
    category: g.category || "Utility",
    name: g.name || g.id,
  }));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Glyph Registry</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <ActionButton variant="primary" icon={<Icons.Plus />} onClick={() => window.alert("Add YAML under content/world/glyphs/.")}>Design Glyph</ActionButton>
          <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={() => window.alert("Use AI Forge → Glyph / Ability.")}>AI Forge Glyph</ActionButton>
        </div>
      </div>
      <FetchErrorBanner error={glyphsError} label="glyphs" />
      {!glyphs.length && !glyphsError && <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>No glyphs found. Add YAML under <code style={{ color: COLORS.textDim }}>content/world/glyphs/</code> or use AI Forge.</div>}
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable columns={[
          { label: "Glyph", render: (row) => (<div style={{ display: "flex", alignItems: "center", gap: 10 }}><div style={{ width: 32, height: 32, borderRadius: 6, background: `${(catColors[row.category] || COLORS.accent)}15`, border: `1px solid ${(catColors[row.category] || COLORS.accent)}30`, display: "flex", alignItems: "center", justifyContent: "center", color: (catColors[row.category] || COLORS.accent), fontSize: 14 }}><Icons.Glyphs /></div><div><div style={{ fontWeight: 600, fontSize: 13 }}>{row.name}</div><div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>{row.id}</div></div></div>) },
          { label: "Category", render: (row) => <Badge color={catColors[row.category] || COLORS.textMuted}>{row.category}</Badge> },
          { label: "Tier", key: "tier", mono: true },
          { label: "Energy", render: (row) => <span style={{ color: COLORS.cyan, fontFamily: "'JetBrains Mono', monospace" }}>{row.energyCost}</span> },
          { label: "Body Slot", key: "bodySlot" },
          { label: "Effect", render: (row) => <span style={{ fontSize: 12, color: COLORS.textMuted }}>{row.effect}</span> },
          { label: "", render: () => <div style={{ display: "flex", gap: 4 }}><ActionButton small variant="ghost"><Icons.Eye /></ActionButton></div> },
        ]} rows={rows} />
      </div>
    </div>
  );
};

const LocationsPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [selectedZone, setSelectedZone] = useState("");
  const { rows: zones, error: zonesError } = usePolledList(`${API_BASE}/content/zones`, 12000);
  const { rows: roomRows, error: roomsError } = usePolledList(
    selectedZone ? `${API_BASE}/content/zones/${selectedZone}/rooms` : null,
    10000,
    { enabled: !!selectedZone }
  );
  useEffect(() => {
    if (zones.length && !selectedZone) setSelectedZone(zones[0].id);
  }, [zones, selectedZone]);

  const zone = zones.find((z) => z.id === selectedZone);

  const reloadCaches = async () => {
    try {
      await axios.post(`${API_BASE}/content/cache/reload`);
      window.alert("Content cache and prompts reloaded.");
    } catch (e) {
      window.alert(e.message || "Reload failed");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Location Builder</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <select value={selectedZone} onChange={(e) => setSelectedZone(e.target.value)} style={{ padding: "8px 12px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 8, color: COLORS.text, fontSize: 13, fontFamily: "'DM Sans', sans-serif" }}>
            {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
          </select>
          <ActionButton variant="primary" icon={<Icons.Plus />} onClick={() => window.alert("Use AI Forge → Room, then Accept & Deploy, or add a .yaml under this zone's rooms/ folder.")}>Add Room</ActionButton>
          <ActionButton
            variant="primary"
            icon={<Icons.Map />}
            onClick={() => {
              window.dispatchEvent(
                new CustomEvent("fs-admin-nav", {
                  detail: { page: "builder", zoneId: selectedZone, zoneLabel: zone?.name },
                })
              );
            }}
          >
            Open in World Builder
          </ActionButton>
          <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={() => window.alert("Open AI Forge → Room.")}>AI Generate Rooms</ActionButton>
        </div>
      </div>
      <FetchErrorBanner error={zonesError} label="zones" />
      <FetchErrorBanner error={roomsError} label="rooms" />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{zone?.name || "—"}</div>
          <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 2 }}>{zone?.id} · {zone?.rooms ?? roomRows.length} rooms · depth {zone?.depth ?? "—"}</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <ActionButton small variant="ghost" icon={<Icons.Zap />} onClick={reloadCaches}>Hot Reload</ActionButton>
          <ActionButton small variant="forge" icon={<Icons.Wand />} onClick={() => window.alert("Use Forge per-room for now.")}>AI Describe All</ActionButton>
        </div>
      </div>
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable columns={[
          { label: "Room", render: (row) => (<div><div style={{ fontWeight: 600, fontSize: 13 }}>{row.name}</div><div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{row.id}</div></div>) },
          { label: "Type", render: (row) => <Badge>{row.type}</Badge> },
          { label: "Exits", render: (row) => (<div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>{(row.exits || []).map((e) => (<span key={e} style={{ width: 22, height: 22, borderRadius: 4, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 600, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>{e}</span>))}</div>) },
          { label: "Entities", key: "entities", mono: true },
          { label: "Hazards", render: (row) => <span style={{ color: row.hazards > 0 ? COLORS.danger : COLORS.textDim }}>{row.hazards}</span> },
          { label: "", render: (row) => (<div style={{ display: "flex", gap: 4 }}><ActionButton small variant="ghost" icon={<Icons.Eye />} onClick={async () => {
            try {
              const { data } = await axios.get(`${API_BASE}/content/room/${selectedZone}/${row.name}/yaml`);
              window.alert(data.yaml.slice(0, 1200) + (data.yaml.length > 1200 ? "\n…" : ""));
            } catch {
              window.alert("Could not load YAML");
            }
          }}>View</ActionButton></div>) },
        ]} rows={roomRows} />
      </div>
    </div>
  );
};

const ServerPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [info, setInfo] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/server/info`);
        setInfo(data);
      } catch {
        setInfo(null);
      }
    };
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, []);

  const metrics = info ? [
    { label: "Tick rate", value: `${info.tick_rate_hz?.toFixed(1) ?? "—"} Hz`, color: COLORS.success, pct: Math.min(100, (info.tick_rate_hz || 0) * 5) },
    { label: "Nexus port", value: String(info.nexus_port ?? "—"), color: COLORS.info, pct: 40 },
    { label: "Redis", value: info.redis_ok ? "OK" : "down", color: info.redis_ok ? COLORS.accent : COLORS.danger, pct: info.redis_ok ? 70 : 10 },
    { label: "PostgreSQL", value: info.postgres_ok ? "OK" : "down", color: info.postgres_ok ? COLORS.warning : COLORS.danger, pct: info.postgres_ok ? 50 : 10 },
    { label: "LLM backend", value: info.llm_backend ?? "—", color: COLORS.cyan, pct: 55 },
    { label: "Game sessions", value: String(info.sessions ?? 0), color: COLORS.success, pct: Math.min(100, (info.sessions || 0) * 10) },
  ] : [
    { label: "Nexus", value: "offline", color: COLORS.danger, pct: 5 },
  ];

  const configRows = info ? [
    { key: "tick_interval_s", value: String(info.tick_interval_s) },
    { key: "nexus_port", value: String(info.nexus_port) },
    { key: "player_transport", value: String(info.player_transport ?? "websocket") },
    { key: "max_connections", value: String(info.max_connections) },
    { key: "dev_mode", value: String(info.dev_mode) },
    { key: "llm_backend", value: String(info.llm_backend) },
    { key: "llm_url", value: String(info.llm_url || "—") },
    { key: "llm_model", value: String(info.llm_model || "—") },
    { key: "llm_detected_model", value: String(info.llm_detected_model || "—") },
    { key: "llm_models_align", value: info.llm_models_align == null ? "—" : info.llm_models_align ? "yes" : "no" },
    { key: "llm_chat_model_auto", value: info.llm_chat_model_auto == null ? "—" : info.llm_chat_model_auto ? "yes" : "no" },
    { key: "llm_connected", value: info.llm_connected ? "yes" : "no" },
    { key: "llm_list_ms", value: info.llm_latency_ms != null ? String(info.llm_latency_ms) : "—" },
    { key: "tick_count", value: String(info.tick_count) },
  ] : [{ key: "status", value: "Could not load /server/info" }];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Server & Performance</h2>
        <div style={{ display: "flex", gap: 8 }}><ActionButton small variant="ghost" icon={<Icons.Alert />} onClick={() => window.alert("Process restart is not exposed via API yet.")}>Restart</ActionButton></div>
      </div>
      {info?.host && (
        <HostMachinePanel
          host={info.host}
          llmDetected={info.llm_detected_model}
          llmConfigured={info.llm_model}
          llmConnected={info.llm_connected}
          llmBackend={info.llm_backend}
          llmModelsAlign={info.llm_models_align}
        />
      )}
      <LmStudioPanel />
      <ComfyUIPanel />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14 }}>
        {metrics.map((m) => (
          <div key={m.label} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>{m.label}</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace" }}>{m.value}</span>
            </div>
            <div style={{ width: "100%", height: 6, borderRadius: 3, background: COLORS.bgInput }}><div style={{ width: `${m.pct}%`, height: "100%", borderRadius: 3, background: m.color }} /></div>
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Server Config</h3>
          {configRows.map((c) => (
            <div key={c.key} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${COLORS.border}22`, gap: 8 }}>
              <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", wordBreak: "break-all" }}>{c.key}</span>
              <span style={{ fontSize: 12, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, textAlign: "right" }}>{c.value}</span>
            </div>
          ))}
        </div>
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Recent Events</h3>
          <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
            No persisted event stream on the server yet. Use <strong style={{ color: COLORS.text }}>Dashboard → Live Activity</strong> for the WebSocket log feed while the Nexus is running.
          </div>
        </div>
      </div>
    </div>
  );
};

const ContentPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [overview, setOverview] = useState(null);
  const [reloadMsg, setReloadMsg] = useState("");
  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/content/overview`);
        setOverview(data);
      } catch {
        setOverview(null);
      }
    };
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, []);

  const counts = overview || { room_count: 0, entity_templates: 0, item_count: 0, glyph_count: 0, zone_count: 0 };
  const templates = [
    { name: "Room", desc: "Create rooms with exits, entities, and hazards", icon: <Icons.Locations />, count: counts.room_count },
    { name: "Entity / NPC", desc: "Define behavior, dialogue, and combat", icon: <Icons.Entities />, count: counts.entity_templates },
    { name: "Item", desc: "Equipment, consumables, keys, and lore", icon: <Icons.Items />, count: counts.item_count },
    { name: "Glyph", desc: "Reality-manipulation abilities", icon: <Icons.Glyphs />, count: counts.glyph_count },
    { name: "Quest", desc: "Objective chains with branching", icon: <Icons.Content />, count: "Forge" },
    { name: "Dialogue Tree", desc: "NPC conversation flows", icon: <Icons.Activity />, count: "Forge" },
  ];

  const doReload = async () => {
    setReloadMsg("");
    try {
      await axios.post(`${API_BASE}/content/cache/reload`);
      setReloadMsg("Caches cleared.");
    } catch (e) {
      setReloadMsg(e.message || "Failed");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Content Tools</h2>
      {reloadMsg && <div style={{ fontSize: 12, color: COLORS.textMuted }}>{reloadMsg}</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 }}>
        {templates.map((t) => (
          <div key={t.name} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, cursor: "pointer", display: "flex", gap: 14, alignItems: "flex-start" }}
            onClick={() => window.alert("Use the matching sidebar section or AI Forge for this content type.")}>
            <div style={{ width: 40, height: 40, borderRadius: 8, background: COLORS.accentGlow, border: `1px solid ${COLORS.accent}30`, display: "flex", alignItems: "center", justifyContent: "center", color: COLORS.accent, flexShrink: 0 }}>{t.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>{t.name}</span><Badge>{t.count}</Badge>
              </div>
              <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4, lineHeight: 1.4, fontFamily: "'DM Sans', sans-serif" }}>{t.desc}</div>
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14 }}>
        {[
          { name: "YAML Editor", desc: "Edit files under content/world/", color: COLORS.success, action: () => window.alert("Use your IDE or View on Locations for raw YAML.") },
          { name: "Hot-Reload", desc: "Clear in-memory content + prompt caches", color: COLORS.warning, action: doReload },
          { name: "Validation", desc: "Room YAML is validated when loaded by the engine", color: COLORS.info, action: () => window.alert("Invalid YAML fails at load time in server logs.") },
          { name: "Export / Import", desc: "Backup and restore", color: COLORS.textMuted, action: () => window.alert("Use git or copy the content/ directory.") },
        ].map((tool) => (
          <div key={tool.name} role="button" tabIndex={0} onClick={tool.action} onKeyDown={(e) => e.key === "Enter" && tool.action()}
            style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16, cursor: "pointer", borderTop: `2px solid ${tool.color}` }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>{tool.name}</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4, fontFamily: "'DM Sans', sans-serif" }}>{tool.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
};


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
            Sessions, server-wide broadcast, content cache reload, and Redis world snapshot. These endpoints are not authenticated — use only on trusted networks (see README).
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
                <span>Rooms w/ players: <strong style={{ color: COLORS.text }}>{worldLive.rooms_with_players ?? "—"}</strong></span>
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


// ═══════════════════════════════════════════════════════════════
// ADMIN AUTH, PRESENCE & TEAM (staff / head admin)
// ═══════════════════════════════════════════════════════════════

const LoginScreen = ({ onLoggedIn }) => {
  const { colors: COLORS } = useAdminTheme();
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
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
            "). Start Docker Desktop, then from the repo root: docker compose up -d redis postgres — then: python -m fablestar (port 8001 must match this UI)."
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
        <h1 style={{ margin: "0 0 8px", fontSize: 20, color: COLORS.accent, fontFamily: "'Space Grotesk', sans-serif" }}>Fablestar Admin</h1>
        <p style={{ margin: "0 0 20px", fontSize: 13, color: COLORS.textMuted }}>Sign in with a staff account. Ask a head admin for credentials. Username and password are case-sensitive.</p>
        <label style={{ display: "block", fontSize: 11, color: COLORS.textMuted, marginBottom: 6 }}>Username</label>
        <input autoComplete="username" value={user} onChange={(e) => setUser(e.target.value)} style={{ ...inp, marginBottom: 14 }} />
        <label style={{ display: "block", fontSize: 11, color: COLORS.textMuted, marginBottom: 6 }}>Password</label>
        <input type="password" autoComplete="current-password" value={pass} onChange={(e) => setPass(e.target.value)} style={{ ...inp, marginBottom: 16 }} />
        {err && <div style={{ color: COLORS.danger, fontSize: 12, marginBottom: 12 }}>{typeof err === "string" ? err : JSON.stringify(err)}</div>}
        <button type="submit" disabled={busy} style={{
          width: "100%", padding: "12px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, cursor: busy ? "wait" : "pointer",
        }}>{busy ? "Signing in…" : "Sign in"}</button>
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

const StaffTeamPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [rows, setRows] = useState([]);
  const [loadErr, setLoadErr] = useState("");
  const [form, setForm] = useState({
    username: "", password: "", display_name: "", role: "gm", tools: ["dashboard", "players"], zones: "*",
  });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoadErr("");
    try {
      const { data } = await axios.get(`${API_BASE}/admin/staff`);
      setRows(data);
    } catch (e) {
      setLoadErr(e.response?.data?.detail || e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleTool = (id) => {
    setForm((f) => {
      const s = new Set(f.tools);
      if (s.has(id)) s.delete(id); else s.add(id);
      return { ...f, tools: [...s] };
    });
  };

  const createStaff = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const zonesRaw = (form.zones || "").trim();
      const zones = zonesRaw === "*" || zonesRaw === "" ? ["*"] : zonesRaw.split(",").map((z) => z.trim()).filter(Boolean);
      await axios.post(`${API_BASE}/admin/staff`, {
        username: form.username.trim(),
        password: form.password,
        display_name: form.display_name.trim() || form.username.trim(),
        role: form.role,
        permissions: { tools: form.tools, zones },
      });
      setForm({ username: "", password: "", display_name: "", role: "gm", tools: ["dashboard", "players"], zones: "*" });
      await load();
    } catch (ex) {
      window.alert(ex.response?.data?.detail || ex.message);
    } finally {
      setBusy(false);
    }
  };

  const patchStaff = async (id, patch) => {
    try {
      await axios.patch(`${API_BASE}/admin/staff/${id}`, patch);
      await load();
    } catch (ex) {
      window.alert(ex.response?.data?.detail || ex.message);
    }
  };

  return (
    <div style={{ maxWidth: 960 }}>
      <h2 style={{ margin: "0 0 8px", fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Team &amp; access</h2>
      <p style={{ margin: "0 0 16px", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
        Head admins can add staff, assign roles (admin / GM), and restrict <strong>tools</strong> (sidebar areas) and <strong>zones</strong> (world regions for room edits / forge inject / live spawns).
        Use zones <code style={{ color: COLORS.textDim }}>*</code> for all zones, or comma-separated ids e.g. <code style={{ color: COLORS.textDim }}>test_zone</code>.
        {" "}Staff accounts are for this admin console only. To give a <strong>play</strong> login the in-game pink <strong>GM</strong> crown, use <strong>Players → Game accounts</strong> and enable <em>Game Master play account</em> on that row.
      </p>
      {loadErr && <div style={{ color: COLORS.danger, marginBottom: 12 }}>{loadErr}</div>}

      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, marginBottom: 20 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Add staff</h3>
        <form onSubmit={createStaff} style={{ display: "grid", gap: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
            <input placeholder="username" value={form.username} onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }} />
            <input type="password" placeholder="password" value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }} />
            <input placeholder="display name" value={form.display_name} onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }} />
            <select value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }}>
              <option value="gm">GM</option>
              <option value="admin">Admin</option>
              <option value="head_admin">Head admin</option>
            </select>
          </div>
          <input placeholder="Zones (* or zone_id, zone_id2)" value={form.zones} onChange={(e) => setForm((f) => ({ ...f, zones: e.target.value }))} style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {ALL_ADMIN_TOOLS.map((tid) => (
              <label key={tid} style={{ fontSize: 11, color: COLORS.textMuted, display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
                <input type="checkbox" checked={form.tools.includes(tid)} onChange={() => toggleTool(tid)} />
                {tid}
              </label>
            ))}
          </div>
          <button type="submit" disabled={busy} style={{ alignSelf: "start", padding: "8px 16px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}>Create</button>
        </form>
      </div>

      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable
          columns={[
            { label: "User", render: (r) => <span style={{ fontWeight: 600 }}>{r.display_name}</span> },
            { label: "Login", key: "username", mono: true },
            { label: "Role", key: "role", mono: true },
            { label: "Active", render: (r) => <Badge color={r.is_active ? COLORS.success : COLORS.danger}>{r.is_active ? "yes" : "no"}</Badge> },
            { label: "Tools", render: (r) => <span style={{ fontSize: 10, color: COLORS.textDim }}>{(r.permissions?.tools || []).join(", ") || "—"}</span> },
            { label: "Zones", render: (r) => <span style={{ fontSize: 10, color: COLORS.textDim }}>{(r.permissions?.zones || []).join(", ") || "*"}</span> },
            { label: "", render: (r) => (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <ActionButton small variant="ghost" onClick={() => patchStaff(r.id, { is_active: !r.is_active })}>{r.is_active ? "Deactivate" : "Activate"}</ActionButton>
              </div>
            ) },
          ]}
          rows={rows}
        />
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════
// NAVIGATION & MAIN APP
// ═══════════════════════════════════════════════════════════════

function SettingsPlaceholderPage() {
  const { colors: COLORS, toggleMode, mode } = useAdminTheme();
  return (
    <div style={{ fontFamily: "'DM Sans', sans-serif", padding: 40, maxWidth: 560 }}>
      <h2 style={{ margin: "0 0 12px", fontSize: 18, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Settings</h2>
      <p style={{ margin: "0 0 20px", fontSize: 14, color: COLORS.textMuted, lineHeight: 1.55 }}>
        Configure server, LLM, and permissions from other sidebar areas. Theme preference is stored in this browser.
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: COLORS.text }}>Appearance</span>
        <button
          type="button"
          onClick={toggleMode}
          style={{
            padding: "8px 16px",
            borderRadius: 8,
            border: `1px solid ${COLORS.border}`,
            background: COLORS.bgCard,
            color: COLORS.text,
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: "'DM Sans', sans-serif",
          }}
        >
          {mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        </button>
      </div>
    </div>
  );
}

const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: <Icons.Dashboard /> },
  { id: "forge", label: "AI Forge", icon: <Icons.Forge />, highlight: true },
  { id: "operations", label: "Operations", icon: <Icons.Alert /> },
  { id: "players", label: "Players & accounts", icon: <Icons.Players /> },
  { id: "world", label: "World & Zones", icon: <Icons.World /> },
  { id: "entities", label: "Entities", icon: <Icons.Entities /> },
  { id: "items", label: "Items", icon: <Icons.Items /> },
  { id: "glyphs", label: "Glyphs", icon: <Icons.Glyphs /> },
  { id: "skills", label: "Skills catalog", icon: <Icons.Skills /> },
  { id: "locations", label: "Locations", icon: <Icons.Locations /> },
  { id: "builder", label: "World Builder", icon: <Icons.Map /> },
  { id: "server", label: "Server", icon: <Icons.Server /> },
  { id: "content", label: "Content Tools", icon: <Icons.Content /> },
  { id: "settings", label: "Settings", icon: <Icons.Settings /> },
  { id: "team", label: "Team & access", icon: <Icons.Players />, headOnly: true },
];

const PAGES = {
  dashboard: DashboardPage,
  forge: AiForgePage,
  operations: OperationsPage,
  players: PlayersPage,
  world: WorldPage,
  entities: EntitiesPage,
  items: ItemsPage,
  glyphs: GlyphsPage,
  skills: ProficienciesPage,
  locations: LocationsPage,
  builder: WorldBuilderPage,
  server: ServerPage,
  content: ContentPage,
  settings: SettingsPlaceholderPage,
  team: StaffTeamPage,
};

export default function App() {
  const { colors: COLORS, toggleMode, mode } = useAdminTheme();
  const [activePage, setActivePage] = useState("dashboard");
  const [sidebarHovered, setSidebarHovered] = useState(null);
  const [serverInfo, setServerInfo] = useState(null);
  const [staffProfile, setStaffProfile] = useState(null);
  const [booting, setBooting] = useState(true);
  const [presenceOnline, setPresenceOnline] = useState([]);

  useEffect(() => {
    const onAuthLost = () => {
      localStorage.removeItem(LS_ADMIN_TOKEN);
      window.location.reload();
    };
    window.addEventListener("fablestar-admin-unauthorized", onAuthLost);
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
            window.dispatchEvent(new Event("fablestar-admin-unauthorized"));
          }
        }
        return Promise.reject(err);
      }
    );
    return () => {
      window.removeEventListener("fablestar-admin-unauthorized", onAuthLost);
      axios.interceptors.request.eject(reqId);
      axios.interceptors.response.eject(resId);
    };
  }, []);

  const refreshMe = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/admin/me`);
      setStaffProfile(data);
      return data;
    } catch {
      setStaffProfile(null);
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
      if (d.page !== "builder") return;
      if (d.zoneId) {
        sessionStorage.setItem(
          "fs_builder_initial",
          JSON.stringify({ scale: "zone", id: d.zoneId, label: d.zoneLabel || d.zoneId })
        );
      } else if (d.shipId) {
        sessionStorage.setItem(
          "fs_builder_initial",
          JSON.stringify({ scale: "ship", id: d.shipId, label: d.shipLabel || d.shipId })
        );
      }
      setActivePage("builder");
    };
    window.addEventListener("fs-admin-nav", onNav);
    return () => window.removeEventListener("fs-admin-nav", onNav);
  }, []);

  useEffect(() => {
    if (booting || !serverInfo) return;
    try {
      const u = new URL(window.location.href);
      const zone = u.searchParams.get("zone");
      const ship = u.searchParams.get("ship");
      if (u.searchParams.get("page") === "builder" || u.searchParams.get("builder") === "1") {
        if (zone) {
          sessionStorage.setItem("fs_builder_initial", JSON.stringify({ scale: "zone", id: zone, label: zone }));
        } else if (ship) {
          sessionStorage.setItem("fs_builder_initial", JSON.stringify({ scale: "ship", id: ship, label: ship }));
        }
        setActivePage("builder");
        u.searchParams.delete("page");
        u.searchParams.delete("zone");
        u.searchParams.delete("ship");
        u.searchParams.delete("builder");
        const qs = u.searchParams.toString();
        window.history.replaceState({}, "", `${u.pathname}${qs ? `?${qs}` : ""}${u.hash}`);
      }
    } catch { /* ignore */ }
  }, [booting, serverInfo]);

  const allowedSet = useMemo(() => {
    if (staffProfile?.tools_effective == null) return new Set(ALL_ADMIN_TOOLS);
    return new Set(staffProfile.tools_effective);
  }, [staffProfile]);

  const navFiltered = useMemo(() => NAV_ITEMS.filter((item) => {
    if (item.headOnly) return staffProfile?.role === "head_admin";
    if (item.id === "skills") return allowedSet.has("skills") || allowedSet.has("content");
    return allowedSet.has(item.id);
  }), [staffProfile, allowedSet]);

  const resolvedPage = navFiltered.some((n) => n.id === activePage)
    ? activePage
    : (navFiltered[0]?.id ?? "dashboard");

  const PageComponent = PAGES[resolvedPage] || PAGES.dashboard;

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
            FABLESTAR
          </div>
          <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace", marginTop: 4, letterSpacing: "0.08em", textTransform: "uppercase" }}>Admin Console</div>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2, padding: "0 8px" }}>
          {navFiltered.map(item => {
            const isActive = resolvedPage === item.id;
            const isHovered = sidebarHovered === item.id;
            const isForge = item.highlight;
            return (
              <button key={item.id} onClick={() => setActivePage(item.id)}
                onMouseEnter={() => setSidebarHovered(item.id)} onMouseLeave={() => setSidebarHovered(null)}
                style={{
                  display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", border: "none", borderRadius: 6,
                  background: isActive ? (isForge ? COLORS.forgeGlow : COLORS.accentGlow) : isHovered ? COLORS.bgHover : "transparent",
                  color: isActive ? (isForge ? COLORS.forge : COLORS.accent) : isHovered ? COLORS.text : COLORS.textMuted,
                  cursor: "pointer", fontSize: 13, fontWeight: isActive ? 600 : 400,
                  fontFamily: "'DM Sans', sans-serif", textAlign: "left", transition: "all 0.12s ease", position: "relative",
                }}
              >
                {isActive && <div style={{ position: "absolute", left: 0, top: "50%", transform: "translateY(-50%)", width: 3, height: 18, borderRadius: "0 2px 2px 0", background: isForge ? COLORS.forge : COLORS.accent }} />}
                <span style={{ opacity: isActive ? 1 : 0.6 }}>{item.icon}</span>
                {item.label}
                {isForge && !isActive && <span style={{ marginLeft: "auto", width: 6, height: 6, borderRadius: "50%", background: COLORS.forge, animation: "pulse 2s infinite" }} />}
              </button>
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
        <PageComponent />
      </main>
    </div>
  );
}
