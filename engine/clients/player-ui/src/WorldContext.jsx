import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { playFetchCommands, playFetchWorld } from "./playApi.js";

/** The world this server runs (GET /play/world): its display name titles the page and headers;
 * its theme (ui/theme.yaml: mark, accent) restyles the client; its command names
 * (GET /play/commands) drive input autocomplete. */
const WorldContext = createContext({ id: "", name: "", theme: {}, commands: [] });

export function WorldProvider({ children }) {
  const [world, setWorld] = useState({ id: "", name: "", theme: {} });
  const [commands, setCommands] = useState([]);

  useEffect(() => {
    let cancelled = false;
    playFetchWorld()
      .then((w) => {
        if (cancelled || !w || typeof w.name !== "string") return;
        setWorld({ id: String(w.id || ""), name: w.name, theme: w.theme && typeof w.theme === "object" ? w.theme : {} });
        document.title = `${w.name} — Player`;
      })
      .catch(() => {});
    playFetchCommands()
      .then((c) => {
        if (!cancelled && Array.isArray(c?.commands)) setCommands(c.commands.map(String));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => ({ ...world, commands }), [world, commands]);
  return <WorldContext.Provider value={value}>{children}</WorldContext.Provider>;
}

export function useWorld() {
  return useContext(WorldContext);
}
