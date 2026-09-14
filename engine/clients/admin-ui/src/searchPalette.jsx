import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";
import { useDebounced } from "./listHooks.js";

// Search everything (Ctrl+K or /): console pages, characters, accounts, rooms, items, creatures and
// lexicon keys. The server returns only kinds the staff member has the tool for, each result with
// the address that opens it.

const mono = "'JetBrains Mono', monospace";

export default function SearchPalette({ pages }) {
  const { colors: COLORS } = useAdminTheme();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const q = useDebounced(query, 180);
  const [groups, setGroups] = useState([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName) || e.target?.isContentEditable;
      if ((e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  useEffect(() => {
    let alive = true;
    if (!open || q.trim().length < 2) return undefined;
    axios.get(`${API_BASE}/admin/search`, { params: { q } })
      .then(({ data }) => { if (alive) { setGroups(data.groups || []); setActive(0); } })
      .catch(() => alive && setGroups([]));
    return () => { alive = false; };
  }, [q, open]);

  const needle = query.trim().toLowerCase();
  const pageHits = useMemo(() => (needle ? pages.filter((p) => `${p.label} ${p.group}`.toLowerCase().includes(needle)) : []), [pages, needle]);
  const sections = [
    ...(pageHits.length ? [{ kind: "pages", label: "Pages", total: pageHits.length, results: pageHits.map((p) => ({ id: p.id, label: p.label, sub: p.group, href: `#/${p.id}` })) }] : []),
    ...(needle.length >= 2 ? groups : []),
  ];
  const flat = sections.flatMap((s) => s.results);
  const starts = sections.map((_, i) => sections.slice(0, i).reduce((n, s) => n + s.results.length, 0));

  const close = () => { setOpen(false); setQuery(""); setGroups([]); };
  const go = (hit) => { if (hit) { window.location.assign(hit.href); close(); } };
  const onKeyDown = (e) => {
    if (e.key === "Escape") close();
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(flat.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter") go(flat[active]);
  };

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} title="Search everything (Ctrl+K)"
        style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 12px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 8, color: COLORS.textMuted, cursor: "pointer", fontSize: 13, minWidth: 240 }}>
        Search characters, rooms, items…
        <span style={{ marginLeft: "auto", fontFamily: mono, fontSize: 11, color: COLORS.textDim, border: `1px solid ${COLORS.border}`, borderRadius: 4, padding: "0 5px" }}>Ctrl K</span>
      </button>
      {open && (
        <div role="dialog" aria-modal="true" aria-label="Search" onClick={close}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 1000, display: "flex", justifyContent: "center", alignItems: "flex-start", paddingTop: "12vh", paddingInline: 16 }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{ width: "min(640px, 100%)", background: COLORS.bgPanel, border: `1px solid ${COLORS.border}`, borderRadius: 12, boxShadow: "0 20px 60px rgba(0,0,0,0.35)", overflow: "hidden" }}>
            <input id="global-search" ref={inputRef} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKeyDown}
              placeholder="Search everything…" aria-label="Search everything" autoComplete="off"
              style={{ width: "100%", padding: "14px 16px", border: "none", borderBottom: `1px solid ${COLORS.border}`, background: "transparent", color: COLORS.text, fontSize: 15, outline: "none" }} />
            <div style={{ maxHeight: "55vh", overflowY: "auto", padding: "6px 0" }}>
              {needle.length > 0 && flat.length === 0 && (
                <div style={{ padding: "14px 16px", fontSize: 13, color: COLORS.textMuted }}>{needle.length < 2 ? "Keep typing…" : "Nothing matches."}</div>
              )}
              {sections.map((section, si) => (
                <div key={section.kind}>
                  <div style={{ padding: "8px 16px 4px", fontSize: 10, fontWeight: 600, color: COLORS.textDim, textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: mono }}>
                    {section.label}{section.total > section.results.length ? ` · ${section.results.length} of ${section.total}` : ""}
                  </div>
                  {section.results.map((hit, ri) => {
                    const mine = starts[si] + ri;
                    return (
                      <button key={`${section.kind}-${hit.id}`} type="button" onMouseEnter={() => setActive(mine)} onClick={() => go(hit)}
                        style={{ display: "flex", width: "100%", gap: 12, alignItems: "baseline", padding: "8px 16px", border: "none", textAlign: "left", cursor: "pointer", background: active === mine ? COLORS.accentGlow : "transparent", color: COLORS.text }}>
                        <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap" }}>{hit.label}</span>
                        <span style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: mono, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{hit.sub}</span>
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
