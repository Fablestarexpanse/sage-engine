import { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { useHashParts } from "../listHooks.js";
import { Badge, ActionButton, SearchBar, FetchErrorBanner } from "../adminCommon.jsx";

// Keys most operators look for first; everything else is one search away.
const FEATURED = ["login.banner", "login.motd", "onboarding.new_player", "prompt"];

const LexiconPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [world, setWorld] = useState("");
  const [rows, setRows] = useState([]);
  const [loadErr, setLoadErr] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    setLoadErr("");
    try {
      const { data } = await axios.get(`${API_BASE}/admin/lexicon`);
      setWorld(data.world);
      setRows(data.keys);
    } catch (e) {
      setLoadErr(e.response?.data?.detail || e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const open = useCallback(async (row) => {
    setSelected(row);
    setDraft(row.value ?? "");
    setNote("");
    setStatus("");
    try {
      const { data } = await axios.get(`${API_BASE}/admin/lexicon/${encodeURIComponent(row.key)}/history`);
      setHistory(data.versions);
    } catch {
      setHistory([]);
    }
  }, []);

  // #/lexicon/<key> (from search) opens that line.
  const [hashParts] = useHashParts();
  const linkedKey = hashParts[0];
  useEffect(() => {
    const row = linkedKey && rows.find((r) => r.key === linkedKey);
    if (!row || selected?.key === linkedKey) return;
    Promise.resolve().then(() => { setQuery(linkedKey); open(row); });
  }, [linkedKey, rows, selected?.key, open]);

  const refreshSelected = async (key) => {
    const { data } = await axios.get(`${API_BASE}/admin/lexicon`);
    setRows(data.keys);
    const row = data.keys.find((r) => r.key === key);
    if (row) await open(row);
  };

  const run = async (label, fn) => {
    setBusy(true);
    try {
      await fn();
      await refreshSelected(selected.key);
      setStatus(label);
    } catch (ex) {
      setStatus(`Not saved: ${ex.response?.data?.detail || ex.message}`);
    } finally {
      setBusy(false);
    }
  };

  const save = () => run("Saved and live — players see it now.", () =>
    axios.put(`${API_BASE}/admin/lexicon/${encodeURIComponent(selected.key)}`, { value: draft, note: note || null }));
  const rollback = (version) => run(`Rolled back to version ${version}.`, () =>
    axios.post(`${API_BASE}/admin/lexicon/${encodeURIComponent(selected.key)}/rollback`, { version }));
  const revert = () => run("Reverted to the world package text.", () =>
    axios.delete(`${API_BASE}/admin/lexicon/${encodeURIComponent(selected.key)}`));

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? rows.filter((r) => r.key.toLowerCase().includes(q) || (r.value || "").toLowerCase().includes(q))
      : rows;
    return [...filtered].sort((a, b) => {
      const fa = FEATURED.indexOf(a.key), fb = FEATURED.indexOf(b.key);
      if (fa !== -1 || fb !== -1) return (fa === -1 ? 99 : fa) - (fb === -1 ? 99 : fb);
      return a.key.localeCompare(b.key);
    });
  }, [rows, query]);

  const card = { background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10 };
  const sourceColor = (s) => (s === "override" ? COLORS.warning : s === "world" ? COLORS.accent : COLORS.textDim);

  return (
    <div style={{ maxWidth: 1180 }}>
      <h2 style={{ margin: "0 0 8px", fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Lexicon &amp; MOTD</h2>
      <p style={{ margin: "0 0 16px", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", maxWidth: 760 }}>
        Every player-facing line in <strong>{world || "this world"}</strong>. Edits go live immediately and are kept as
        versions, so any change can be rolled back. <em>Revert</em> returns a line to the text shipped in the world package.
        Placeholders like <code style={{ color: COLORS.textDim }}>{"{name}"}</code> are filled in by the game.
      </p>
      <FetchErrorBanner error={loadErr} onRetry={load} />

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.1fr)", gap: 16, alignItems: "start" }}>
        <div style={{ ...card, overflow: "hidden" }}>
          <div style={{ padding: 12, borderBottom: `1px solid ${COLORS.border}` }}>
            <SearchBar value={query} onChange={setQuery} placeholder="Search keys or text…" />
          </div>
          <div style={{ maxHeight: 620, overflowY: "auto" }}>
            {visible.map((r) => (
              <button
                key={r.key}
                type="button"
                onClick={() => open(r)}
                style={{
                  display: "block", width: "100%", textAlign: "left", padding: "10px 14px", border: "none",
                  borderBottom: `1px solid ${COLORS.border}`, cursor: "pointer",
                  background: selected?.key === r.key ? COLORS.bgInput : "transparent", color: COLORS.text,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                  <code style={{ fontSize: 12, color: COLORS.text }}>{r.key}</code>
                  <Badge color={sourceColor(r.source)}>{r.source}</Badge>
                </div>
                <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {r.value ? r.value.replace(/\r?\n/g, " ⏎ ") : <em>(empty)</em>}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div style={{ ...card, padding: 18 }}>
          {!selected ? (
            <p style={{ margin: 0, color: COLORS.textMuted, fontSize: 13 }}>Pick a line on the left to edit it. The login banner and MOTD are at the top.</p>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <code style={{ fontSize: 14, color: COLORS.text }}>{selected.key}</code>
                <Badge color={sourceColor(selected.source)}>{selected.overridden ? "edited live" : `from ${selected.source}`}</Badge>
              </div>
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={6}
                style={{ width: "100%", boxSizing: "border-box", padding: 10, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}
              />
              <input
                placeholder="Note for the history (optional)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                style={{ padding: 8, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }}
              />
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <ActionButton onClick={save} disabled={busy || draft === selected.value}>Save and apply</ActionButton>
                {selected.overridden && (
                  <ActionButton variant="ghost" onClick={revert} disabled={busy}>Revert to package text</ActionButton>
                )}
                {status && <span style={{ fontSize: 12, color: COLORS.textMuted }}>{status}</span>}
              </div>
              <div style={{ fontSize: 12, color: COLORS.textDim }}>
                Package text ({selected.default_source}): <span style={{ color: COLORS.textMuted }}>{selected.default || <em>(empty)</em>}</span>
              </div>

              <h3 style={{ margin: "8px 0 0", fontSize: 12, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>History</h3>
              {history.length === 0 ? (
                <p style={{ margin: 0, fontSize: 12, color: COLORS.textDim }}>Never edited live.</p>
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {history.map((h) => (
                    <div key={h.version} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 6, padding: 10 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, color: COLORS.textMuted }}>
                        <span>v{h.version} · {h.created_at?.replace("T", " ").slice(0, 16)}{h.note ? ` · ${h.note}` : ""}</span>
                        {h.active ? (
                          <Badge color={COLORS.success}>live</Badge>
                        ) : (
                          <ActionButton small variant="ghost" onClick={() => rollback(h.version)} disabled={busy}>Roll back to this</ActionButton>
                        )}
                      </div>
                      <div style={{ fontSize: 12, color: COLORS.text, marginTop: 6, whiteSpace: "pre-wrap" }}>{String(h.value)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LexiconPage;
