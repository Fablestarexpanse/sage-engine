import { useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePlayTheme } from "../PlayThemeContext.jsx";
import { playFetchProficiencyCatalog } from "../playApi.js";
import { GameCmdContext } from "./00-ctx.jsx";

const RESONANCE_TOTAL_CAP = 5000;
const LEAF_LEVEL_CAP = 200;

function formatWeights(w) {
  if (!w || typeof w !== "object") return "";
  const ranked = Object.entries(w)
    .map(([k, v]) => [String(k).toUpperCase(), Number(v)])
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (!ranked.length) return "";
  return ranked.map(([k, v]) => `${k} ${Math.round(v * 100)}%`).join(" · ");
}

function stateColor(st, T) {
  if (st === "lower") return T.glyph.amber;
  if (st === "lock") return T.text.muted;
  return T.glyph.emerald;
}

function barLabelShadow(T) {
  return `0 0 3px ${T.bg.void}, 0 0 6px ${T.bg.void}, 0 1px 2px rgba(0,0,0,0.65)`;
}

/**
 * Per-leaf rank vs 200 cap. Fill = current; labels inside track show level and ranks still needed to cap.
 * Optional peak tick when peak exceeds current (decay).
 */
function LeafLevelBar({ level, peak, T, height = 12, showPeakMarker = true, compact = false }) {
  const lv = Math.max(0, Math.min(LEAF_LEVEL_CAP, Number(level) || 0));
  const pk = Math.max(lv, Math.min(LEAF_LEVEL_CAP, Number(peak) || lv));
  const need = Math.max(0, LEAF_LEVEL_CAP - lv);
  const recover = pk > lv ? pk - lv : 0;
  const fillPct = LEAF_LEVEL_CAP > 0 ? (lv / LEAF_LEVEL_CAP) * 100 : 0;
  const peakPct = LEAF_LEVEL_CAP > 0 ? (pk / LEAF_LEVEL_CAP) * 100 : 0;
  const warn = lv > 0 && fillPct < 12;
  const fillColor = lv <= 0 ? T.text.muted : warn ? T.glyph.amber : T.glyph.violet;
  const trackH = Math.max(12, height);
  const tip =
    need > 0
      ? `Level ${lv} / ${LEAF_LEVEL_CAP} — need ${need} more to leaf cap${recover ? ` · recover ${recover} to peak ${pk}` : ""}`
      : `At leaf cap (${LEAF_LEVEL_CAP})${pk > lv ? ` · peak was ${pk}` : ""}`;
  return (
    <div
      style={{
        height: trackH,
        borderRadius: 3,
        background: T.bg.void,
        overflow: "hidden",
        border: `1px solid ${T.border.subtle}`,
        position: "relative",
      }}
      title={tip}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: `${fillPct}%`,
          borderRadius: 2,
          background:
            lv <= 0 ? "transparent" : `linear-gradient(90deg, ${fillColor}, ${String(fillColor)}cc)`,
          boxShadow: warn && lv > 0 ? `0 0 6px ${T.glyph.amber}50` : "none",
          transition: "width 0.35s ease",
        }}
      />
      {showPeakMarker && pk > lv ? (
        <div
          aria-hidden
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: `${peakPct}%`,
            width: 2,
            marginLeft: -1,
            background: T.text.muted,
            opacity: 0.95,
            pointerEvents: "none",
            boxShadow: `0 0 0 1px ${T.bg.void}`,
            zIndex: 1,
          }}
        />
      ) : null}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: compact ? "center" : "space-between",
          padding: compact ? "0 5px" : "0 7px",
          gap: 6,
          fontFamily: T.font.mono,
          fontSize: compact ? 7 : 8,
          lineHeight: 1,
          pointerEvents: "none",
          color: T.text.primary,
          textShadow: barLabelShadow(T),
          zIndex: 2,
        }}
      >
        {compact ? (
          <span style={{ fontWeight: 700, opacity: 0.95, textAlign: "center" }}>
            {need > 0 ? `${need} to cap` : "At cap"}
            {recover > 0 ? ` ·↓${recover}` : ""}
          </span>
        ) : (
          <>
            <span style={{ opacity: 0.92 }}>Lv {lv}</span>
            <span style={{ fontWeight: 700, opacity: 0.95, textAlign: "right" }}>
              {need > 0 ? `${need} to cap` : "At cap"}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

function ResonanceBar({ current, cap, T }) {
  const v = Math.max(0, Math.min(cap, Number(current) || 0));
  const left = Math.max(0, cap - v);
  const pct = cap > 0 ? (v / cap) * 100 : 0;
  const warn = pct > 85;
  const color = warn ? T.glyph.amber : T.glyph.violet;
  const h = 14;
  return (
    <div style={{ marginTop: 6 }}>
      <div
        style={{
          height: h,
          borderRadius: 3,
          background: T.bg.void,
          overflow: "hidden",
          border: `1px solid ${T.border.subtle}`,
          position: "relative",
        }}
        title={`${v.toLocaleString()} resonance used of ${cap.toLocaleString()} — ${left.toLocaleString()} headroom left`}
      >
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: `${pct}%`,
            borderRadius: 3,
            background: `linear-gradient(90deg, ${color}, ${String(color)}cc)`,
            transition: "width 0.4s ease",
          }}
        />
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 6px",
            fontFamily: T.font.mono,
            fontSize: 8,
            pointerEvents: "none",
            color: T.text.primary,
            textShadow: barLabelShadow(T),
            zIndex: 1,
          }}
        >
          <span style={{ opacity: 0.9 }}>{v.toLocaleString()} used</span>
          <span style={{ fontWeight: 700, opacity: 0.95 }}>{left.toLocaleString()} left</span>
        </div>
      </div>
    </div>
  );
}

