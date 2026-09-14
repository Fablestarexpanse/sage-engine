import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { playFetchCommands, playFetchWorld } from "./playApi.js";

/** The world this server runs (GET /play/world): its display name titles the page and headers;
 * its command names (GET /play/commands) drive input autocomplete. */
const WorldContext = createContext({ id: "", name: "", commands: [] });

export function WorldProvider({ children }) {
  const [world, setWorld] = useState({ id: "", name: "" });
  const [commands, setCommands] = useState([]);

  useEffect(() => {
    let cancelled = false;
    playFetchWorld()
      .then((w) => {
        if (cancelled || !w || typeof w.name !== "string") return;
        setWorld({ id: String(w.id || ""), name: w.name });
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
