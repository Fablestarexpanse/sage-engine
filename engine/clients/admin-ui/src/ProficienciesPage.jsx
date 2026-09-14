import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";

const WEIGHT_KEYS = ["FRT", "RFX", "ACU", "RSV", "PRS"];

function emptyLeaf() {
  return {
    id: "domain.branch.new_skill",
    name: "",
    description: "",
    domain: "domain",
    stat_weights: { FRT: 0.2, RFX: 0.2, ACU: 0.2, RSV: 0.2, PRS: 0.2 },
    tree_depth: 0,
    tags: [],
  };
}

function weightSum(w) {
  if (!w || typeof w !== "object") return 0;
  return WEIGHT_KEYS.reduce((a, k) => a + (Number(w[k]) || 0), 0);
}

export default function ProficienciesPage() {
  const { colors: COLORS } = useAdminTheme();
  const [doc, setDoc] = useState(null);
  const [loadErr, setLoadErr] = useState("");
  const [saveMsg, setSaveMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [domain, setDomain] = useState("");
  const [sel, setSel] = useState(null);

  const load = useCallback(async () => {
    setLoadErr("");
    setSaveMsg("");
    try {
      const { data } = await axios.get(`${API_BASE}/content/proficiencies/catalog`);
      setDoc(data);
      setSel(null);
    } catch (e) {
      setDoc(null);
      setLoadErr(e.response?.data?.detail || e.message || "Load failed");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const domains = useMemo(() => {
    const leaves = doc?.leaves;
    if (!Array.isArray(leaves)) return [];
    const s = new Set();
    for (const L of leaves) {
      const d = L?.domain || (typeof L?.id === "string" ? L.id.split(".")[0] : "");
      if (d) s.add(d);
    }
    return [...s].sort();
  }, [doc]);

  const filtered = useMemo(() => {
    const leaves = doc?.leaves;
    if (!Array.isArray(leaves)) return [];
    const needle = (q || "").trim().toLowerCase();
    return leaves
      .map((L, i) => ({ L, i }))
      .filter(({ L }) => {
        if (domain && L.domain !== domain) return false;
        if (!needle) return true;
        const id = (L.id || "").toLowerCase();
        const name = (L.name || "").toLowerCase();
        const desc = (L.description || "").toLowerCase();
        return id.includes(needle) || name.includes(needle) || desc.includes(needle);
      });
  }, [doc, domain, q]);

  const selectedLeaf = sel != null && doc?.leaves?.[sel] != null ? doc.leaves[sel] : null;

  const updateLeaf = (idx, patch) => {
    setDoc((d) => {
      if (!d?.leaves) return d;
      const leaves = [...d.leaves];
      leaves[idx] = { ...leaves[idx], ...patch };
      return { ...d, leaves };
    });
  };

  const updateWeights = (idx, key, val) => {
    const n = val === "" ? 0 : Number(val);
    setDoc((d) => {
      if (!d?.leaves) return d;
      const leaves = [...d.leaves];
      const row = { ...(leaves[idx] || {}) };
      const w = { ...(row.stat_weights || {}) };
      w[key] = Number.isFinite(n) ? n : 0;
      row.stat_weights = w;
      leaves[idx] = row;
      return { ...d, leaves };
    });
  };

  const save = async () => {
    if (!doc) return;
    setBusy(true);
    setSaveMsg("");
    try {
      const { data } = await axios.put(`${API_BASE}/content/proficiencies/catalog`, doc);
      setSaveMsg(`Saved ${data.leaf_count} leaves. Reload game content cache if players are online.`);
      await load();
    } catch (e) {
      const d = e.response?.data?.detail;
      setSaveMsg(typeof d === "string" ? d : JSON.stringify(d || e.message));
    } finally {
      setBusy(false);
    }
  };

  const addLeaf = () => {
    let newIdx = 0;
    setDoc((d) => {
      const leaves = [...(d?.leaves || []), emptyLeaf()];
      newIdx = leaves.length - 1;
      return { ...(d || { version: 1 }), version: d?.version ?? 1, leaves };
    });
    setSel(newIdx);
  };

  const removeSelected = () => {
    if (sel == null || !doc?.leaves) return;
    if (!window.confirm(`Remove leaf ${doc.leaves[sel]?.id || sel}?`)) return;
    setDoc((d) => {
      const leaves = [...(d.leaves || [])];
      leaves.splice(sel, 1);
      return { ...d, leaves };
    });
    setSel(null);
  };

  const inputStyle = {
    padding: 8,
    background: COLORS.bgInput,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 6,
    color: COLORS.text,
    width: "100%",
    boxSizing: "border-box",
  };

  return (
    <div style={{ maxWidth: 1200 }}>
      <h2 style={{ margin: "0 0 8px", fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>
        Skills catalog
      </h2>
      <p style={{ margin: "0 0 16px", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.45 }}>
        Edit <code style={{ color: COLORS.textDim }}>content/proficiencies/catalog.json</code> from here. Saves are validated (unique ids, domain matches id root, stat weights sum to ~1 when non-empty).
        After saving, use <strong>Server → Reload content cache</strong> or restart Nexus so players pick up changes. Optional display copy in{" "}
        <code style={{ color: COLORS.textDim }}>content/proficiencies/leaf_descriptions.json</code> is separate from this file.
      </p>

      {loadErr ? <div style={{ color: COLORS.danger, marginBottom: 12 }}>{loadErr}</div> : null}
      {saveMsg ? (
        <div
          style={{
            marginBottom: 12,
            padding: 10,
            borderRadius: 8,
            background: saveMsg.startsWith("Saved") ? `${COLORS.success}18` : `${COLORS.warning}18`,
            color: COLORS.text,
            fontSize: 12,
            whiteSpace: "pre-wrap",
          }}
        >
          {saveMsg}
        </div>
      ) : null}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
        <button
          type="button"
          onClick={load}
          disabled={busy}
          style={{ padding: "8px 14px", background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, cursor: "pointer" }}
        >
          Reload
        </button>
        <button
          type="button"
          onClick={save}
          disabled={busy || !doc}
          style={{ padding: "8px 14px", background: COLORS.accent, border: "none", borderRadius: 6, color: "#fff", fontWeight: 600, cursor: busy ? "wait" : "pointer" }}
        >
          {busy ? "Saving…" : "Save catalog"}
        </button>
        <button
          type="button"
          onClick={addLeaf}
          disabled={busy || !doc}
          style={{ padding: "8px 14px", background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, cursor: "pointer" }}
        >
          Add leaf
        </button>
        <button
          type="button"
          onClick={removeSelected}
          disabled={busy || sel == null}
          style={{ padding: "8px 14px", background: COLORS.bgCard, border: `1px solid ${COLORS.danger}`, borderRadius: 6, color: COLORS.danger, cursor: "pointer" }}
        >
          Delete selected
        </button>
        {doc ? (
          <span style={{ fontSize: 12, color: COLORS.textMuted, alignSelf: "center" }}>
            {doc.leaves?.length ?? 0} leaves · v{doc.version ?? 1}
          </span>
        ) : null}
      </div>

      {!doc ? null : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 1fr) minmax(360px, 1.1fr)", gap: 16, alignItems: "start" }}>
          <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 12, minHeight: 360 }}>
            <input
              placeholder="Search id, name, description…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ ...inputStyle, marginBottom: 8 }}
            />
            <select value={domain} onChange={(e) => setDomain(e.target.value)} style={{ ...inputStyle, marginBottom: 8 }}>
              <option value="">All domains</option>
              {domains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            <div style={{ maxHeight: 480, overflowY: "auto", borderRadius: 6, border: `1px solid ${COLORS.border}` }}>
              {filtered.map(({ L, i }) => {
                const active = sel === i;
                const ws = weightSum(L.stat_weights);
                const okW = ws <= 0.01 || Math.abs(ws - 1) <= 0.03;
                return (
                  <button
                    key={`${L.id}-${i}`}
                    type="button"
                    onClick={() => setSel(i)}
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      padding: "8px 10px",
                      border: "none",
                      borderBottom: `1px solid ${COLORS.border}`,
                    background: active ? COLORS.accentGlow : "transparent",
                    color: COLORS.text,
                    cursor: "pointer",
                    fontSize: 12,
                  }}
                  >
                    <div style={{ fontWeight: 600 }}>{L.name?.trim() || L.id}</div>
                    <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{L.id}</div>
                    <div style={{ fontSize: 9, color: okW ? COLORS.textMuted : COLORS.warning }}>weights Σ={ws.toFixed(2)}</div>
                  </button>
                );
              })}
            </div>
          </div>

          <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 14 }}>
            {!selectedLeaf ? (
              <div style={{ color: COLORS.textMuted, fontSize: 13 }}>Select a leaf to edit, or use Add leaf.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label style={{ fontSize: 11, color: COLORS.textMuted }}>
                  id
                  <input
                    style={{ ...inputStyle, marginTop: 4 }}
                    value={selectedLeaf.id || ""}
                    onChange={(e) => updateLeaf(sel, { id: e.target.value.trim() })}
                  />
                </label>
                <label style={{ fontSize: 11, color: COLORS.textMuted }}>
                  domain (must match first segment of id)
                  <input
                    style={{ ...inputStyle, marginTop: 4 }}
                    value={selectedLeaf.domain || ""}
                    onChange={(e) => updateLeaf(sel, { domain: e.target.value.trim() })}
                  />
                </label>
                <label style={{ fontSize: 11, color: COLORS.textMuted }}>
                  name
                  <input
                    style={{ ...inputStyle, marginTop: 4 }}
                    value={selectedLeaf.name || ""}
                    onChange={(e) => updateLeaf(sel, { name: e.target.value })}
                  />
                </label>
                <label style={{ fontSize: 11, color: COLORS.textMuted }}>
                  description
                  <textarea
                    style={{ ...inputStyle, marginTop: 4, minHeight: 100, resize: "vertical" }}
                    value={selectedLeaf.description || ""}
                    onChange={(e) => updateLeaf(sel, { description: e.target.value })}
                  />
                </label>
                <label style={{ fontSize: 11, color: COLORS.textMuted }}>
                  tree_depth (0 = auto from id; else 1–4)
                  <input
                    type="number"
                    min={0}
                    max={4}
                    style={{ ...inputStyle, marginTop: 4, maxWidth: 120 }}
                    value={selectedLeaf.tree_depth ?? 0}
                    onChange={(e) => updateLeaf(sel, { tree_depth: parseInt(e.target.value, 10) || 0 })}
                  />
                </label>
                <label style={{ fontSize: 11, color: COLORS.textMuted }}>
                  tags (comma-separated)
                  <input
                    style={{ ...inputStyle, marginTop: 4 }}
                    value={(selectedLeaf.tags || []).join(", ")}
                    onChange={(e) =>
                      updateLeaf(sel, {
                        tags: e.target.value
                          .split(",")
                          .map((t) => t.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </label>
                <div>
                  <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 4 }}>stat_weights (sum ≈ 1.0)</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 6 }}>
                    {WEIGHT_KEYS.map((k) => (
                      <label key={k} style={{ fontSize: 10, color: COLORS.textDim }}>
                        {k}
                        <input
                          type="number"
                          step="0.05"
                          min={0}
                          max={1}
                          style={{ ...inputStyle, marginTop: 2 }}
                          value={selectedLeaf.stat_weights?.[k] ?? ""}
                          onChange={(e) => updateWeights(sel, k, e.target.value)}
                        />
                      </label>
                    ))}
                  </div>
                  <div style={{ fontSize: 11, marginTop: 4, color: Math.abs(weightSum(selectedLeaf.stat_weights) - 1) <= 0.03 || weightSum(selectedLeaf.stat_weights) <= 0.01 ? COLORS.textMuted : COLORS.warning }}>
                    Sum: {weightSum(selectedLeaf.stat_weights).toFixed(3)}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
