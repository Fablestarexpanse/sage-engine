/** Admin console + world builder palettes (inline styles). */

export const ADMIN_THEME_DARK = {
  bg: "#0a0b0f",
  bgPanel: "#111318",
  bgCard: "#161920",
  bgHover: "#1c1f28",
  bgInput: "#0d0e13",
  border: "#252833",
  borderActive: "#3d4158",
  text: "#c8cad4",
  textMuted: "#6b6f82",
  textDim: "#454860",
  accent: "#7c6aef",
  accentGlow: "rgba(124,106,239,0.15)",
  accentSoft: "#5a4bc7",
  success: "#34d399",
  successBg: "rgba(52,211,153,0.08)",
  warning: "#fbbf24",
  warningBg: "rgba(251,191,36,0.08)",
  danger: "#f87171",
  dangerBg: "rgba(248,113,113,0.08)",
  info: "#60a5fa",
  infoBg: "rgba(96,165,250,0.08)",
  cyan: "#22d3ee",
  cyanBg: "rgba(34,211,238,0.08)",
  forge: "#e879f9",
  forgeBg: "rgba(232,121,249,0.08)",
  forgeGlow: "rgba(232,121,249,0.15)",
};

export const ADMIN_THEME_LIGHT = {
  bg: "#e8eaf2",
  bgPanel: "#ffffff",
  bgCard: "#f4f5fb",
  bgHover: "#e8e6ff",
  bgInput: "#ffffff",
  border: "#c9cfde",
  borderActive: "#8b93ad",
  text: "#1a1d28",
  textMuted: "#5a6172",
  textDim: "#7a8194",
  accent: "#5b4cdb",
  accentGlow: "rgba(91,76,219,0.12)",
  accentSoft: "#4338a8",
  success: "#059669",
  successBg: "rgba(5,150,105,0.1)",
  warning: "#b45309",
  warningBg: "rgba(180,83,9,0.1)",
  danger: "#dc2626",
  dangerBg: "rgba(220,38,38,0.1)",
  info: "#2563eb",
  infoBg: "rgba(37,99,235,0.1)",
  cyan: "#0891b2",
  cyanBg: "rgba(8,145,178,0.1)",
  forge: "#a21caf",
  forgeBg: "rgba(162,28,175,0.1)",
  forgeGlow: "rgba(162,28,175,0.15)",
};

export const ADMIN_THEMES = {
  dark: ADMIN_THEME_DARK,
  light: ADMIN_THEME_LIGHT,
};

/** Room-type swatches for builder (depends on palette). */
export function adminRoomTypeColors(C) {
  return {
    chamber: C.cyan,
    corridor: C.textMuted,
    junction: C.accent,
    alcove: C.info,
    descent: C.warning,
    danger: C.danger,
    safe: C.success,
    boss: C.danger,
    hub: C.forge,
    command: C.info,
    engineering: C.warning,
    airlock: C.danger,
    "?": C.textDim,
  };
}
