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

export default function AgentsTab() {
  const { colors: COLORS } = useAdminTheme();
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
    const room = window.prompt("Teleport to room id (zone:slug):", "starter_zone:plaza");
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

  return (
    <div>
    <BrainPanel />
    <div style={{ display: "grid", gridTemplateColumns: "minmax(420px, 1fr) minmax(360px, 1fr)", gap: 16, alignItems: "start" }}>
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <div style={{ padding: "10px 12px", fontWeight: 700, fontSize: 13, color: COLORS.text, borderBottom: `1px solid ${COLORS.border}` }}>
          Agents {error && <span style={{ color: COLORS.danger, fontWeight: 400, marginLeft: 8 }}>{error}</span>}
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>
            <th style={th}>Name</th><th style={th}>Room</th><th style={th}>HP</th>
            <th style={th}>Mood</th><th style={th}>Last action</th><th style={th}></th>
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
            {!rows.length && <tr><td style={cell} colSpan={6}>No agents. Add YAML personas under content/agents/.</td></tr>}
          </tbody>
        </table>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {detail && (
          <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: COLORS.text, marginBottom: 8 }}>
              {detail.name} <span style={{ color: COLORS.textMuted, fontWeight: 400 }}>· {detail.room_id} · {detail.mood}</span>
            </div>
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
                <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", marginBottom: 4 }}>Inventory</div>
                <div style={{ fontSize: 11, color: COLORS.text }}>
                  {(detail.inventory ?? []).map((it) => it.name).join(", ") || "empty"}
                </div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", margin: "8px 0 4px" }}>Recent perceptions</div>
                <div style={{ fontSize: 10, color: COLORS.textMuted, maxHeight: 90, overflow: "auto", whiteSpace: "pre-wrap" }}>
                  {(detail.perceptions ?? []).slice(-8).join("\n") || "—"}
                </div>
              </div>
            </div>
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
    </div>
  );
}
