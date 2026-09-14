import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";

// The model agents think with (config/agents_llm.toml). Lives with the other AI models under
// System › Server & AI models; shown only when the running world loads the agents plugin.
export default function AgentBrainPanel() {
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

  if (!cfg) return msg ? <div style={{ fontSize: 12, color: COLORS.danger }}>Agent brain: {msg}</div> : null;
  const inp = { width: "100%", boxSizing: "border-box", padding: "5px 8px", fontSize: 11, fontFamily: "monospace", background: COLORS.bgInput, color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 6 };
  const lbl = { fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", margin: "8px 0 3px" };
  const btn = { padding: "5px 10px", fontSize: 11, borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bgCard, color: COLORS.text, cursor: "pointer" };
  const embedded = cfg.backend === "embedded";

  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Agent brain</h3>
        <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: COLORS.text }}>
          <input id="agent-brain-enabled" type="checkbox" checked={!!cfg.enabled} disabled={busy}
            onChange={(e) => save({ enabled: e.target.checked })} />
          enabled
        </label>
        <select id="agent-brain-backend" aria-label="Agent brain backend" value={cfg.backend} disabled={busy} style={{ ...inp, width: 160 }}
          onChange={(e) => save({ primary_backend: e.target.value })}>
          <option value="embedded">embedded (in-server)</option>
          <option value="lm_studio">LM Studio</option>
          <option value="ollama">Ollama</option>
        </select>
        <button type="button" style={btn} disabled={busy} onClick={runTest}>Test brain</button>
        {msg && <span style={{ fontSize: 10, color: COLORS.textMuted }}>{msg}</span>}
      </div>
      <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 4 }}>The model agent characters think with. Separate from the narration model above.</div>
      {embedded ? (
        <>
          <label htmlFor="agent-brain-model-path" style={lbl}>GGUF model path (relative to server root)</label>
          <input id="agent-brain-model-path" style={inp} defaultValue={cfg.model_path} key={`mp-${cfg.model_path}`}
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
            <label htmlFor="agent-brain-url" style={lbl}>{cfg.backend === "ollama" ? "Ollama URL" : "LM Studio URL"}</label>
            <input id="agent-brain-url" style={inp} defaultValue={cfg.backend === "ollama" ? cfg.ollama_url : cfg.lm_studio_url}
              key={`url-${cfg.backend}`}
              onBlur={(e) => save(cfg.backend === "ollama" ? { ollama_url: e.target.value } : { lm_studio_url: e.target.value })} />
          </div>
          <div>
            <label htmlFor="agent-brain-model" style={lbl}>Model id</label>
            <input id="agent-brain-model" style={inp} defaultValue={cfg.chat_model} key={`cm-${cfg.chat_model}`}
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
