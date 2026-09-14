import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { getPalette } from "./theme.js";

const STORAGE_KEY = "worldforge_color_scheme";

function readScheme() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "light") return "light";
    return "dark";
  } catch {
    return "dark";
  }
}

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [colorScheme, setColorScheme] = useState(readScheme);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, colorScheme);
    } catch {
      /* ignore */
    }
  }, [colorScheme]);

  useEffect(() => {
    const { colors } = getPalette(colorScheme);
    const root = document.documentElement;
    root.style.setProperty("--wf-bg", colors.bg);
    root.style.setProperty("--wf-text", colors.text);
    root.style.setProperty("--wf-panel", colors.bgPanel);
    root.style.setProperty("--wf-border", colors.border);
    root.style.colorScheme = colorScheme;
  }, [colorScheme]);

  const value = useMemo(() => {
    const { colors, roomTypeColors } = getPalette(colorScheme);
    return {
      colorScheme,
      setColorScheme,
      colors,
      roomTypeColors,
    };
  }, [colorScheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const v = useContext(ThemeContext);
  if (!v) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return v;
}
