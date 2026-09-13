import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";

/** Agents admin — watch list, detail drawer (feelings/inventory/POV), actions, persona editor. */

const fmtAgo = (ts) => {
  if (!ts) return "—";
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  return s < 60 ? `${s}s ago` : `${Math.round(s / 60)}m ago`;
};

function Bar({ label, val }) {
  const { colors: COLORS } = useAdminTheme();
  const pct = Math.round(Math.max(0, Math.min(1, val ?? 0)) * 100);
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: COLORS.textMuted }}>
        <span>{label}</span><span>{pct}%</span>
      </div>
      <div style={{ height: 4, background: COLORS.bgInput, borderRadius: 2 }}>
        <div style={{ height: "100%", width: `${pct}%`, background: COLORS.accent, borderRadius: 2 }} />
      </div>
    </div>
  );
}

function BrainPanel() {
  const { colors: COLORS } = useAdminTheme();
  const [cfg, setCfg] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API_BASE}/admin/agents-llm`);
      setCfg(r.data);
    } catch (e) {
      setMsg(e.response?.data?.detail || e.message || "brain API failed");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (patch) => {
    setBusy(true);
    setMsg("");
    try {
      const r = await axios.put(`${API_BASE}/admin/agents-llm`, patch);
      setCfg(r.data);
      setMsg("Saved — applied live.");
    } catch (e) {
      setMsg(String(e.response?.data?.detail || e.message || "Save failed"));
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setBusy(true);
    setTestResult(null);
    try {
      const r = await axios.post(`${API_BASE}/admin/agents-llm/test`);
      setTestResult(r.data);
    } catch (e) {
      setTestResult({ ok: false, error: e.response?.data?.detail || e.message });
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return null;
  const inp = { width: "100%", boxSizing: "border-box", padding: "5px 8px", fontSize: 11, fontFamily: "monospace", background: COLORS.bgInput, color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 6 };
  const lbl = { fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", margin: "8px 0 3px" };
  const btn = { padding: "5px 10px", fontSize: 11, borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bgCard, color: COLORS.text, cursor: "pointer" };
  const embedded = cfg.backend === "embedded";

  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 12, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
        <span style={{ fontWeight: 700, fontSize: 13, color: COLORS.text }}>Agent Brain (LLM)</span>
        <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: COLORS.text }}>
          <input type="checkbox" checked={!!cfg.enabled} disabled={busy}
            onChange={(e) => save({ enabled: e.target.checked })} />
          enabled
        </label>
        <select value={cfg.backend} disabled={busy} style={{ ...inp, width: 130 }}
          onChange={(e) => save({ primary_backend: e.target.value })}>
          <option value="embedded">embedded (in-server)</option>
          <option value="lm_studio">LM Studio</option>
          <option value="ollama">Ollama</option>
        </select>
        <button type="button" style={btn} disabled={busy} onClick={runTest}>Test brain</button>
        {msg && <span style={{ fontSize: 10, color: COLORS.textMuted }}>{msg}</span>}
      </div>
      {embedded ? (
        <>
          <span style={lbl}>GGUF model path (relative to server root)</span>
          <input style={inp} defaultValue={cfg.model_path} key={`mp-${cfg.model_path}`}
            onBlur={(e) => e.target.value !== cfg.model_path && save({ model_path: e.target.value })} />
          <div style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 4 }}>
            {cfg.embedded?.model_file_exists
              ? (cfg.embedded?.loaded ? "Model loaded." : "Model file found — loads on first use.")
              : "Model file not found. Drop a small instruct GGUF (e.g. Qwen 2.5 3B Q4) into models/ and set the path."}
            {cfg.embedded?.load_error && <span style={{ color: COLORS.danger }}> Load error: {cfg.embedded.load_error}</span>}
          </div>
        </>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 8 }}>
          <div>
            <span style={lbl}>{cfg.backend === "ollama" ? "Ollama URL" : "LM Studio URL"}</span>
            <input style={inp} defaultValue={cfg.backend === "ollama" ? cfg.ollama_url : cfg.lm_studio_url}
              key={`url-${cfg.backend}`}
              onBlur={(e) => save(cfg.backend === "ollama" ? { ollama_url: e.target.value } : { lm_studio_url: e.target.value })} />
          </div>
          <div>
            <span style={lbl}>Model id</span>
            <input style={inp} defaultValue={cfg.chat_model} key={`cm-${cfg.chat_model}`}
              onBlur={(e) => e.target.value !== cfg.chat_model && save({ chat_model: e.target.value })} />
          </div>
        </div>
      )}
      {testResult && (
        <div style={{ marginTop: 8, fontSize: 11, fontFamily: "monospace", color: testResult.ok ? COLORS.success : COLORS.danger }}>
          {testResult.ok
            ? `✓ ${testResult.latency_s}s — "${testResult.reply}"`
            : `✗ ${testResult.error}`}
        </div>
      )}
    </div>
  );
}

function ProgressChart({ progress }) {
  const { colors: COLORS } = useAdminTheme();
  const pts = Array.isArray(progress) ? progress : [];
  if (pts.length < 2) {
    return (
      <div style={{ fontSize: 10, color: COLORS.textMuted }}>
        Progression chart appears after a few minutes of play (sampled every ~60s).
      </div>
    );
  }
  const W = 320;
  const H = 70;
  const series = [
    { key: "levels", color: COLORS.accent, label: "levels" },
    { key: "kills", color: COLORS.danger, label: "kills" },
    { key: "goals", color: COLORS.success, label: "goals" },
    { key: "rooms", color: COLORS.info, label: "rooms" },
  ];
  const t0 = pts[0].t;
  const t1 = pts[pts.length - 1].t || t0 + 1;
  const x = (t) => ((t - t0) / Math.max(1, t1 - t0)) * (W - 8) + 4;
  const line = (key) => {
    const maxV = Math.max(1, ...pts.map((p) => Number(p[key]) || 0));
    return pts.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${(H - 6 - ((Number(p[key]) || 0) / maxV) * (H - 14)).toFixed(1)}`).join(" ");
  };
  const last = pts[pts.length - 1];
  const spanMin = Math.max(1, Math.round((t1 - t0) / 60));
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, background: COLORS.bgInput, borderRadius: 6 }}>
        {series.map((s) => <path key={s.key} d={line(s.key)} fill="none" stroke={s.color} strokeWidth="1.5" />)}
      </svg>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", fontSize: 10, color: COLORS.textMuted, marginTop: 3 }}>
        <span>last {spanMin}m</span>
        {series.map((s) => (
          <span key={s.key}><span style={{ color: s.color }}>■</span> {s.label} {last[s.key] ?? 0}</span>
        ))}
      </div>
    </div>
  );
}

