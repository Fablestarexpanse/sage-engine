/**
 * Nexus HTTP + WebSocket bases.
 *
 * In dev, defaults go through the Vite proxy at /__nexus →127.0.0.1:8001 (same origin as the admin UI).
 * That avoids Firefox and other environments where direct requests to 127.0.0.1:8001 fail.
 *
 * Set VITE_DIRECT_NEXUS=1 (and optional VITE_API_BASE / VITE_WS_BASE) to talk to Nexus directly.
 * Production builds must set VITE_API_BASE / VITE_WS_BASE (or rely on the 127.0.0.1 fallbacks).
 */
function pickBase(envVal, fallback) {
  if (envVal == null) return fallback;
  const s = String(envVal).trim();
  return s !== "" ? s.replace(/\/$/, "") : fallback;
}

const directNexus =
  import.meta.env.VITE_DIRECT_NEXUS === "1" || import.meta.env.VITE_DIRECT_NEXUS === "true";

function devProxyHttp() {
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}/__nexus`;
  }
  return "http://127.0.0.1:8001";
}

function devProxyWs() {
  if (typeof window !== "undefined" && window.location?.href) {
    const u = new URL(window.location.href);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    u.pathname = "/__nexus";
    u.search = "";
    u.hash = "";
    return u.href.replace(/\/$/, "");
  }
  return "ws://127.0.0.1:8001";
}

const fallbackHttp = "http://127.0.0.1:8001";
const fallbackWs = "ws://127.0.0.1:8001";

export const API_BASE = import.meta.env.DEV && !directNexus
  ? devProxyHttp()
  : pickBase(import.meta.env.VITE_API_BASE, fallbackHttp);

export const WS_BASE = import.meta.env.DEV && !directNexus
  ? devProxyWs()
  : pickBase(import.meta.env.VITE_WS_BASE, fallbackWs);
