import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE, WS_BASE } from "../apiConfig.js";
import {
  LS_ADMIN_TOKEN, ALL_ADMIN_TOOLS, adminWsBase, adminPresenceWsUrl, adminLogsWsUrl,
  sendWsAuthToken, parseLeadingInt, parseRoomType, extractYamlRoomId, Icons,
  Badge, StatusDot, Pill, ActionButton, PlannedAction, SearchBar, TabBar,
  DataTable, StatCard, usePolledList, FetchErrorBanner,
} from "../adminCommon.jsx";
import ComfyWorkflowLibrary from "../ComfyWorkflowLibrary.jsx";
import AgentBrainPanel from "../agentBrainPanel.jsx";
import { useWorldSummary } from "../useWorldSummary.js";


const HostMachinePanel = ({ host, llmDetected, llmConfigured, llmConnected, llmBackend, llmModelsAlign }) => {
  const { colors: COLORS } = useAdminTheme();
  if (!host) return null;
  const bar = (pct, color) => (
    <div style={{ width: "100%", height: 5, borderRadius: 5, background: COLORS.bgInput, overflow: "hidden" }}>
      <div style={{ width: `${Math.min(100, Math.max(0, pct || 0))}%`, height: "100%", borderRadius: 5, background: color, transition: "width 0.35s ease" }} />
    </div>
  );
  const metricRow = (icon, label, value, icolor) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ color: icolor, flexShrink: 0, display: "flex" }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
        <div style={{ fontSize: 13, fontWeight: 600, color: icolor, fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
      </div>
    </div>
  );

  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20, display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Host machine</h3>
          <p style={{ margin: "6px 0 0", fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>
            {host.hostname || "—"} · {host.os || "—"}
            {host.python_version ? ` · Python ${host.python_version}` : ""}
          </p>
        </div>
        {(llmBackend === "lm_studio" || llmDetected || llmConfigured) && (
          <div style={{ textAlign: "right", maxWidth: 440 }}>
            <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Chat model{llmConnected ? "" : " (LLM offline)"}
            </div>
            <div style={{ fontSize: 12, color: COLORS.forge, fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, wordBreak: "break-word" }}>
              {llmDetected || llmConfigured || "—"}
            </div>
            {llmModelsAlign === false && llmConfigured && llmDetected && (
              <div style={{ fontSize: 10, color: COLORS.warning, marginTop: 4, fontFamily: "'JetBrains Mono', monospace" }}>
                Chat model id not in server list: {llmConfigured}
              </div>
            )}
          </div>
        )}
      </div>

      {!host.ok && host.error && (
        <div style={{ fontSize: 12, color: COLORS.warning, fontFamily: "'DM Sans', sans-serif" }}>{host.error}</div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>CPU load</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace" }}>{host.cpu_percent != null ? `${host.cpu_percent}%` : "—"}</span>
          </div>
          {bar(host.cpu_percent, COLORS.accent)}
          {host.cpu_count != null && (
            <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{host.cpu_count} logical CPUs</div>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>System memory</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: COLORS.info, fontFamily: "'JetBrains Mono', monospace" }}>{host.memory_percent != null ? `${host.memory_percent}%` : "—"}</span>
          </div>
          {bar(host.memory_percent, COLORS.info)}
          <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>
            {host.memory_used_gb != null && host.memory_total_gb != null
              ? `${host.memory_used_gb} GB / ${host.memory_total_gb} GB`
              : ""}
          </div>
        </div>
      </div>

      <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>Graphics</div>

      {host.gpus && host.gpus.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {host.gpus.map((gpu) => (
            <div
              key={gpu.index}
              style={{
                background: COLORS.bgInput,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 10,
                padding: 16,
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                gap: 24,
              }}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{gpu.name}</span>
                  <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999, background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}># {gpu.index}</span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {metricRow(<Icons.Thermometer />, "Temperature", gpu.temperature_c != null ? `${gpu.temperature_c}°C` : "—", COLORS.success)}
                  {metricRow(<Icons.Fan />, "Fan speed", gpu.fan_percent != null ? `${gpu.fan_percent}%` : "N/A", COLORS.info)}
                  {metricRow(<Icons.Clock />, "Clock", gpu.clock_mhz != null ? `${gpu.clock_mhz} MHz` : "—", COLORS.forge)}
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}><Icons.Chip /> GPU load</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace" }}>{gpu.gpu_util_percent ?? 0}%</span>
                  </div>
                  {bar(gpu.gpu_util_percent, COLORS.textMuted)}
                </div>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}><Icons.Ram /> VRAM</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.info, fontFamily: "'JetBrains Mono', monospace" }}>{gpu.memory_percent != null ? `${gpu.memory_percent}%` : "—"}</span>
                  </div>
                  {bar(gpu.memory_percent ?? 0, COLORS.cyan)}
                  <div style={{ fontSize: 10, color: COLORS.textDim, marginTop: 6, fontFamily: "'JetBrains Mono', monospace" }}>
                    {gpu.memory_used_mib != null && gpu.memory_total_mib != null
                      ? `${(gpu.memory_used_mib / 1024).toFixed(1)} GB / ${(gpu.memory_total_mib / 1024).toFixed(1)} GB`
                      : ""}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
                  <span style={{ color: COLORS.warning, display: "flex" }}><Icons.Zap /></span>
                  <span>
                    Power{" "}
                    <span style={{ color: COLORS.text, fontFamily: "'JetBrains Mono', monospace" }}>
                      {gpu.power_draw_w != null ? `${gpu.power_draw_w.toFixed(1)}W` : "—"}
                      {gpu.power_limit_w != null ? ` / ${gpu.power_limit_w.toFixed(1)}W` : ""}
                    </span>
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif" }}>
          No NVIDIA GPU telemetry (nvidia-smi not available or no driver). CPU and system RAM above still reflect this host.
        </div>
      )}
    </div>
  );
};



