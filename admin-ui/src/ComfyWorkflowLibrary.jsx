import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";
import { Icons, ActionButton, StatusDot } from "./adminCommon.jsx";

const ROLE_LABEL = { portrait: "Portrait", area: "Scene/Area" };

const fmtSize = (n) => (n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`);
const errText = (e, fallback) => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : d ? JSON.stringify(d) : e?.message || fallback;
};

/**
 * ComfyUI workflow library: see every workflow file, upload API-format exports,
 * inspect nodes, download, delete unused uploads, and assign one to the
 * portrait or scene role (prompt/output node ids checked server-side).
 */
export default function ComfyWorkflowLibrary({ status, onStatus }) {
  const { colors: C } = useAdminTheme();
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [assign, setAssign] = useState({ role: "portrait", prompt: "", output: "" });
  const fileRef = useRef(null);

  const mono = { fontFamily: "'JetBrains Mono', monospace" };
  const inp = {
    padding: "6px 8px", background: C.bgInput, border: `1px solid ${C.border}`,
    borderRadius: 6, color: C.text, fontSize: 12, ...mono,
  };

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/comfyui/workflows`);
      setItems(data.workflows || []);
    } catch (e) {
      setMsg({ ok: false, text: errText(e, "Could not list workflows") });
    }
  }, []);

  const open = useCallback(async (name) => {
    setSelected(name);
    setDetail(null);
    setShowJson(false);
    try {
      const { data } = await axios.get(`${API_BASE}/comfyui/workflows/${encodeURIComponent(name)}`);
      setDetail(data);
      const a = data.analysis;
      const role = data.in_use_as?.[0] || "portrait";
      const current = role === "area"
        ? { prompt: status?.area_positive_prompt_node_id, output: status?.area_output_node_id }
        : { prompt: status?.positive_prompt_node_id, output: status?.output_node_id };
      const inUse = (data.in_use_as || []).includes(role);
      setAssign({
        role,
        prompt: (inUse && current.prompt) || a?.suggested_prompt_node_id || a?.prompt_nodes?.[0]?.id || "",
        output: (inUse && current.output) || a?.suggested_output_node_id || a?.output_nodes?.[0]?.id || "",
      });
    } catch (e) {
      setMsg({ ok: false, text: errText(e, "Could not open workflow") });
    }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    setMsg(null);
    try {
      const content = await file.text();
      const { data } = await axios.post(`${API_BASE}/comfyui/workflows`, { filename: file.name, content, overwrite });
      setMsg({ ok: true, text: `Uploaded ${data.name} (${data.node_count} nodes).` });
      await load();
      await open(data.name);
    } catch (e) {
      const d = errText(e, "Upload failed");
      setMsg({ ok: false, text: d === "name_taken" ? `A workflow named like "${file.name}" already exists — tick "Replace existing" to overwrite it.` : d });
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (name) => {
    if (!window.confirm(`Delete workflow ${name}? This removes the file.`)) return;
    setBusy(true);
    try {
      await axios.delete(`${API_BASE}/comfyui/workflows/${encodeURIComponent(name)}`);
      setMsg({ ok: true, text: `Deleted ${name}.` });
      if (selected === name) { setSelected(null); setDetail(null); }
      await load();
    } catch (e) {
      setMsg({ ok: false, text: errText(e, "Delete failed") });
    } finally {
      setBusy(false);
    }
  };

  const download = () => {
    if (!detail) return;
    const url = URL.createObjectURL(new Blob([detail.content], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = detail.name;
    a.click();
    URL.revokeObjectURL(url);
  };

  const doAssign = async () => {
    if (!detail) return;
    setBusy(true);
    setMsg(null);
    try {
      const { data } = await axios.post(`${API_BASE}/comfyui/workflows/${encodeURIComponent(detail.name)}/assign`, {
        role: assign.role,
        positive_prompt_node_id: assign.prompt || null,
        output_node_id: assign.output || null,
        persist: true,
      });
      onStatus?.(data);
      setMsg({ ok: true, text: `${ROLE_LABEL[assign.role]} generation now uses ${detail.name} (saved to config/comfyui.toml).` });
      await load();
      await open(detail.name);
    } catch (e) {
      setMsg({ ok: false, text: errText(e, "Assign failed") });
    } finally {
      setBusy(false);
    }
  };

  const a = detail?.analysis;
  const th = { textAlign: "left", padding: "6px 8px", fontSize: 10, color: C.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: `1px solid ${C.border}` };
  const td = { padding: "6px 8px", fontSize: 12, color: C.text, borderBottom: `1px solid ${C.border}44`, ...mono };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontSize: 11, color: C.textMuted, lineHeight: 1.5 }}>
        Upload workflows exported from ComfyUI with <strong style={{ color: C.text }}>Workflow → Export (API)</strong>.
        Uploads are stored in <code>config/comfyui_workflows/</code>. Assigning one to a role checks that the prompt node has a text
        input and the output node saves an image, then writes <code>config/comfyui.toml</code>.
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <input ref={fileRef} type="file" accept=".json,application/json" aria-label="Upload workflow JSON"
          onChange={(e) => upload(e.target.files?.[0])} disabled={busy} style={{ fontSize: 12, color: C.textMuted }} />
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: C.textMuted }}>
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
          Replace existing
        </label>
        <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={load} disabled={busy}>Refresh</ActionButton>
      </div>

      {msg && (
        <div role="status" style={{
          display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 6, fontSize: 11.5, ...mono,
          background: msg.ok ? C.successBg : C.dangerBg, color: msg.ok ? C.success : C.danger,
          border: `1px solid ${msg.ok ? C.success : C.danger}22`, wordBreak: "break-word",
        }}>
          <StatusDot color={msg.ok ? C.success : C.danger} />{msg.text}
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>File</th><th style={th}>Nodes</th><th style={th}>Prompt / output nodes</th>
              <th style={th}>In use</th><th style={th}>Size</th><th style={th}>Modified</th><th style={th} />
            </tr>
          </thead>
          <tbody>
            {items.map((w) => (
              <tr key={w.path} onClick={() => open(w.name)}
                style={{ cursor: "pointer", background: selected === w.name ? `${C.accent}18` : "transparent" }}>
                <td style={td}>
                  {w.name}
                  <div style={{ fontSize: 10, color: C.textDim }}>{w.source === "library" ? "uploaded" : "shipped"}{!w.valid && <span style={{ color: C.danger }}> · invalid</span>}</div>
                </td>
                <td style={td}>{w.valid ? w.node_count : "—"}</td>
                <td style={td}>{w.valid ? `${w.prompt_node_count} / ${w.output_node_count}` : <span style={{ color: C.danger, fontSize: 11 }}>{w.error}</span>}</td>
                <td style={td}>{w.in_use_as.length ? w.in_use_as.map((r) => ROLE_LABEL[r]).join(", ") : <span style={{ color: C.textDim }}>—</span>}</td>
                <td style={td}>{fmtSize(w.size_bytes)}</td>
                <td style={td}>{new Date(w.modified_at).toLocaleString()}</td>
                <td style={td} onClick={(e) => e.stopPropagation()}>
                  {w.source === "library" && !w.in_use_as.length && (
                    <ActionButton small variant="danger" icon={<Icons.Trash />} onClick={() => remove(w.name)} disabled={busy} title="Delete">Delete</ActionButton>
                  )}
                </td>
              </tr>
            ))}
            {!items.length && <tr><td style={td} colSpan={7}>No workflows found.</td></tr>}
          </tbody>
        </table>
      </div>

      {detail && (
        <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: C.text, ...mono }}>{detail.name}</div>
            <div style={{ display: "flex", gap: 8 }}>
              <ActionButton small variant="ghost" icon={<Icons.Code />} onClick={() => setShowJson((v) => !v)}>{showJson ? "Hide JSON" : "View JSON"}</ActionButton>
              <ActionButton small icon={<Icons.Copy />} onClick={download}>Download</ActionButton>
            </div>
          </div>
          {!a ? (
            <div style={{ color: C.danger, fontSize: 12 }}>{detail.error}</div>
          ) : (
            <>
              <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
                <label style={{ fontSize: 11, color: C.textMuted }}>Use for
                  <select value={assign.role} onChange={(e) => setAssign((p) => ({ ...p, role: e.target.value }))} style={{ ...inp, display: "block", marginTop: 4 }}>
                    <option value="portrait">Portrait</option>
                    <option value="area">Scene/Area</option>
                  </select>
                </label>
                <label style={{ fontSize: 11, color: C.textMuted }}>Prompt node (text input)
                  <select value={assign.prompt} onChange={(e) => setAssign((p) => ({ ...p, prompt: e.target.value }))} style={{ ...inp, display: "block", marginTop: 4, minWidth: 220 }}>
                    <option value="">— pick —</option>
                    {a.prompt_nodes.map((n) => <option key={n.id} value={n.id}>{n.id} · {n.title}</option>)}
                  </select>
                </label>
                <label style={{ fontSize: 11, color: C.textMuted }}>Output node (image)
                  <select value={assign.output} onChange={(e) => setAssign((p) => ({ ...p, output: e.target.value }))} style={{ ...inp, display: "block", marginTop: 4, minWidth: 200 }}>
                    <option value="">— pick —</option>
                    {a.output_nodes.map((n) => <option key={n.id} value={n.id}>{n.id} · {n.title}</option>)}
                  </select>
                </label>
                <ActionButton variant="primary" icon={<Icons.Check />} onClick={doAssign} disabled={busy || !assign.prompt || !assign.output}>Assign &amp; save</ActionButton>
              </div>
              {a.checkpoint_loaders.length > 0 && (
                <div style={{ fontSize: 11, color: C.textMuted }}>
                  Checkpoint loaders: {a.checkpoint_loaders.map((l) => `${l.id} (${l.ckpt_name || "unset"})`).join(", ")} — the Checkpoint name setting overrides these.
                </div>
              )}
              <div style={{ overflowX: "auto", maxHeight: 260, overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead><tr><th style={th}>Node</th><th style={th}>Class</th><th style={th}>Title</th></tr></thead>
                  <tbody>
                    {a.nodes.map((n) => (
                      <tr key={n.id}>
                        <td style={td}>{n.id}</td>
                        <td style={td}>{n.class_type}</td>
                        <td style={td}>{n.title}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {showJson && (
            <pre style={{ margin: 0, maxHeight: 360, overflow: "auto", background: C.bgInput, border: `1px solid ${C.border}`, borderRadius: 6, padding: 10, fontSize: 11, color: C.text, ...mono }}>
              {detail.content}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
