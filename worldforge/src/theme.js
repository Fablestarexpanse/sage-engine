/** Dark palette — mirrors admin-ui builderConstants. */
export const COLORS_DARK = {
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
  accentGlow: "rgba(124, 106, 239, 0.12)",
  success: "#34d399",
  warning: "#fbbf24",
  danger: "#f87171",
  info: "#60a5fa",
  cyan: "#22d3ee",
  forge: "#e879f9",
  // Tint tokens — kept in parity with admin-ui's adminTheme.js so components
  // ported between the two apps don't silently render "undefined" backgrounds.
  accentSoft: "#5a4bc7",
  successBg: "rgba(52,211,153,0.08)",
  warningBg: "rgba(251,191,36,0.08)",
  dangerBg: "rgba(248,113,113,0.08)",
  infoBg: "rgba(96,165,250,0.08)",
  cyanBg: "rgba(34,211,238,0.08)",
  forgeBg: "rgba(232,121,249,0.08)",
  forgeGlow: "rgba(232,121,249,0.15)",
};

export const ROOM_TYPE_COLORS_DARK = {
  chamber: COLORS_DARK.cyan,
  corridor: COLORS_DARK.textMuted,
  junction: COLORS_DARK.accent,
  alcove: COLORS_DARK.info,
  descent: COLORS_DARK.warning,
  danger: COLORS_DARK.danger,
  safe: COLORS_DARK.success,
  boss: COLORS_DARK.danger,
  hub: COLORS_DARK.forge,
  command: COLORS_DARK.info,
  engineering: COLORS_DARK.warning,
  airlock: COLORS_DARK.danger,
  "?": COLORS_DARK.textDim,
};

/** Light palette for desktop tool readability (avoid pure white chrome). */
export const COLORS_LIGHT = {
  bg: "#d6dae6",
  bgPanel: "#e8ebf4",
  bgCard: "#f0f2f8",
  bgHover: "#dde1ec",
  bgInput: "#f6f7fb",
  border: "#aeb6ca",
  borderActive: "#7c82a3",
  text: "#1a1d28",
  textMuted: "#4b5166",
  textDim: "#7a8199",
  accent: "#5b4cdb",
  accentGlow: "rgba(91, 76, 219, 0.1)",
  success: "#059669",
  warning: "#b45309",
  danger: "#dc2626",
  info: "#2563eb",
  cyan: "#0e7490",
  forge: "#a21caf",
  // Tint tokens — parity with adminTheme.js (see COLORS_DARK note).
  accentSoft: "#4338a8",
  successBg: "rgba(5,150,105,0.1)",
  warningBg: "rgba(180,83,9,0.1)",
  dangerBg: "rgba(220,38,38,0.1)",
  infoBg: "rgba(37,99,235,0.1)",
  cyanBg: "rgba(8,145,178,0.1)",
  forgeBg: "rgba(162,28,175,0.1)",
  forgeGlow: "rgba(162,28,175,0.15)",
};

export const ROOM_TYPE_COLORS_LIGHT = {
  chamber: COLORS_LIGHT.cyan,
  corridor: COLORS_LIGHT.textMuted,
  junction: COLORS_LIGHT.accent,
  alcove: COLORS_LIGHT.info,
  descent: COLORS_LIGHT.warning,
  danger: COLORS_LIGHT.danger,
  safe: COLORS_LIGHT.success,
  boss: COLORS_LIGHT.danger,
  hub: COLORS_LIGHT.forge,
  command: COLORS_LIGHT.info,
  engineering: COLORS_LIGHT.warning,
  airlock: COLORS_LIGHT.danger,
  "?": COLORS_LIGHT.textDim,
};

/**
 * @param {"dark" | "light"} scheme
 * @returns {{ colors: typeof COLORS_DARK, roomTypeColors: typeof ROOM_TYPE_COLORS_DARK }}
 */
export function getPalette(scheme) {
  if (scheme === "light") {
    return { colors: COLORS_LIGHT, roomTypeColors: ROOM_TYPE_COLORS_LIGHT };
  }
  return { colors: COLORS_DARK, roomTypeColors: ROOM_TYPE_COLORS_DARK };
}
