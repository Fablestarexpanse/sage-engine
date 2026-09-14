import { useCallback, useEffect, useState } from "react";

// The path after the page in the URL (#/content/items/blade -> ["items", "blade"]), and a setter
// that keeps the page. Every record a page can open gets an address staff can bookmark or paste.
function hashParts() {
  return window.location.hash.replace(/^#\/?/, "").split("/").slice(1).filter(Boolean).map(decodeURIComponent);
}

export function useHashParts() {
  const [parts, setParts] = useState(hashParts);
  useEffect(() => {
    const onHash = () => setParts(hashParts());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = useCallback((...next) => {
    const page = window.location.hash.replace(/^#\/?/, "").split("/")[0] || "dashboard";
    const tail = next.filter((x) => x != null && x !== "").map((x) => encodeURIComponent(String(x)));
    window.location.hash = `/${[page, ...tail].join("/")}`;
  }, []);
  return [parts, go];
}

// A value that follows `value` after `ms` without changes (for search boxes that query the server).
export function useDebounced(value, ms = 250) {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return settled;
}