function StatBoard() {
  const { colors: COLORS } = useAdminTheme();
  const [board, setBoard] = useState(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${API_BASE}/admin/agents-statboard`);
      setBoard(r.data);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || e.message || "statboard API failed");
    }
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  const cell = { padding: "6px 10px", fontSize: 12, color: COLORS.text, borderBottom: `1px solid ${COLORS.border}`, whiteSpace: "nowrap" };
  const th = { ...cell, color: COLORS.textMuted, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left" };
  const rows = board?.rows ?? [];
  // Fixed interesting columns first, then any extra counters new systems add
  // (trades, rentals, ...) appear automatically.
  const known = ["kills", "deaths", "goals_completed", "items_used", "rooms_visited"];
  const extra = (board?.counter_keys ?? []).filter((k) => !known.includes(k));
  const sum = (key) => rows.reduce((a, r) => a + (Number(r[key] ?? r.counters?.[key]) || 0), 0);

  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
      <div style={{ padding: "10px 12px", fontWeight: 700, fontSize: 13, color: COLORS.text, borderBottom: `1px solid ${COLORS.border}` }}>
        Stat board {error && <span style={{ color: COLORS.danger, fontWeight: 400, marginLeft: 8 }}>{error}</span>}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>
            <th style={th}>Name</th><th style={th}>Room</th><th style={th}>HP</th><th style={th}>Mood</th>
            <th style={th} title="Total proficiency levels">Levels</th>
            <th style={th}>Kills</th><th style={th}>Deaths</th>
            <th style={th}>Goals</th><th style={th}>Items used</th>
            <th style={th}>Most used</th><th style={th}>Top prey</th>
            <th style={th}>Rooms</th><th style={th}>Achievements</th><th style={th}>Memories</th>
            {extra.map((k) => <th key={k} style={th}>{k.replace(/_/g, " ")}</th>)}
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td style={cell}>{r.name}</td>
                <td style={cell}>{r.room_id ? r.room_id.split(":")[1] : "—"}</td>
                <td style={cell}>{r.hp != null ? `${r.hp}/${r.max_hp}` : "—"}</td>
                <td style={cell}>{r.mood ?? "—"}</td>
                <td style={cell}>{r.levels}</td>
                <td style={cell}>{r.kills}</td>
                <td style={cell}>{r.deaths}</td>
                <td style={cell}>{r.goals_completed}</td>
                <td style={cell}>{r.items_used}</td>
                <td style={cell}>{r.most_used_item ?? "—"}</td>
                <td style={cell}>{r.top_prey ? `${r.top_prey} (${r.top_prey_kills})` : "—"}</td>
                <td style={cell}>{r.rooms_visited}</td>
                <td style={cell} title={(r.achievements ?? []).join(", ")}>{(r.achievements ?? []).length}</td>
                <td style={cell}>{r.memories_count}</td>
                {extra.map((k) => <td key={k} style={cell}>{r.counters?.[k] ?? 0}</td>)}
              </tr>
            ))}
            {rows.length > 1 && (
              <tr style={{ background: COLORS.bgInput }}>
                <td style={{ ...cell, fontWeight: 700 }}>All agents</td>
                <td style={cell} colSpan={3}></td>
                <td style={{ ...cell, fontWeight: 700 }}>{sum("levels")}</td>
                <td style={{ ...cell, fontWeight: 700 }}>{sum("kills")}</td>
                <td style={{ ...cell, fontWeight: 700 }}>{sum("deaths")}</td>
                <td style={{ ...cell, fontWeight: 700 }}>{sum("goals_completed")}</td>
                <td style={{ ...cell, fontWeight: 700 }}>{sum("items_used")}</td>
                <td style={cell} colSpan={2}></td>
                <td style={{ ...cell, fontWeight: 700 }}>{sum("rooms_visited")}</td>
                <td style={{ ...cell, fontWeight: 700 }}>{rows.reduce((a, r) => a + (r.achievements?.length || 0), 0)}</td>
                <td style={{ ...cell, fontWeight: 700 }}>{sum("memories_count")}</td>
                {extra.map((k) => <td key={k} style={{ ...cell, fontWeight: 700 }}>{sum(k)}</td>)}
              </tr>
            )}
            {!rows.length && <tr><td style={cell} colSpan={14}>No agents running.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function AgentsTab() {
  const { colors: COLORS } = useAdminTheme();
  const [view, setView] = useState("watch");
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [pov, setPov] = useState([]);
  const [personaText, setPersonaText] = useState("");
  const [personaMsg, setPersonaMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${API_BASE}/admin/agents`);
      setRows(Array.isArray(r.data) ? r.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || e.message || "agents API failed");
    }
  }, []);

  const loadDetail = useCallback(async (id) => {
    if (!id) return;
    try {
      const [d, p, y] = await Promise.all([
        axios.get(`${API_BASE}/admin/agents/${encodeURIComponent(id)}`).catch(() => null),
        axios.get(`${API_BASE}/admin/agents/${encodeURIComponent(id)}/pov`).catch(() => null),
        axios.get(`${API_BASE}/admin/agents/${encodeURIComponent(id)}/persona`).catch(() => null),
      ]);
      setDetail(d?.data ?? null);
      setPov(p?.data?.pov ?? []);
      if (y?.data?.yaml_text != null) setPersonaText(y.data.yaml_text);
    } catch {
      /* detail best-effort */
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) return undefined;
    loadDetail(selectedId);
    const t = setInterval(() => loadDetail(selectedId), 5000);
    return () => clearInterval(t);
  }, [selectedId, loadDetail]);

  const act = async (id, action, body) => {
    setBusy(true);
    try {
      await axios.post(`${API_BASE}/admin/agents/${encodeURIComponent(id)}/${action}`, body ?? {});
      await refresh();
      await loadDetail(id);
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message || "Failed");
    } finally {
      setBusy(false);
    }
  };

  const savePersona = async () => {
    if (!selectedId) return;
    setBusy(true);
    setPersonaMsg("");
    try {
      const r = await axios.put(`${API_BASE}/admin/agents/${encodeURIComponent(selectedId)}/persona`, {
        yaml_text: personaText,
      });
      setPersonaMsg(r.data?.applies === "on_restart" ? "Saved — restart the agent to apply." : "Saved.");
    } catch (e) {
      setPersonaMsg(String(e.response?.data?.detail || e.message || "Save failed"));
    } finally {
      setBusy(false);
    }
  };

  const teleport = (id) => {
    const room = window.prompt("Teleport to room id (zone:slug):", "test_isle:town_plaza");
    if (room) act(id, "teleport", { room_id: room });
  };
  const give = (id) => {
    const item = window.prompt("Item template id to grant (blank = set stat instead):", "ration_pack");
    if (item) return act(id, "give", { item_template: item, count: 1 });
    const stat = window.prompt("Stat name:", "hp");
    if (!stat) return undefined;
    const value = Number(window.prompt("Value:", "100"));
    if (!Number.isNaN(value)) act(id, "give", { stat, value });
    return undefined;
  };

  const cell = { padding: "6px 10px", fontSize: 12, color: COLORS.text, borderBottom: `1px solid ${COLORS.border}` };
  const th = { ...cell, color: COLORS.textMuted, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left" };
  const btn = { padding: "4px 8px", fontSize: 11, borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bgCard, color: COLORS.text, cursor: "pointer" };

  const viewBtn = (id, label) => (
    <button type="button" onClick={() => setView(id)}
      style={{ ...btn, background: view === id ? COLORS.bgInput : COLORS.bgCard, fontWeight: view === id ? 700 : 400 }}>
      {label}
    </button>
  );

  return (
    <div>
    <BrainPanel />
    <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
      {viewBtn("watch", "Watch")}
      {viewBtn("stats", "Stat board")}
    </div>
    {view === "stats" ? <StatBoard /> : (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(420px, 1fr) minmax(360px, 1fr)", gap: 16, alignItems: "start" }}>
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <div style={{ padding: "10px 12px", fontWeight: 700, fontSize: 13, color: COLORS.text, borderBottom: `1px solid ${COLORS.border}` }}>
          Agents {error && <span style={{ color: COLORS.danger, fontWeight: 400, marginLeft: 8 }}>{error}</span>}
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>
            <th style={th}>Name</th><th style={th}>Room</th><th style={th}>HP</th>
            <th style={th}>Mood</th><th style={th} title="Total proficiency levels">Lv</th>
            <th style={th} title="Kills / Deaths">K/D</th>
            <th style={th}>Last action</th><th style={th}></th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}
                onClick={() => setSelectedId(r.id)}
                style={{ cursor: "pointer", background: selectedId === r.id ? COLORS.bgInput : "transparent", opacity: r.enabled ? 1 : 0.5 }}>
                <td style={cell}>{r.name}</td>
                <td style={cell}>{r.room_id ? r.room_id.split(":")[1] : "—"}</td>
                <td style={cell}>{r.hp != null ? `${r.hp}/${r.max_hp}` : "—"}</td>
                <td style={cell}>{r.mood ?? "—"}</td>
                <td style={cell}>{r.levels ?? 0}</td>
                <td style={cell}>{r.kills ?? 0}/{r.deaths ?? 0}</td>
                <td style={cell} title={r.last_action}>{(r.last_action || "").slice(0, 28)} <span style={{ color: COLORS.textMuted }}>{fmtAgo(r.last_action_at)}</span></td>
                <td style={cell}>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button type="button" style={btn} disabled={busy} onClick={(e) => { e.stopPropagation(); act(r.id, "restart"); }}>Restart</button>
                    <button type="button" style={btn} disabled={busy} onClick={(e) => { e.stopPropagation(); act(r.id, r.enabled ? "disable" : "enable"); }}>{r.enabled ? "Pause" : "Start"}</button>
                    <button type="button" style={btn} disabled={busy} onClick={(e) => { e.stopPropagation(); teleport(r.id); }}>TP</button>
                    <button type="button" style={btn} disabled={busy} onClick={(e) => { e.stopPropagation(); give(r.id); }}>Give</button>
                  </div>
                </td>
              </tr>
            ))}
            {!rows.length && <tr><td style={cell} colSpan={8}>No agents. Add YAML personas under content/agents/.</td></tr>}
          </tbody>
        </table>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {detail && (
          <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: COLORS.text, marginBottom: 8 }}>
              {detail.name} <span style={{ color: COLORS.textMuted, fontWeight: 400 }}>· {detail.room_id} · {detail.mood}</span>
            </div>
            {detail.metrics && (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10, fontSize: 11, color: COLORS.textMuted }}>
                <span>Levels <b style={{ color: COLORS.text }}>{detail.metrics.levels}</b></span>
                <span>Kills <b style={{ color: COLORS.text }}>{detail.metrics.kills}</b></span>
                <span>Deaths <b style={{ color: COLORS.text }}>{detail.metrics.deaths}</b></span>
                <span>Goals done <b style={{ color: COLORS.text }}>{detail.metrics.goals_completed}</b></span>
                <span>Items used <b style={{ color: COLORS.text }}>{detail.metrics.items_used}</b>{detail.metrics.most_used_item ? ` (top: ${detail.metrics.most_used_item})` : ""}</span>
              </div>
            )}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", marginBottom: 4 }}>Needs</div>
                {Object.entries(detail.feelings?.needs ?? {}).map(([k, v]) => <Bar key={k} label={k} val={v} />)}
                <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", margin: "8px 0 4px" }}>Mood</div>
                <div style={{ fontSize: 11, color: COLORS.text }}>
                  valence {Number(detail.feelings?.mood?.valence ?? 0).toFixed(2)} · arousal {Number(detail.feelings?.mood?.arousal ?? 0).toFixed(2)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", marginBottom: 4 }}>Inventory + equipped</div>
                <div style={{ fontSize: 11, color: COLORS.text, maxHeight: 70, overflow: "auto" }}>
                  {Object.entries(detail.equipment ?? {}).map(([slot, it]) => (
                    <div key={slot}><span style={{ color: COLORS.accent }}>▣ {slot}:</span> {it?.name ?? "?"}</div>
                  ))}
                  {(() => {
                    const grouped = {};
                    (detail.inventory ?? []).forEach((it) => { grouped[it.name] = (grouped[it.name] || 0) + 1; });
                    const entries = Object.entries(grouped);
                    if (!entries.length && !Object.keys(detail.equipment ?? {}).length) return "empty";
                    return entries.map(([n, c]) => <div key={n}>{n}{c > 1 ? ` ×${c}` : ""}</div>);
                  })()}
                </div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", margin: "8px 0 4px" }}>Recent perceptions</div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, maxHeight: 90, overflow: "auto", whiteSpace: "pre-wrap" }}>
                  {(detail.perceptions ?? []).slice(-8).join("\n") || "—"}
                </div>
              </div>
            </div>
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", marginBottom: 4 }}>XP progression</div>
              <ProgressChart progress={detail.progress} />
            </div>
            {detail.skills && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", marginBottom: 4 }}>
                  Skill sheet <span style={{ textTransform: "none" }}>(Σ {detail.metrics?.levels ?? 0} levels)</span>
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", fontSize: 11, color: COLORS.text, marginBottom: 6 }}>
                  {Object.entries(detail.skills.attributes ?? {}).map(([k, v]) => (
                    <span key={k}><span style={{ color: COLORS.textMuted }}>{k}</span> <b>{v}</b></span>
                  ))}
                </div>
                <div style={{ maxHeight: 110, overflow: "auto", fontSize: 10, fontFamily: "monospace", color: COLORS.text }}>
                  {(detail.skills.leaves ?? []).filter((l) => l.level > 0 || l.peak > 0).map((l) => (
                    <div key={l.id}>
                      {l.id} <span style={{ color: COLORS.accent }}>lv {l.level}</span>
                      {l.peak > l.level ? <span style={{ color: COLORS.textMuted }}> (peak {l.peak})</span> : null}
                      <span style={{ color: COLORS.textMuted }}> · {l.state}</span>
                    </div>
                  ))}
                  {!(detail.skills.leaves ?? []).some((l) => l.level > 0 || l.peak > 0) && (
                    <span style={{ color: COLORS.textMuted }}>All proficiencies still at 0 — they raise through use, same engine as players.</span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {selectedId && (
          <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 12, color: COLORS.text, marginBottom: 6 }}>POV — what the brain saw / decided</div>
            <div style={{ maxHeight: 140, overflow: "auto", fontSize: 10, fontFamily: "monospace", color: COLORS.textMuted }}>
              {pov.slice().reverse().map((p, i) => (
                <div key={i} style={{ marginBottom: 4 }}>
                  <span style={{ color: COLORS.accent }}>[{p.kind}]</span> {p.prompt} → <span style={{ color: COLORS.text }}>{p.response}</span>
                </div>
              ))}
              {!pov.length && "No decisions yet."}
            </div>
          </div>
        )}

        {selectedId && (
          <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 12, color: COLORS.text, marginBottom: 6 }}>
              Persona YAML {personaMsg && <span style={{ fontWeight: 400, color: COLORS.textMuted, marginLeft: 8 }}>{personaMsg}</span>}
            </div>
            <textarea
              value={personaText}
              onChange={(e) => setPersonaText(e.target.value)}
              spellCheck={false}
              style={{ width: "100%", minHeight: 220, boxSizing: "border-box", fontFamily: "monospace", fontSize: 11, background: COLORS.bgInput, color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 6, padding: 8 }}
            />
            <div style={{ marginTop: 6, display: "flex", gap: 8 }}>
              <button type="button" style={btn} disabled={busy} onClick={savePersona}>Save persona</button>
              <button type="button" style={btn} disabled={busy} onClick={() => act(selectedId, "restart")}>Save applies on restart →</button>
            </div>
          </div>
        )}
      </div>
    </div>
    )}
    </div>
  );
}
