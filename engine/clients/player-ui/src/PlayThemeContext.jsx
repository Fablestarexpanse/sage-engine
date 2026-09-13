import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { PLAY_THEMES } from "./theme.js";

const LS_KEY = "fablestar_player_ui_theme";

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

  const T = useMemo(() => PLAY_THEMES[mode], [mode]);

  useEffect(() => {
    document.documentElement.setAttribute("data-play-theme", mode);
  }, [mode]);

  const value = useMemo(() => ({ mode, setMode, toggleMode, T }), [mode, setMode, toggleMode, T]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePlayTheme() {
  const v = useContext(Ctx);
  if (!v) {
    throw new Error("usePlayTheme must be used within PlayThemeProvider");
  }
  return v;
}