/**
 * In-play proficiency browser: your levels vs full catalog, lore text, and MUD command hooks.
 */
export function ProficienciesPanel({ characterStats = null, resonanceLevelsTotal = null }) {
  const { T } = usePlayTheme();
  const { sendCommand } = useContext(GameCmdContext);
  const [tab, setTab] = useState("mine");
  const [domain, setDomain] = useState("");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [catErr, setCatErr] = useState(null);
  const [catLoading, setCatLoading] = useState(true);

  const profMap = characterStats?.conduit?.proficiencies;
  const profById = useMemo(() => (profMap && typeof profMap === "object" ? profMap : {}), [profMap]);

  const loadCatalog = useCallback(() => {
    setCatErr(null);
    setCatLoading(true);
    playFetchProficiencyCatalog()
      .then((data) => {
        const leaves = Array.isArray(data?.leaves) ? data.leaves : [];
        setCatalog({ leaves, domains: Array.isArray(data?.domains) ? data.domains : [] });
      })
      .catch((e) => {
        setCatalog(null);
        setCatErr(e?.message || "Could not load skill catalog");
      })
      .finally(() => setCatLoading(false));
  }, []);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  const leaves = catalog?.leaves || [];
  const byId = useMemo(() => {
    const m = new Map();
    for (const L of leaves) {
      if (L?.id) m.set(L.id, L);
    }
    return m;
  }, [leaves]);

  const selected = selectedId ? byId.get(selectedId) : null;
  const selectedRow = selectedId ? profById[selectedId] : null;
  const selectedLevel = selectedRow != null ? Number(selectedRow.level) || 0 : 0;
  const selectedPeak = selectedRow != null ? Number(selectedRow.peak) || selectedLevel : 0;
  const selectedState = (selectedRow?.state && String(selectedRow.state)) || "raise";

  const mineRows = useMemo(() => {
    const out = [];
    for (const L of leaves) {
      const row = profById[L.id];
      const lv = row != null ? Number(row.level) || 0 : 0;
      if (lv <= 0) continue;
      out.push({ leaf: L, row, lv });
    }
    out.sort((a, b) => b.lv - a.lv || a.leaf.id.localeCompare(b.leaf.id));
    return out;
  }, [leaves, profById]);

  const catalogFiltered = useMemo(() => {
    const needle = (q || "").trim().toLowerCase();
    return leaves.filter((L) => {
      if (domain && L.domain !== domain) return false;
      if (!needle) return true;
      const id = (L.id || "").toLowerCase();
      const name = (L.name || "").toLowerCase();
      const det = (L.detail || "").toLowerCase();
      return id.includes(needle) || name.includes(needle) || det.includes(needle);
    });
  }, [leaves, domain, q]);

  const resTotal =
    typeof resonanceLevelsTotal === "number" && !Number.isNaN(resonanceLevelsTotal)
      ? resonanceLevelsTotal
      : null;

  const micro = {
    fontSize: 8,
    fontFamily: T.font.body,
    color: T.text.muted,
    textTransform: "uppercase",
    letterSpacing: "0.09em",
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ flexShrink: 0, padding: "6px 8px", borderBottom: `1px solid ${T.border.subtle}` }}>
        <div style={{ ...micro, marginBottom: 4 }}>Resonance</div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
          <div style={{ fontSize: 12, fontFamily: T.font.mono, color: T.text.secondary }}>
            {resTotal != null ? (
              <>
                <span style={{ color: T.glyph.violet, fontWeight: 700 }}>{resTotal}</span>
                <span style={{ opacity: 0.45 }}> / {RESONANCE_TOTAL_CAP}</span>
              </>
            ) : (
              <span style={{ opacity: 0.7 }}>— sync after next snapshot</span>
            )}
          </div>
          {resTotal != null ? (
            <span style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted }}>
              {Math.round((resTotal / RESONANCE_TOTAL_CAP) * 1000) / 10}%
            </span>
          ) : null}
        </div>
        {resTotal != null ? <ResonanceBar current={resTotal} cap={RESONANCE_TOTAL_CAP} T={T} /> : null}
        <div style={{ fontSize: 9, color: T.text.muted, marginTop: 4, lineHeight: 1.35 }}>
          Levels accrue in play; each leaf caps at {LEAF_LEVEL_CAP}. Use story commands for detail:{" "}
          <code style={{ fontSize: 8, color: T.text.accent }}>prof</code>,{" "}
          <code style={{ fontSize: 8, color: T.text.accent }}>cap</code>,{" "}
          <code style={{ fontSize: 8, color: T.text.accent }}>bonus &lt;id&gt;</code>.
        </div>
      </div>

      <div style={{ display: "flex", borderBottom: `1px solid ${T.border.subtle}`, flexShrink: 0 }}>
        {[
          { id: "mine", label: "My skills" },
          { id: "catalog", label: "Catalog" },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            style={{
              flex: 1,
              padding: "6px 0",
              background: "none",
              border: "none",
              borderBottom: tab === t.id ? `2px solid ${T.glyph.violet}` : "2px solid transparent",
              color: tab === t.id ? T.text.accent : T.text.muted,
              fontFamily: T.font.body,
              fontSize: 9,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              cursor: "pointer",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {catLoading && !catErr ? (
        <div style={{ padding: 10, fontSize: 11, color: T.text.muted }}>Loading skill catalog…</div>
      ) : null}

      {catErr ? (
        <div style={{ padding: 8, fontSize: 11, color: T.text.danger, lineHeight: 1.4 }}>
          {catErr}
          <button
            type="button"
            onClick={loadCatalog}
            style={{
              display: "block",
              marginTop: 8,
              padding: "4px 10px",
              borderRadius: T.radius.sm,
              border: `1px solid ${T.border.medium}`,
              background: T.bg.surface,
              color: T.text.secondary,
              cursor: "pointer",
              fontSize: 10,
            }}
          >
            Retry
          </button>
        </div>
      ) : null}

      {!catErr && !catLoading && tab === "catalog" ? (
        <div style={{ flexShrink: 0, padding: "6px 8px", borderBottom: `1px solid ${T.border.subtle}` }}>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search id, name, description…"
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: "5px 8px",
              borderRadius: T.radius.sm,
              border: `1px solid ${T.border.subtle}`,
              background: T.bg.deep,
              color: T.text.primary,
              fontSize: 11,
              fontFamily: T.font.body,
              marginBottom: 6,
            }}
          />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, maxHeight: 52, overflowY: "auto" }}>
            <button
              type="button"
              onClick={() => setDomain("")}
              style={{
                padding: "2px 8px",
                borderRadius: T.radius.sm,
                border: `1px solid ${!domain ? T.glyph.violet : T.border.subtle}`,
                background: !domain ? `${T.glyph.violet}22` : T.bg.surface,
                color: !domain ? T.text.accent : T.text.muted,
                fontSize: 9,
                cursor: "pointer",
              }}
            >
              All
            </button>
            {(catalog?.domains || []).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDomain(d === domain ? "" : d)}
                style={{
                  padding: "2px 8px",
                  borderRadius: T.radius.sm,
                  border: `1px solid ${domain === d ? T.glyph.violet : T.border.subtle}`,
                  background: domain === d ? `${T.glyph.violet}22` : T.bg.surface,
                  color: domain === d ? T.text.accent : T.text.muted,
                  fontSize: 9,
                  cursor: "pointer",
                  textTransform: "capitalize",
                }}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div style={{ flex: 1, display: "flex", minHeight: 0, overflow: "hidden" }}>
        <div
          style={{
            flex: 1,
            minWidth: 0,
            overflowY: "auto",
            borderRight: selected ? `1px solid ${T.border.subtle}` : "none",
          }}
        >
          {!catErr && !catLoading && tab === "mine" && mineRows.length === 0 ? (
            <div style={{ padding: 10, fontSize: 11, color: T.text.muted, lineHeight: 1.45 }}>
              No proficiency ranks yet. Use skills in context (combat, fabrication, medicine, etc.) or seek training in
              the world; starter picks from chargen appear here once synced.
            </div>
          ) : null}
          {!catErr && !catLoading && tab === "mine"
            ? mineRows.map(({ leaf: L, row, lv }) => {
                const st = (row?.state && String(row.state)) || "raise";
                const pk = Number(row?.peak) || lv;
                const active = selectedId === L.id;
                return (
                  <button
                    key={L.id}
                    type="button"
                    onClick={() => setSelectedId(L.id)}
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      padding: "6px 8px",
                      border: "none",
                      borderBottom: `1px solid ${T.border.subtle}`,
                      background: active ? `${T.glyph.violet}18` : "transparent",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "baseline" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: T.text.primary, fontFamily: T.font.body }}>
                        {L.name || L.id}
                      </span>
                      <span style={{ fontSize: 11, fontFamily: T.font.mono, color: T.glyph.violet }}>{lv}</span>
                    </div>
                    <div style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted, marginTop: 2 }}>{L.id}</div>
                    <div style={{ fontSize: 9, color: stateColor(st, T), marginTop: 2 }}>
                      {st} · peak {pk}
                    </div>
                    <div style={{ marginTop: 5 }}>
                      <LeafLevelBar level={lv} peak={pk} T={T} height={12} compact />
                    </div>
                  </button>
                );
              })
            : null}
          {!catErr && !catLoading && tab === "catalog"
            ? catalogFiltered.map((L) => {
                const row = profById[L.id];
                const lv = row != null ? Number(row.level) || 0 : 0;
                const active = selectedId === L.id;
                return (
                  <button
                    key={L.id}
                    type="button"
                    onClick={() => setSelectedId(L.id)}
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      padding: "6px 8px",
                      border: "none",
                      borderBottom: `1px solid ${T.border.subtle}`,
                      background: active ? `${T.glyph.violet}18` : "transparent",
                      cursor: "pointer",
                      opacity: lv > 0 ? 1 : 0.72,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "baseline" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: T.text.primary }}>{L.name || L.id}</span>
                      <span
                        style={{
                          fontSize: 10,
                          fontFamily: T.font.mono,
                          color: lv > 0 ? T.glyph.violet : T.text.muted,
                        }}
                      >
                        {lv > 0 ? lv : "—"}
                      </span>
                    </div>
                    <div style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted, marginTop: 2 }}>{L.id}</div>
                    {lv > 0 ? (
                      <div style={{ marginTop: 5 }}>
                        <LeafLevelBar level={lv} peak={Number(row?.peak) || lv} T={T} height={12} compact />
                      </div>
                    ) : null}
                  </button>
                );
              })
            : null}
        </div>

        {selected ? (
          <div
            style={{
              width: "44%",
              minWidth: 140,
              maxWidth: 280,
              overflowY: "auto",
              padding: "8px 10px",
              background: T.bg.surface,
              flexShrink: 0,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 700, color: T.text.accent, fontFamily: T.font.display, marginBottom: 4 }}>
              {selected.name || selected.id}
            </div>
            <div style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted, marginBottom: 8, wordBreak: "break-all" }}>
              {selected.id}
            </div>
            <div style={{ fontSize: 10, color: T.text.secondary, lineHeight: 1.45, marginBottom: 8 }}>{selected.detail}</div>
            {formatWeights(selected.stat_weights) ? (
              <div style={{ fontSize: 9, color: T.text.muted, marginBottom: 8, lineHeight: 1.4 }}>
                <span style={{ ...micro, display: "block", marginBottom: 2 }}>Stat mix</span>
                {formatWeights(selected.stat_weights)}
              </div>
            ) : null}
            <div
              style={{
                fontSize: 10,
                padding: "6px 8px",
                borderRadius: T.radius.sm,
                background: T.bg.deep,
                border: `1px solid ${T.border.subtle}`,
                marginBottom: 10,
                lineHeight: 1.4,
                color: T.text.secondary,
              }}
            >
              <strong style={{ color: T.text.primary }}>Progress</strong>
              <div style={{ fontSize: 9, color: T.text.muted, marginTop: 4, marginBottom: 4, lineHeight: 1.35 }}>
                Violet fill = current ranks; text inside the track is how many ranks you can still add on this leaf
                before the {LEAF_LEVEL_CAP} ceiling.
              </div>
              <LeafLevelBar level={selectedLevel} peak={selectedPeak} T={T} height={15} />
              {selectedPeak > selectedLevel ? (
                <div style={{ fontSize: 8, color: T.text.muted, marginTop: 4, lineHeight: 1.35 }}>
                  Grey tick = historical peak {selectedPeak}. In compact lists, (↓N) means N ranks below that peak. State{" "}
                  <span style={{ color: stateColor(selectedState, T) }}>{selectedState}</span>.
                </div>
              ) : (
                <div style={{ fontSize: 8, color: T.text.muted, marginTop: 4 }}>
                  State <span style={{ color: stateColor(selectedState, T) }}>{selectedState}</span> · Peak {selectedPeak}
                </div>
              )}
            {selectedLevel <= 0 ? (
                <div style={{ marginTop: 6, fontSize: 9, color: T.text.muted }}>
                  You do not have ranks here yet. Read the description above, then pursue the matching activity or
                  training in-character; the world may offer teachers, archives, or contracts.
                </div>
              ) : null}
            </div>
            <div style={{ ...micro, marginBottom: 4 }}>Story commands</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <button
                type="button"
                onClick={() => sendCommand(`bonus ${selected.id}`)}
                style={cmdBtn(T)}
              >
                bonus (math breakdown)
              </button>
              <button type="button" onClick={() => sendCommand(`raise ${selected.id}`)} style={cmdBtn(T)}>
                raise — allow gains
              </button>
              <button type="button" onClick={() => sendCommand(`lower ${selected.id}`)} style={cmdBtn(T)}>
                lower — decay-eligible over cap
              </button>
              <button type="button" onClick={() => sendCommand(`lock ${selected.id}`)} style={cmdBtn(T)}>
                lock — no field gains
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function cmdBtn(T) {
  return {
    padding: "5px 8px",
    borderRadius: T.radius.sm,
    border: `1px solid ${T.border.medium}`,
    background: T.bg.deep,
    color: T.text.secondary,
    fontSize: 10,
    fontFamily: T.font.body,
    textAlign: "left",
    cursor: "pointer",
  };
}