const LmStudioPanel = () => {
  const { colors: COLORS } = useAdminTheme();
  const [llmStatus, setLlmStatus] = useState(null);
  const [llmForm, setLlmForm] = useState({
    primary_backend: "lm_studio",
    lm_studio_url: "http://localhost:1234/v1",
    ollama_url: "http://localhost:11434/v1",
    chat_model: "auto",
    temperature: 0.7,
    timeout_seconds: 10,
    lm_studio_key: "",
  });
  const [persistLlm, setPersistLlm] = useState(true);
  const [llmBusy, setLlmBusy] = useState(false);
  const [testReply, setTestReply] = useState("");
  const [connectResult, setConnectResult] = useState(null);

  const syncLlm = useCallback(async (forceRefresh = false) => {
    try {
      const { data } = await axios.get(`${API_BASE}/llm/status`, {
        params: forceRefresh ? { refresh: true } : undefined,
      });
      setLlmStatus(data);
      setLlmForm((prev) => ({
        ...prev,
        primary_backend: data.primary_backend,
        lm_studio_url: data.lm_studio_url,
        ollama_url: data.ollama_url,
        chat_model: data.chat_model,
        temperature: data.temperature,
        timeout_seconds: data.timeout_seconds,
      }));
    } catch {
      setLlmStatus(null);
    }
  }, []);

  useEffect(() => {
    syncLlm();
    const id = setInterval(() => syncLlm(false), 120000);
    return () => clearInterval(id);
  }, [syncLlm]);

  const connectLlm = async () => {
    setLlmBusy(true);
    setConnectResult(null);
    try {
      const { data } = await axios.patch(`${API_BASE}/llm/settings?persist=false`, {
        primary_backend: llmForm.primary_backend,
        lm_studio_url: llmForm.lm_studio_url,
        ollama_url: llmForm.ollama_url,
      });
      setLlmStatus(data);
      setLlmForm((prev) => ({
        ...prev,
        primary_backend: data.primary_backend,
        lm_studio_url: data.lm_studio_url,
        ollama_url: data.ollama_url,
        chat_model: data.chat_model,
        temperature: data.temperature,
        timeout_seconds: data.timeout_seconds,
      }));
      if (data.connected) {
        const det = data.detected_model ? ` · model: ${data.detected_model.length > 40 ? `${data.detected_model.slice(0, 38)}…` : data.detected_model}` : "";
        setConnectResult({ ok: true, msg: `Connected · ${data.latency_ms ?? "?"}ms · ${data.model_count ?? 0} model(s)${det}` });
      } else {
        setConnectResult({ ok: false, msg: data.error || "Backend unreachable" });
      }
    } catch (e) {
      const d = e.response?.data?.detail;
      setConnectResult({ ok: false, msg: typeof d === "string" ? d : (e.message || "Connection failed") });
    } finally {
      setLlmBusy(false);
    }
  };

  const saveLlmSettings = async () => {
    setLlmBusy(true);
    setTestReply("");
    try {
      const body = {
        primary_backend: llmForm.primary_backend,
        lm_studio_url: llmForm.lm_studio_url,
        ollama_url: llmForm.ollama_url,
        chat_model: llmForm.chat_model,
        temperature: Number(llmForm.temperature),
        timeout_seconds: Number(llmForm.timeout_seconds),
      };
      if (llmForm.lm_studio_key?.trim()) body.lm_studio_key = llmForm.lm_studio_key.trim();
      const { data } = await axios.patch(`${API_BASE}/llm/settings?persist=${persistLlm}`, body);
      setLlmStatus(data);
    } catch (e) {
      const d = e.response?.data?.detail;
      window.alert(typeof d === "string" ? d : (e.message || "Save failed"));
    } finally {
      setLlmBusy(false);
    }
  };

  const runLlmTest = async () => {
    setLlmBusy(true);
    setTestReply("");
    try {
      const { data } = await axios.post(`${API_BASE}/llm/test-completion`);
      setTestReply(data.reply || "");
    } catch (e) {
      setTestReply(e.response?.data?.detail || e.message || "failed");
    } finally {
      setLlmBusy(false);
    }
  };

  const inp = {
    width: "100%",
    padding: "8px 10px",
    background: COLORS.bgInput,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 6,
    color: COLORS.text,
    fontSize: 12,
    fontFamily: "'DM Sans', sans-serif",
  };

  return (
    <div style={{
      background: COLORS.bgCard,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 10,
      padding: 18,
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
      gap: 20,
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif", display: "flex", alignItems: "center", gap: 8 }}>
            <Icons.Zap /> LM Studio / LLM
          </h3>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <StatusDot color={llmStatus?.connected ? COLORS.success : COLORS.danger} pulse={llmStatus?.connected} />
            <span style={{ fontSize: 12, fontWeight: 600, color: llmStatus?.connected ? COLORS.success : COLORS.danger, fontFamily: "'DM Sans', sans-serif" }}>
              {llmStatus?.connected ? "Reachable" : "Not connected"}
            </span>
          </div>
        </div>
        <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.5, wordBreak: "break-all" }}>
          <div><strong style={{ color: COLORS.textDim }}>Base URL</strong> {llmStatus?.base_url || "—"}</div>
          <div>
            <strong style={{ color: COLORS.textDim }}>Detected</strong>{" "}
            <span style={{ color: COLORS.forge, fontWeight: 600 }}>{llmStatus?.detected_model || "—"}</span>
            {llmStatus?.detected_model_source === "loaded" && (
              <span style={{ color: COLORS.textDim, fontWeight: 400 }}> (loaded)</span>
            )}
          </div>
          <div><strong style={{ color: COLORS.textDim }}>Chat model id</strong> {llmStatus?.chat_model || "—"}</div>
          {llmStatus?.chat_model_auto && (
            <div style={{ color: COLORS.textDim, marginTop: 4, fontSize: 11 }}>
              Auto: Nexus sends the model the server lists (loaded / first entry). Set a specific id only if you use Ollama with several models or need to pin one name.
            </div>
          )}
          {llmStatus?.models_align === false && (
            <div style={{ color: COLORS.warning, marginTop: 6 }}>
              That chat model id is not in the server&apos;s model list. Switch to <code style={{ color: COLORS.textMuted }}>auto</code> or type an id from the list below.
            </div>
          )}
          {llmStatus?.model_count != null && (
            <div><strong style={{ color: COLORS.textDim }}>Models listed</strong> {llmStatus.model_count}</div>
          )}
          {llmStatus?.latency_ms != null && (
            <div><strong style={{ color: COLORS.textDim }}>List latency</strong> {llmStatus.latency_ms} ms</div>
          )}
          {llmStatus?.status_cached && (
            <div style={{ fontSize: 11, color: COLORS.textDim, marginTop: 4 }}>Status from cache (use Refresh for live probe)</div>
          )}
          {llmStatus?.error && (
            <div style={{ color: COLORS.danger, marginTop: 6 }}>{llmStatus.error}</div>
          )}
        </div>
        <p style={{ margin: 0, fontSize: 11, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.45 }}>
          Powers: <strong>AI Forge</strong> (room + generic YAML), in-game <strong>look</strong> narration, and the test button below. Start LM Studio, load a model, enable the local server (default <code style={{ color: COLORS.textMuted }}>http://localhost:1234</code>), then set the base URL here (include <code style={{ color: COLORS.textMuted }}>/v1</code>).
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={() => syncLlm(true)} disabled={llmBusy}>Refresh status</ActionButton>
          <ActionButton small variant="primary" icon={<Icons.Terminal />} onClick={runLlmTest} disabled={llmBusy}>Test chat</ActionButton>
        </div>
        {testReply && (
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", padding: 8, background: COLORS.bgInput, borderRadius: 6 }}>
            Test reply: {testReply}
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>Settings</div>
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>Backend</label>
        <select value={llmForm.primary_backend} onChange={(e) => { setLlmForm((p) => ({ ...p, primary_backend: e.target.value })); setConnectResult(null); }} style={inp}>
          <option value="embedded">Embedded (model loaded inside the server)</option>
          <option value="lm_studio">LM Studio (OpenAI-compatible)</option>
          <option value="ollama">Ollama</option>
        </select>
        {llmForm.primary_backend === "embedded" && (
          <div style={{ fontSize: 11, color: COLORS.textMuted, lineHeight: 1.5 }}>
            The embedded backend runs the GGUF file named by <code>model_path</code> in <code>config/llm.toml</code>; change the file there and restart. The URLs below are only used by LM Studio and Ollama.
          </div>
        )}
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>LM Studio base URL</label>
        <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
          <input value={llmForm.lm_studio_url} onChange={(e) => { setLlmForm((p) => ({ ...p, lm_studio_url: e.target.value })); setConnectResult(null); }} style={{ ...inp, flex: 1 }} placeholder="http://localhost:1234/v1" />
          <button
            type="button"
            onClick={connectLlm}
            disabled={llmBusy || llmForm.primary_backend !== "lm_studio"}
            title={llmForm.primary_backend !== "lm_studio" ? "Switch backend to LM Studio to connect" : "Test connection to this URL"}
            style={{
              padding: "0 14px",
              background: llmBusy ? COLORS.bgInput : COLORS.accent,
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              fontFamily: "'DM Sans', sans-serif",
              cursor: llmBusy || llmForm.primary_backend !== "lm_studio" ? "not-allowed" : "pointer",
              opacity: llmForm.primary_backend !== "lm_studio" ? 0.35 : 1,
              whiteSpace: "nowrap",
              flexShrink: 0,
              transition: "background 0.15s",
            }}
          >
            {llmBusy ? "…" : "Connect"}
          </button>
        </div>
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>Ollama base URL</label>
        <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
          <input value={llmForm.ollama_url} onChange={(e) => { setLlmForm((p) => ({ ...p, ollama_url: e.target.value })); setConnectResult(null); }} style={{ ...inp, flex: 1 }} placeholder="http://localhost:11434/v1" />
          <button
            type="button"
            onClick={connectLlm}
            disabled={llmBusy || llmForm.primary_backend !== "ollama"}
            title={llmForm.primary_backend !== "ollama" ? "Switch backend to Ollama to connect" : "Test connection to this URL"}
            style={{
              padding: "0 14px",
              background: llmBusy ? COLORS.bgInput : COLORS.accent,
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              fontFamily: "'DM Sans', sans-serif",
              cursor: llmBusy || llmForm.primary_backend !== "ollama" ? "not-allowed" : "pointer",
              opacity: llmForm.primary_backend !== "ollama" ? 0.35 : 1,
              whiteSpace: "nowrap",
              flexShrink: 0,
              transition: "background 0.15s",
            }}
          >
            {llmBusy ? "…" : "Connect"}
          </button>
        </div>
        {connectResult && (
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 12px",
            borderRadius: 6,
            background: connectResult.ok ? COLORS.successBg : COLORS.dangerBg,
            border: `1px solid ${connectResult.ok ? COLORS.success : COLORS.danger}22`,
            fontSize: 11.5,
            fontFamily: "'JetBrains Mono', monospace",
            color: connectResult.ok ? COLORS.success : COLORS.danger,
          }}>
            <StatusDot color={connectResult.ok ? COLORS.success : COLORS.danger} pulse={connectResult.ok} />
            {connectResult.msg}
          </div>
        )}
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>Chat model id</label>
        <input list="llm-model-ids-server" value={llmForm.chat_model} onChange={(e) => setLlmForm((p) => ({ ...p, chat_model: e.target.value }))} style={inp} placeholder="auto — or exact model id from server" />
        <datalist id="llm-model-ids-server">
          <option value="auto" />
          {(llmStatus?.models || []).map((m) => <option key={m.id} value={m.id} />)}
        </datalist>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div>
            <label style={{ fontSize: 11, color: COLORS.textMuted }}>Temperature</label>
            <input type="number" step="0.05" min="0" max="2" value={llmForm.temperature} onChange={(e) => setLlmForm((p) => ({ ...p, temperature: e.target.value }))} style={inp} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: COLORS.textMuted }}>Timeout (s)</label>
            <input type="number" step="1" min="1" value={llmForm.timeout_seconds} onChange={(e) => setLlmForm((p) => ({ ...p, timeout_seconds: e.target.value }))} style={inp} />
          </div>
        </div>
        <label style={{ fontSize: 11, color: COLORS.textMuted }}>API key (optional)</label>
        <input type="password" value={llmForm.lm_studio_key} onChange={(e) => setLlmForm((p) => ({ ...p, lm_studio_key: e.target.value }))} style={inp} placeholder={llmStatus?.lm_studio_key_set ? "Leave blank to keep current key" : "not-needed"} autoComplete="off" />
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: COLORS.textMuted, cursor: "pointer" }}>
          <input type="checkbox" checked={persistLlm} onChange={(e) => setPersistLlm(e.target.checked)} />
          Save to config/llm.toml (survives restart)
        </label>
        <ActionButton variant="primary" icon={<Icons.Save />} onClick={saveLlmSettings} disabled={llmBusy}>{llmBusy ? "Saving…" : "Apply settings"}</ActionButton>
      </div>
    </div>
  );
};


