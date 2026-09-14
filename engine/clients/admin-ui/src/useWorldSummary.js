import { useEffect, useState } from "react";
import axios from "axios";
import { API_BASE } from "./apiConfig.js";

// GET /admin/world: engine version, the running world, loaded plugins, AI slots, online counts.
// One shared request per refresh window, whichever pages ask for it.
let cached = null;
let cachedAt = 0;
let inflight = null;
const TTL_MS = 15000;

async function fetchSummary(force = false) {
  if (!force && cached && Date.now() - cachedAt < TTL_MS) return cached;
  if (!inflight) {
    inflight = axios
      .get(`${API_BASE}/admin/world`)
      .then(({ data }) => {
        cached = data;
        cachedAt = Date.now();
        return data;
      })
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

export function useWorldSummary(refreshMs = TTL_MS) {
  const [summary, setSummary] = useState(cached);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = (force) =>
      fetchSummary(force)
        .then((data) => {
          if (alive) {
            setSummary(data);
            setError(null);
          }
        })
        .catch((e) => alive && setError(e?.response?.data?.detail || e.message || "unavailable"));
    load(false);
    const id = setInterval(() => load(true), refreshMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [refreshMs]);
  return { summary, error };
}

/** Whether the running world fills an AI slot (false while unknown). */
export function slotEnabled(summary, slot) {
  return Boolean(summary?.ai_slots?.[slot]?.enabled);
}
