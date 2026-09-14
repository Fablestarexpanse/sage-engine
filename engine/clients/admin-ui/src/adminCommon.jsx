// Shared admin console primitives: nav/auth constants, ws helpers, icons,
// UI atoms, and the polled-fetch hook. Split out of App.jsx (2026-09-12).
import { useState, useEffect } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { WS_BASE } from "./apiConfig.js";

const LS_ADMIN_TOKEN = "sage_admin_token";

/** Tool ids enforced by Nexus (see sage.admin.admin_security.NAV_TOOL_IDS). */
const ALL_ADMIN_TOOLS = [
  "dashboard", "forge", "operations", "players", "world", "entities",
  "items", "skills", "agents", "shops", "lexicon", "server", "content", "team",
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

// Visually distinct affordance for actions that are not built yet — dashed border
// and a hint popover, so unbuilt features never look like working buttons or errors.
const PlannedAction = ({ children, hint, small, icon }) => {
  const { colors: COLORS } = useAdminTheme();
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: "relative", display: "inline-flex" }}>
      <button
        type="button"
        title={hint}
        onClick={() => setOpen((o) => !o)}
        onBlur={() => setOpen(false)}
        style={{
          display: "inline-flex", alignItems: "center", gap: 6, padding: small ? "4px 10px" : "8px 16px",
          fontSize: small ? 12 : 13, fontWeight: 500, fontFamily: "'DM Sans', sans-serif",
          border: `1px dashed ${COLORS.border}`, borderRadius: 6,
          background: "transparent", color: COLORS.textDim, cursor: "help", whiteSpace: "nowrap",
        }}
      >
        {icon}{children}
        <span style={{ fontSize: 9, letterSpacing: "0.06em", textTransform: "uppercase", border: `1px solid ${COLORS.border}`, borderRadius: 4, padding: "1px 4px" }}>planned</span>
      </button>
      {open && hint && (
        <span style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 40, width: 280, padding: "8px 10px", fontSize: 11, lineHeight: 1.5, color: COLORS.textMuted, background: COLORS.bgPanel, border: `1px solid ${COLORS.border}`, borderRadius: 8, boxShadow: "0 8px 24px rgba(0,0,0,0.35)" }}>{hint}</span>
      )}
    </span>
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

export {
  LS_ADMIN_TOKEN, ALL_ADMIN_TOOLS, adminWsBase, adminPresenceWsUrl, adminLogsWsUrl,
  sendWsAuthToken, parseLeadingInt, parseRoomType, extractYamlRoomId, Icons,
  Badge, StatusDot, Pill, ActionButton, PlannedAction, SearchBar, TabBar,
  DataTable, StatCard, usePolledList, FetchErrorBanner,
};