// ─── ComfyUI Workflows Panel (AI art credit prices are under Economy › AI art credits) ──────────────────────────────────────

const COMFY_TABS = [
  { id: "status",    label: "Status" },
  { id: "library",   label: "Workflow library" },
  { id: "portrait",  label: "Portrait workflow" },
  { id: "scene",     label: "Scene/Area workflow" },
];

const ComfyUIPanel = () => {
  const { colors: COLORS } = useAdminTheme();
  const [tab, setTab] = useState("status");
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({
    enabled: false,
    base_url: "http://127.0.0.1:8188",
    workflow_path: "config/comfyui_character_portrait_workflow.json",
    positive_prompt_node_id: "57",
    output_node_id: "40",
    area_workflow_path: "config/comfyui_scene_workflow.json",
    area_positive_prompt_node_id: "16",
    area_output_node_id: "17",
    checkpoint_name: "",
    timeout_seconds: 600,
    poll_interval_seconds: 0.75,
    economy_enabled: true,
    starting_ai_credits: 50,
    portrait_generation_cost: 3,
    area_generation_cost: 3,
    character_create_portrait_cost: 3,
    currency_display_name: "credits",
    credits_per_usd: 100,
  });
  const [persist, setPersist] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saveMsg, setSaveMsg] = useState("");

  const syncStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/comfyui/status`);
      setStatus(data);
      setForm((prev) => ({
        ...prev,
        enabled: data.enabled ?? prev.enabled,
        base_url: data.base_url ?? prev.base_url,
        workflow_path: data.workflow_path ?? prev.workflow_path,
        positive_prompt_node_id: data.positive_prompt_node_id ?? prev.positive_prompt_node_id,
        output_node_id: data.output_node_id ?? prev.output_node_id,
        area_workflow_path: data.area_workflow_path ?? prev.area_workflow_path,
        area_positive_prompt_node_id: data.area_positive_prompt_node_id ?? prev.area_positive_prompt_node_id,
        area_output_node_id: data.area_output_node_id ?? prev.area_output_node_id,
        checkpoint_name: data.checkpoint_name ?? prev.checkpoint_name,
        timeout_seconds: data.timeout_seconds ?? prev.timeout_seconds,
        poll_interval_seconds: data.poll_interval_seconds ?? prev.poll_interval_seconds,
        economy_enabled: data.economy_enabled ?? prev.economy_enabled,
        starting_ai_credits: data.starting_ai_credits ?? prev.starting_ai_credits,
        portrait_generation_cost: data.portrait_generation_cost ?? prev.portrait_generation_cost,
        area_generation_cost: data.area_generation_cost ?? prev.area_generation_cost,
        character_create_portrait_cost: data.character_create_portrait_cost ?? prev.character_create_portrait_cost,
        currency_display_name: data.currency_display_name ?? prev.currency_display_name,
        credits_per_usd: data.credits_per_usd ?? prev.credits_per_usd,
      }));
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    syncStatus();
    const id = setInterval(syncStatus, 120000);
    return () => clearInterval(id);
  }, [syncStatus]);

  const testConnection = async () => {
    setBusy(true);
    setTestResult(null);
    try {
      const { data } = await axios.post(`${API_BASE}/comfyui/test-connection`);
      setTestResult({ ok: data.reachable, msg: data.reachable ? `Reachable · ${data.base_url}` : (data.error || "Not reachable") });
    } catch (e) {
      setTestResult({ ok: false, msg: e.response?.data?.detail || e.message || "Request failed" });
    } finally {
      setBusy(false);
    }
  };

  const saveSettings = async () => {
    setBusy(true);
    setSaveMsg("");
    try {
      const body = { ...form };
      body.timeout_seconds = Number(form.timeout_seconds);
      body.poll_interval_seconds = Number(form.poll_interval_seconds);
      body.starting_ai_credits = Number(form.starting_ai_credits);
      body.portrait_generation_cost = Number(form.portrait_generation_cost);
      body.area_generation_cost = Number(form.area_generation_cost);
      body.character_create_portrait_cost = Number(form.character_create_portrait_cost);
      body.credits_per_usd = Number(form.credits_per_usd);
      const { data } = await axios.patch(`${API_BASE}/comfyui/settings?persist=${persist}`, body);
      setStatus(data);
      setSaveMsg(persist ? "Saved to config/comfyui.toml." : "Applied (in-memory only).");
    } catch (e) {
      setSaveMsg(e.response?.data?.detail || e.message || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const inp = {
    width: "100%", padding: "8px 10px",
    background: COLORS.bgInput, border: `1px solid ${COLORS.border}`,
    borderRadius: 6, color: COLORS.text, fontSize: 12,
    fontFamily: "'DM Sans', sans-serif",
  };
  const F = (label, key, type = "text", opts = {}) => (
    <div key={key}>
      <label style={{ fontSize: 11, color: COLORS.textMuted, display: "block", marginBottom: 4 }}>{label}</label>
      <input
        type={type}
        value={form[key] ?? ""}
        onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))}
        style={inp}
        {...opts}
      />
    </div>
  );

  const StatusBadge = ({ ok, yes, no }) => (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "2px 10px", borderRadius: 999, fontSize: 11, fontWeight: 700,
      background: ok ? `${COLORS.success}22` : `${COLORS.danger}22`,
      color: ok ? COLORS.success : COLORS.danger,
      border: `1px solid ${ok ? COLORS.success : COLORS.danger}44`,
    }}>
      <StatusDot color={ok ? COLORS.success : COLORS.danger} pulse={ok} />
      {ok ? yes : no}
    </span>
  );

  return (
    <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif", display: "flex", alignItems: "center", gap: 8 }}>
          <Icons.Wand /> ComfyUI Workflows
        </h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <StatusBadge ok={status?.enabled} yes="Enabled" no="Disabled" />
          <StatusBadge ok={status?.comfy_reachable} yes="Reachable" no="Offline" />
        </div>
      </div>

      <TabBar tabs={COMFY_TABS} active={tab} onChange={setTab} />

      {tab === "status" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>Connection</div>
            <div style={{ fontSize: 12, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.8 }}>
              <div><span style={{ color: COLORS.textDim }}>Base URL</span> {status?.base_url || "—"}</div>
              <div><span style={{ color: COLORS.textDim }}>Enabled</span> {status?.enabled ? "Yes" : "No"}</div>
              <div><span style={{ color: COLORS.textDim }}>Reachable</span> {status?.comfy_reachable ? "Yes" : "No"}</div>
              {status?.comfy_ping_error && <div style={{ color: COLORS.danger, fontSize: 11 }}>{status.comfy_ping_error}</div>}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={syncStatus} disabled={busy}>Refresh</ActionButton>
              <ActionButton small variant="primary" icon={<Icons.Terminal />} onClick={testConnection} disabled={busy}>Test connection</ActionButton>
            </div>
            {testResult && (
              <div style={{
                display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 6,
                background: testResult.ok ? COLORS.successBg : COLORS.dangerBg,
                border: `1px solid ${testResult.ok ? COLORS.success : COLORS.danger}22`,
                fontSize: 11.5, fontFamily: "'JetBrains Mono', monospace",
                color: testResult.ok ? COLORS.success : COLORS.danger,
              }}>
                <StatusDot color={testResult.ok ? COLORS.success : COLORS.danger} pulse={testResult.ok} />
                {testResult.msg}
              </div>
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>Workflows</div>
            <div style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.8 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: COLORS.textDim }}>Portrait</span>
                <StatusBadge ok={status?.workflow_present} yes="file found" no="missing" />
              </div>
              <div style={{ color: COLORS.textMuted, fontSize: 11, marginBottom: 6, wordBreak: "break-all" }}>{status?.workflow_path || "—"}</div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: COLORS.textDim }}>Scene / Area</span>
                <StatusBadge ok={status?.area_workflow_present} yes="file found" no="missing" />
              </div>
              <div style={{ color: COLORS.textMuted, fontSize: 11, wordBreak: "break-all" }}>{status?.area_workflow_path || "—"}</div>
            </div>
            {status?.suggest_checkpoint_name_in_toml && (
              <div style={{ fontSize: 11, color: COLORS.warning, padding: "6px 10px", background: `${COLORS.warning}11`, border: `1px solid ${COLORS.warning}44`, borderRadius: 6 }}>
                Area workflow uses a CheckpointLoaderSimple node but <strong>checkpoint_name</strong> is not set — set it in the Workflows tab so the server can inject it automatically.
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "library" && <ComfyWorkflowLibrary status={status} onStatus={setStatus} />}

      {tab === "portrait" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
            Used for <strong style={{ color: COLORS.text }}>character portraits</strong> — triggered at character creation and from the player client. The JSON must be a ComfyUI API-format workflow.
          </div>
          {F("Workflow JSON path", "workflow_path")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {F("Positive prompt node ID", "positive_prompt_node_id")}
            {F("Output (SaveImage) node ID", "output_node_id")}
          </div>
          {F("Base URL", "base_url")}
          {F("Checkpoint name (optional — injected into CheckpointLoaderSimple nodes)", "checkpoint_name")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {F("Timeout (s)", "timeout_seconds", "number", { min: 10, step: 10 })}
            {F("Poll interval (s)", "poll_interval_seconds", "number", { min: 0.1, step: 0.25 })}
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: COLORS.textMuted, cursor: "pointer" }}>
            <input type="checkbox" checked={form.enabled} onChange={(e) => setForm((p) => ({ ...p, enabled: e.target.checked }))} />
            ComfyUI integration enabled
          </label>
        </div>
      )}

      {tab === "scene" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
            Used for <strong style={{ color: COLORS.text }}>room / area scene images</strong> — triggered by AI Forge and from the player client. Falls back to the portrait workflow JSON if this path is not set.
          </div>
          {F("Area workflow JSON path", "area_workflow_path")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {F("Positive prompt node ID", "area_positive_prompt_node_id")}
            {F("Output (SaveImage) node ID", "area_output_node_id")}
          </div>
          {F("Base URL", "base_url")}
          {F("Checkpoint name (optional)", "checkpoint_name")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {F("Timeout (s)", "timeout_seconds", "number", { min: 10, step: 10 })}
            {F("Poll interval (s)", "poll_interval_seconds", "number", { min: 0.1, step: 0.25 })}
          </div>
        </div>
      )}

      {tab !== "status" && tab !== "library" && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, paddingTop: 6, borderTop: `1px solid ${COLORS.border}44` }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: COLORS.textMuted, cursor: "pointer", flexShrink: 0 }}>
            <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
            Save to config/comfyui.toml
          </label>
          <ActionButton variant="primary" icon={<Icons.Save />} onClick={saveSettings} disabled={busy}>{busy ? "Saving…" : "Apply settings"}</ActionButton>
          {saveMsg && <span style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>{saveMsg}</span>}
        </div>
      )}
    </div>
  );
};


// ═══════════════════════════════════════════════════════════════
// EXISTING PAGE COMPONENTS (condensed from v1)

const TickMetrics = () => {
  const { colors: COLORS } = useAdminTheme();
  const [metrics, setMetrics] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => axios.get(`${API_BASE}/admin/metrics`).then(({ data }) => alive && setMetrics(data)).catch(() => alive && setMetrics(null));
    load();
    const id = setInterval(load, 10000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return (
    <details style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18 }}>
      <summary style={{ cursor: "pointer", fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Tick metrics</summary>
      <pre style={{ margin: "12px 0 0", fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
        {metrics ? JSON.stringify(metrics, null, 2) : "Could not load /admin/metrics"}
      </pre>
    </details>
  );
};

const ServerPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const { summary } = useWorldSummary();
  const hasAgents = (summary?.plugins || []).some((p) => p.id === "agents");
  const [info, setInfo] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/server/info`);
        setInfo(data);
      } catch {
        setInfo(null);
      }
    };
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, []);

  const metrics = info ? [
    { label: "Tick rate", value: `${info.tick_rate_hz?.toFixed(1) ?? "—"} Hz`, color: COLORS.success, pct: Math.min(100, (info.tick_rate_hz || 0) * 5) },
    { label: "Nexus port", value: String(info.nexus_port ?? "—"), color: COLORS.info, pct: 40 },
    { label: "Redis", value: info.redis_ok ? "OK" : "down", color: info.redis_ok ? COLORS.accent : COLORS.danger, pct: info.redis_ok ? 70 : 10 },
    { label: "PostgreSQL", value: info.postgres_ok ? "OK" : "down", color: info.postgres_ok ? COLORS.warning : COLORS.danger, pct: info.postgres_ok ? 50 : 10 },
    { label: "LLM backend", value: info.llm_backend ?? "—", color: COLORS.cyan, pct: 55 },
    { label: "Game sessions", value: String(info.sessions ?? 0), color: COLORS.success, pct: Math.min(100, (info.sessions || 0) * 10) },
  ] : [
    { label: "Nexus", value: "offline", color: COLORS.danger, pct: 5 },
  ];

  const configRows = info ? [
    { key: "tick_interval_s", value: String(info.tick_interval_s) },
    { key: "nexus_port", value: String(info.nexus_port) },
    { key: "player_transport", value: String(info.player_transport ?? "websocket") },
    { key: "max_connections", value: String(info.max_connections) },
    { key: "dev_mode", value: String(info.dev_mode) },
    { key: "llm_backend", value: String(info.llm_backend) },
    { key: "llm_url", value: String(info.llm_url || "—") },
    { key: "llm_model", value: String(info.llm_model || "—") },
    { key: "llm_detected_model", value: String(info.llm_detected_model || "—") },
    { key: "llm_models_align", value: info.llm_models_align == null ? "—" : info.llm_models_align ? "yes" : "no" },
    { key: "llm_chat_model_auto", value: info.llm_chat_model_auto == null ? "—" : info.llm_chat_model_auto ? "yes" : "no" },
    { key: "llm_connected", value: info.llm_connected ? "yes" : "no" },
    { key: "llm_list_ms", value: info.llm_latency_ms != null ? String(info.llm_latency_ms) : "—" },
    { key: "tick_count", value: String(info.tick_count) },
  ] : [{ key: "status", value: "Could not load /server/info" }];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Server &amp; AI models</h2>
      </div>
      {info?.host && (
        <HostMachinePanel
          host={info.host}
          llmDetected={info.llm_detected_model}
          llmConfigured={info.llm_model}
          llmConnected={info.llm_connected}
          llmBackend={info.llm_backend}
          llmModelsAlign={info.llm_models_align}
        />
      )}
      <LmStudioPanel />
      {hasAgents && <AgentBrainPanel />}
      <ComfyUIPanel />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14 }}>
        {metrics.map((m) => (
          <div key={m.label} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>{m.label}</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace" }}>{m.value}</span>
            </div>
            <div style={{ width: "100%", height: 6, borderRadius: 3, background: COLORS.bgInput }}><div style={{ width: `${m.pct}%`, height: "100%", borderRadius: 3, background: m.color }} /></div>
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Server Config</h3>
          {configRows.map((c) => (
            <div key={c.key} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${COLORS.border}22`, gap: 8 }}>
              <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", wordBreak: "break-all" }}>{c.key}</span>
              <span style={{ fontSize: 12, color: COLORS.text, fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, textAlign: "right" }}>{c.value}</span>
            </div>
          ))}
        </div>
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>Recent Events</h3>
          <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
            Events are not stored yet. <strong style={{ color: COLORS.text }}>Dashboard → Live Activity</strong> streams server warnings and errors while this console is open.
          </div>
        </div>
      </div>
      <TickMetrics />
    </div>
  );
};

export default ServerPage;
