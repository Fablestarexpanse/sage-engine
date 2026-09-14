import { usePlayTheme } from "./PlayThemeContext.jsx";

/**
 * Switches Play UI between light and dark (persists in localStorage).
 * @param {'inline'|'floating'} [variant] — floating: fixed corner for auth shell; inline: sits in toolbars.
 * @param {boolean} [compact] — shorter "Light"/"Dark" labels (e.g. game client toolbar).
 */
export function ThemeToggleButton({ variant = "inline", style, compact = false }) {
  const { T, mode, toggleMode } = usePlayTheme();
  const isDark = mode === "dark";
  const floating = variant === "floating";

  const base = {
    padding: floating ? "8px 12px" : "6px 10px",
    borderRadius: T.radius.md,
    border: `1px solid ${T.border.medium}`,
    background: T.bg.surface,
    color: T.text.secondary,
    fontSize: floating ? 11 : 10,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: T.font.body,
    whiteSpace: "nowrap",
    boxShadow: floating ? T.shadow.panel : undefined,
  };

  return (
    <button
      type="button"
      onClick={toggleMode}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Use light background and higher-contrast panels" : "Use dark space theme"}
      style={{ ...base, ...style }}
    >
      {compact ? (isDark ? "Light" : "Dark") : isDark ? "Light mode" : "Dark mode"}
    </button>
  );
}

/** Fixed corner control for full-screen auth routes (welcome, sign in, register). */
export function FloatingThemeToggle() {
  return (
    <div
      style={{
        position: "fixed",
        top: 16,
        right: 16,
        zIndex: 5000,
        pointerEvents: "auto",
      }}
    >
      <ThemeToggleButton variant="floating" />
    </div>
  );
}
