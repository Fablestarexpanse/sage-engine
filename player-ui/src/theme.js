/** Dark (default) play client palette — same structure as light. */
export const PLAY_THEME_DARK = {
  bg: { void: "#08090c", deep: "#0c0e14", panel: "#111318", panelHover: "#161921", surface: "#1a1d25", elevated: "#1e2230", overlay: "rgba(8,9,12,0.92)" },
  border: { subtle: "rgba(255,255,255,0.04)", dim: "rgba(255,255,255,0.07)", medium: "rgba(255,255,255,0.12)", glyph: "rgba(167,139,250,0.25)", glyphHot: "rgba(167,139,250,0.5)", danger: "rgba(239,68,68,0.4)", success: "rgba(52,211,153,0.4)" },
  text: { primary: "#e2e4ea", secondary: "#8b8fa4", muted: "#5a5e72", accent: "#a78bfa", glyph: "#c4b5fd", danger: "#f87171", success: "#34d399", gold: "#fbbf24", info: "#60a5fa", narrative: "#d1cfe0" },
  currency: {
    /** Small caps line above balance (must stay readable on tinted bg in light + dark). */
    digi: {
      fg: "#fb923c",
      bg: "rgba(251,146,60,0.14)",
      border: "rgba(251,146,60,0.5)",
      dim: "rgba(251,146,60,0.28)",
      label: "#fdba74",
    },
    pixel: {
      fg: "#e879f9",
      bg: "rgba(232,121,249,0.12)",
      border: "rgba(232,121,249,0.5)",
      dim: "rgba(232,121,249,0.3)",
      warn: "#fbbf24",
      label: "#f0abfc",
    },
  },
  reputation: { evil: "#dc2626", mid: "#fbbf24", good: "#16a34a" },
  glyph: { violet: "#a78bfa", violetDim: "rgba(167,139,250,0.15)", violetGlow: "rgba(167,139,250,0.3)", cyan: "#22d3ee", cyanDim: "rgba(34,211,238,0.15)", amber: "#f59e0b", amberDim: "rgba(245,158,11,0.15)", crimson: "#ef4444", crimsonDim: "rgba(239,68,68,0.15)", emerald: "#10b981", emeraldDim: "rgba(16,185,129,0.15)" },
  radius: { sm: 4, md: 6, lg: 10, xl: 14 },
  /** display: headings / room titles / branding — was Cinzel + Cormorant Garamond (fantasy serif). */
  font: { mono: "'JetBrains Mono','Fira Code',monospace", display: "'Oxanium','Exo 2',system-ui,sans-serif", body: "'Barlow','IBM Plex Sans',sans-serif" },
  shadow: { panel: "0 2px 20px rgba(0,0,0,0.5),0 0 1px rgba(167,139,250,0.1)", panelHover: "0 4px 30px rgba(0,0,0,0.6),0 0 2px rgba(167,139,250,0.2)", glow: "0 0 20px rgba(167,139,250,0.15)" },
  /** Account GM crown badge (not staff console) */
  gmBadge: { bg: "rgba(244, 114, 182, 0.18)", border: "rgba(244, 114, 182, 0.55)", text: "#fce7f3" },
};

export const PLAY_THEME_LIGHT = {
  bg: { void: "#e8eaf2", deep: "#dfe3ec", panel: "#ffffff", panelHover: "#f4f6fb", surface: "#eef1f8", elevated: "#ffffff", overlay: "rgba(255,255,255,0.94)" },
  border: { subtle: "rgba(0,0,0,0.06)", dim: "rgba(0,0,0,0.1)", medium: "rgba(0,0,0,0.14)", glyph: "rgba(109,78,214,0.22)", glyphHot: "rgba(109,78,214,0.45)", danger: "rgba(220,38,38,0.35)", success: "rgba(5,150,105,0.35)" },
  text: { primary: "#1a1d28", secondary: "#4b5163", muted: "#6b7280", accent: "#6d4ed6", glyph: "#5b3cc4", danger: "#dc2626", success: "#059669", gold: "#b45309", info: "#2563eb", narrative: "#3d4354" },
  currency: {
    digi: {
      fg: "#c2410c",
      bg: "rgba(234,88,12,0.12)",
      border: "rgba(234,88,12,0.45)",
      dim: "rgba(234,88,12,0.25)",
      label: "#7c2d12",
    },
    pixel: {
      fg: "#a21caf",
      bg: "rgba(162,28,175,0.1)",
      border: "rgba(162,28,175,0.45)",
      dim: "rgba(162,28,175,0.25)",
      warn: "#b45309",
      label: "#701a75",
    },
  },
  reputation: { evil: "#b91c1c", mid: "#d97706", good: "#15803d" },
  glyph: { violet: "#6d4ed6", violetDim: "rgba(109,78,214,0.12)", violetGlow: "rgba(109,78,214,0.22)", cyan: "#0891b2", cyanDim: "rgba(8,145,178,0.12)", amber: "#d97706", amberDim: "rgba(217,119,6,0.12)", crimson: "#dc2626", crimsonDim: "rgba(220,38,38,0.12)", emerald: "#059669", emeraldDim: "rgba(5,150,105,0.12)" },
  radius: { sm: 4, md: 6, lg: 10, xl: 14 },
  /** display: headings / room titles / branding — was Cinzel + Cormorant Garamond (fantasy serif). */
  font: { mono: "'JetBrains Mono','Fira Code',monospace", display: "'Oxanium','Exo 2',system-ui,sans-serif", body: "'Barlow','IBM Plex Sans',sans-serif" },
  shadow: { panel: "0 2px 16px rgba(15,23,42,0.08),0 0 1px rgba(109,78,214,0.08)", panelHover: "0 6px 24px rgba(15,23,42,0.1),0 0 2px rgba(109,78,214,0.12)", glow: "0 0 16px rgba(109,78,214,0.12)" },
  /** Strong contrast: dark rose on soft pink (light UI backgrounds) */
  gmBadge: { bg: "rgba(157, 23, 77, 0.12)", border: "rgba(131, 24, 67, 0.5)", text: "#831843" },
};

export const PLAY_THEMES = {
  dark: PLAY_THEME_DARK,
  light: PLAY_THEME_LIGHT,
};

export const clamp = (v, mn, mx) => Math.max(mn, Math.min(mx, v));
