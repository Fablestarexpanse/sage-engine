import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ADMIN_THEMES } from "./adminTheme.js";

const LS_KEY = "fablestar_admin_ui_theme";

const Ctx = createContext(null);

export function AdminThemeProvider({ children }) {
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

  const colors = useMemo(() => ADMIN_THEMES[mode], [mode]);

  useEffect(() => {
    document.documentElement.setAttribute("data-admin-theme", mode);
  }, [mode]);

  const value = useMemo(
    () => ({ mode, setMode, toggleMode, colors }),
    [mode, setMode, toggleMode, colors]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAdminTheme() {
  const v = useContext(Ctx);
  if (!v) {
    throw new Error("useAdminTheme must be used within AdminThemeProvider");
  }
  return v;
}
