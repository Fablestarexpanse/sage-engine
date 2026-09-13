import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { usePlayTheme } from "./PlayThemeContext.jsx";

/**
 * Allocate starter proficiency points (sum ≤ budget, each leaf ≤ maxPerLeaf).
 * `value` / `onChange` use leaf id → non-negative integer (zeros omitted when submitting).
 * @param {'compact'|'full'} [variant] — full: domain chips, picked-only filter, taller list (chargen step 2).
 */
export function ChargenSkillPicker({ budget, maxPerLeaf, leaves, value, onChange, disabled, variant = "compact" }) {
  const { T } = usePlayTheme();
  const [domain, setDomain] = useState("");
  const [q, setQ] = useState("");
  const [pickedOnly, setPickedOnly] = useState(false);
  const [skillTip, setSkillTip] = useState(null);
  const isFull = variant === "full";

  const showSkillTip = useCallback((e, text) => {
    const pad = 14;
    const maxW = 320;
    let x = e.clientX + pad;
    let y = e.clientY + pad;
    if (typeof window !== "undefined") {
      x = Math.min(Math.max(8, x), window.innerWidth - maxW - 12);
      y = Math.min(Math.max(8, y), window.innerHeight - 80);
    }
    setSkillTip({ x, y, text: text || "" });
  }, []);

  const moveSkillTip = useCallback((e) => {
    setSkillTip((prev) => {
      if (!prev) return prev;
      const pad = 14;
      const maxW = 320;
      let x = e.clientX + pad;
      let y = e.clientY + pad;
      if (typeof window !== "undefined") {
        x = Math.min(Math.max(8, x), window.innerWidth - maxW - 12);
        y = Math.min(Math.max(8, y), window.innerHeight - 80);
      }
      return { ...prev, x, y };
    });
  }, []);

  const hideSkillTip = useCallback(() => setSkillTip(null), []);

  useEffect(() => {
    if (disabled) setSkillTip(null);
  }, [disabled]);

  const domains = useMemo(() => {
    const s = new Set();
    for (const L of leaves || []) {
      if (L?.domain) s.add(L.domain);
    }
    return [...s].sort();
  }, [leaves]);

  const used = useMemo(() => Object.values(value || {}).reduce((a, n) => a + (Number(n) || 0), 0), [value]);

  const filtered = useMemo(() => {
    const needle = (q || "").trim().toLowerCase();
    return (leaves || []).filter((L) => {
      if (pickedOnly && !(Number(value?.[L.id]) > 0)) return false;
      if (domain && L.domain !== domain) return false;
      if (!needle) return true;
      return (
        (L.id && L.id.toLowerCase().includes(needle)) ||
        (L.name && String(L.name).toLowerCase().includes(needle)) ||
        (L.domain && L.domain.toLowerCase().includes(needle))
      );
    });
  }, [leaves, domain, q, pickedOnly, value]);

  const setLevel = (id, nextRaw) => {
    const cur = { ...(value || {}) };
    let n = Math.max(0, Math.floor(Number(nextRaw) || 0));
    n = Math.min(n, maxPerLeaf);
    const prev = Number(cur[id]) || 0;
    const other = used - prev;
    const capLeft = Math.max(0, budget - other);
    n = Math.min(n, capLeft);
    if (n <= 0) delete cur[id];
    else cur[id] = n;
    onChange?.(cur);
  };

  const bump = (id, delta) => {
    const prev = Number(value?.[id]) || 0;
    setLevel(id, prev + delta);
  };

  const btn = (active) => ({
    padding: "4px 10px",
    borderRadius: T.radius.sm,
    border: `1px solid ${active ? T.border.medium : T.border.dim}`,
    background: T.bg.surface,
    color: active ? T.text.primary : T.text.muted,
    fontSize: 11,
    fontWeight: 600,
    cursor: disabled ? "not-allowed" : "pointer",
    minWidth: 32,
  });

  const chip = (active) => ({
    padding: "6px 11px",
    borderRadius: 999,
    border: `1px solid ${active ? T.border.glyph : T.border.dim}`,
    background: active ? T.glyph.violetDim : T.bg.surface,
    color: active ? T.text.primary : T.text.muted,
    fontSize: 11,
    fontWeight: 600,
    cursor: disabled ? "not-allowed" : "pointer",
    whiteSpace: "nowrap",
  });

  const listMaxH = isFull ? "min(55vh, 480px)" : 220;

  const tipPortal = skillTip?.text
    ? createPortal(
      <div
        role="tooltip"
        style={{
          position: "fixed",
          left: skillTip.x,
          top: skillTip.y,
          maxWidth: 320,
          zIndex: 100002,
          padding: "10px 12px",
          borderRadius: T.radius.md,
          border: `1px solid ${T.border.medium}`,
          background: T.bg.panel,
          boxShadow: T.shadow.panel,
          color: T.text.secondary,
          fontSize: 11,
          lineHeight: 1.5,
          pointerEvents: "none",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {skillTip.text}
      </div>,
      document.body
    )
    : null;

  return (
    <div
      style={{
        borderRadius: T.radius.lg,
        border: `1px solid ${T.border.medium}`,
        background: T.bg.panel,
        padding: isFull ? "16px 18px" : "12px 14px",
        display: "flex",
        flexDirection: "column",
        gap: isFull ? 14 : 10,
      }}
    >
      <div>
        <div style={{ fontSize: isFull ? 13 : 11, fontWeight: 700, color: T.text.primary, fontFamily: T.font.display }}>
          {isFull ? "Skill catalog" : "Starting proficiencies"}
        </div>
        <p style={{ fontSize: 11, color: T.text.muted, margin: "6px 0 0", lineHeight: 1.45 }}>
          Spend up to <strong style={{ color: T.text.accent }}>{budget}</strong> points (max{" "}
          <strong style={{ color: T.text.accent }}>{maxPerLeaf}</strong> per leaf). Unspent points stay in the pool — you grow the rest in
          play.
        </p>
        {isFull ? (
          <div style={{ marginTop: 10, height: 8, borderRadius: 99, background: T.bg.deep, overflow: "hidden" }}>
            <div
              style={{
                width: `${budget ? Math.min(100, (used / budget) * 100) : 0}%`,
                height: "100%",
                borderRadius: 99,
                background: `linear-gradient(90deg, ${T.glyph.violet}, ${T.glyph.cyan})`,
                transition: "width 0.2s ease",
              }}
            />
          </div>
        ) : null}
      </div>

      {isFull ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Domain</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, flex: 1, minWidth: 0 }}>
            <button type="button" disabled={disabled} style={chip(!domain)} onClick={() => setDomain("")}>
              All
            </button>
            {domains.map((d) => (
              <button key={d} type="button" disabled={disabled} style={chip(domain === d)} onClick={() => setDomain(d === domain ? "" : d)}>
                {d.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        {!isFull ? (
          <>
            <label style={{ fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Domain</label>
            <select
              value={domain}
              disabled={disabled}
              onChange={(e) => setDomain(e.target.value)}
              style={{
                flex: "1 1 140px",
                minWidth: 120,
                maxWidth: 220,
                padding: "6px 8px",
                borderRadius: T.radius.md,
                border: `1px solid ${T.border.medium}`,
                background: T.bg.surface,
                color: T.text.primary,
                fontSize: 12,
              }}
            >
              <option value="">All domains ({domains.length})</option>
              {domains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </>
        ) : null}
        <input
          type="search"
          placeholder="Search name or id…"
          value={q}
          disabled={disabled}
          onChange={(e) => setQ(e.target.value)}
          style={{
            flex: isFull ? "1 1 200px" : "2 1 180px",
            minWidth: 140,
            padding: "8px 11px",
            borderRadius: T.radius.md,
            border: `1px solid ${T.border.medium}`,
            background: T.bg.surface,
            color: T.text.primary,
            fontSize: 12,
            boxSizing: "border-box",
          }}
        />
        {isFull ? (
          <label
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              color: T.text.secondary,
              cursor: disabled ? "not-allowed" : "pointer",
              userSelect: "none",
            }}
          >
            <input type="checkbox" checked={pickedOnly} disabled={disabled} onChange={(e) => setPickedOnly(e.target.checked)} />
            Picked only
          </label>
        ) : null}
        <span style={{ fontSize: 11, color: used > budget ? T.text.danger : T.text.secondary, marginLeft: "auto", whiteSpace: "nowrap" }}>
          {used} / {budget} pts
        </span>
        <button
          type="button"
          disabled={disabled || used === 0}
          onClick={() => onChange?.({})}
          style={{
            padding: "6px 10px",
            borderRadius: T.radius.md,
            border: `1px solid ${T.border.dim}`,
            background: T.bg.surface,
            color: used === 0 ? T.text.muted : T.text.secondary,
            fontSize: 10,
            cursor: disabled || used === 0 ? "not-allowed" : "pointer",
          }}
        >
          Clear picks
        </button>
      </div>
      <div
        style={{
          maxHeight: listMaxH,
          overflowY: "auto",
          borderRadius: T.radius.md,
          border: `1px solid ${T.border.dim}`,
          background: T.bg.surface,
        }}
      >
        {filtered.length === 0 ? (
          <div style={{ padding: 16, fontSize: 12, color: T.text.muted, textAlign: "center" }}>No skills match this filter.</div>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {filtered.map((L) => {
              const lv = Number(value?.[L.id]) || 0;
              const tipText = (typeof L.detail === "string" && L.detail.trim()) || `${L.domain} — ${L.id}`;
              return (
                <li
                  key={L.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "6px 10px",
                    borderBottom: `1px solid ${T.border.dim}`,
                    fontSize: 11,
                  }}
                >
                  <div
                    style={{ flex: 1, minWidth: 0, cursor: "help" }}
                    onMouseEnter={(e) => !disabled && showSkillTip(e, tipText)}
                    onMouseMove={(e) => !disabled && moveSkillTip(e)}
                    onMouseLeave={hideSkillTip}
                  >
                    <div style={{ color: T.text.primary, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {L.name || L.id}
                    </div>
                    <div style={{ fontSize: 9, color: T.text.muted, fontFamily: T.font.mono, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {L.domain} · {L.id}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                    <button type="button" disabled={disabled || lv <= 0} style={btn(lv > 0)} onClick={() => bump(L.id, -1)}>
                      −
                    </button>
                    <input
                      type="number"
                      min={0}
                      max={maxPerLeaf}
                      value={lv}
                      disabled={disabled}
                      onChange={(e) => setLevel(L.id, e.target.value)}
                      style={{
                        width: 44,
                        padding: "4px 6px",
                        borderRadius: T.radius.sm,
                        border: `1px solid ${T.border.medium}`,
                        background: T.bg.panel,
                        color: T.text.primary,
                        fontSize: 12,
                        textAlign: "center",
                      }}
                    />
                    <button
                      type="button"
                      disabled={disabled || lv >= maxPerLeaf || used >= budget}
                      style={btn(lv < maxPerLeaf && used < budget)}
                      onClick={() => bump(L.id, 1)}
                    >
                      +
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {tipPortal}
    </div>
  );
}
