import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { PLAY_THEMES, withAccent } from "./theme.js";
import { useWorld } from "./WorldContext.jsx";

const LS_KEY = "sage_player_ui_theme";

const Ctx = createContext(null);

export function PlayThemeProvider({ children }) {
  const [mode, setModeState] = useState(() => {
    try {
      const s = localStorage.getItem(LS_KEY);
      if (s === "light" || s === "dark") return s;
    } catch {
      /* ignore */
    }
    if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: light)").matches) {
      return "light";
    }
    return "dark";
  });

  const setMode = useCallback((m) => {
    if (m !== "light" && m !== "dark") return;
    setModeState(m);
    try {
      localStorage.setItem(LS_KEY, m);
    } catch {
      /* ignore */
    }
  }, []);

  const toggleMode = useCallback(() => {
    setMode(mode === "dark" ? "light" : "dark");
  }, [mode, setMode]);

  // The world's ui/theme.yaml may recolour the accent and set the header mark.
  const { theme } = useWorld();
  const T = useMemo(() => withAccent(PLAY_THEMES[mode], theme?.accent?.[mode], mode), [mode, theme]);
  const mark = theme?.mark || "◈";

  useEffect(() => {
    document.documentElement.setAttribute("data-play-theme", mode);
  }, [mode]);

  const value = useMemo(() => ({ mode, setMode, toggleMode, T, mark }), [mode, setMode, toggleMode, T, mark]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePlayTheme() {
  const v = useContext(Ctx);
  if (!v) {
    throw new Error("usePlayTheme must be used within PlayThemeProvider");
  }
  return v;
}
