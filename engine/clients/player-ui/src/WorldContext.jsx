import { createContext, useContext, useEffect, useState } from "react";
import { playFetchWorld } from "./playApi.js";

/** The world this server runs (GET /play/world): its display name titles the page and headers. */
const WorldContext = createContext({ id: "", name: "" });

export function WorldProvider({ children }) {
  const [world, setWorld] = useState({ id: "", name: "" });

  useEffect(() => {
    let cancelled = false;
    playFetchWorld()
      .then((w) => {
        if (cancelled || !w || typeof w.name !== "string") return;
        setWorld({ id: String(w.id || ""), name: w.name });
        document.title = `${w.name} — Player`;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return <WorldContext.Provider value={world}>{children}</WorldContext.Provider>;
}

export function useWorld() {
  return useContext(WorldContext);
}
