import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";
import { Icons, Badge, ActionButton, FetchErrorBanner } from "./adminCommon.jsx";

// Detail views for the Content Library: a room (read-only, with live state and its content check
// findings) and an entity or item template (YAML editor with a validated save).

const mono = "'JetBrains Mono', monospace";

// An API error as one line of text: FastAPI returns a string detail, or a list of field errors.
function errorText(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => `${(x.loc || []).join(".")}: ${x.msg}`).join("; ");
  return e?.message || "Request failed";
}
const sans = "'DM Sans', sans-serif";

function Panel({ title, subtitle, onClose, children }) {
  const { colors: COLORS } = useAdminTheme();
  return (
    <section style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.borderActive || COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{title}</div>
          {subtitle && <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: mono, marginTop: 2 }}>{subtitle}</div>}
        </div>
        <ActionButton small variant="ghost" onClick={onClose}>Close</ActionButton>
      </div>
      {children}
    </section>
  );
}

function Label({ children }) {
  const { colors: COLORS } = useAdminTheme();
  return <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, fontFamily: mono, textTransform: "uppercase", letterSpacing: "0.06em" }}>{children}</div>;
}

const ROOM_FIELDS = new Set(["id", "zone", "name", "type", "depth", "group", "description", "exits", "features", "entity_spawns", "tags"]);

export function RoomDetail({ zoneId, slug, onClose, onOpenRoom }) {
  const { colors: COLORS } = useAdminTheme();
  const [detail, setDetail] = useState(null);
  const [live, setLive] = useState(null);
  const [error, setError] = useState(null);
  const [showYaml, setShowYaml] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, l] = await Promise.all([
        axios.get(`${API_BASE}/content/rooms/${zoneId}/${slug}`),
        axios.get(`${API_BASE}/world/rooms/${zoneId}/${slug}/state`).catch(() => null),
      ]);
      setError(null);
      setDetail(d.data);
      setLive(l?.data ?? null);
    } catch (e) {
      setError(errorText(e));
    }
  }, [zoneId, slug]);

  useEffect(() => {
    let alive = true;
    Promise.all([
      axios.get(`${API_BASE}/content/rooms/${zoneId}/${slug}`),
      axios.get(`${API_BASE}/world/rooms/${zoneId}/${slug}/state`).catch(() => null),
    ])
      .then(([d, l]) => {
        if (!alive) return;
        setDetail(d.data);
        setLive(l?.data ?? null);
      })
      .catch((e) => alive && setError(errorText(e)));
    return () => { alive = false; };
  }, [zoneId, slug]);

  const data = detail?.data || {};
  const exits = data.exits && typeof data.exits === "object" ? Object.entries(data.exits) : [];
  const features = Array.isArray(data.features) ? data.features : [];
  const spawns = Array.isArray(data.entity_spawns) ? data.entity_spawns : [];
  const extra = Object.fromEntries(Object.entries(data).filter(([k, v]) => !ROOM_FIELDS.has(k) && !(Array.isArray(v) && v.length === 0)));
  const problems = detail?.problems || { errors: [], warnings: [] };

  return (
    <Panel title={data.name || slug} subtitle={`${zoneId}:${slug}${data.type ? ` · ${data.type}` : ""}${data.depth != null ? ` · depth ${data.depth}` : ""}`} onClose={onClose}>
      <FetchErrorBanner error={error} label="room" />
      {detail?.parse_error && <div style={{ color: COLORS.danger, fontSize: 13, fontFamily: sans }}>This file is not valid YAML, so players see "You are in the void." here: {detail.parse_error}</div>}
      {(problems.errors.length > 0 || problems.warnings.length > 0) && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {problems.errors.map((p) => <div key={p} style={{ fontFamily: mono, fontSize: 12, color: COLORS.danger }}>error: {p}</div>)}
          {problems.warnings.map((p) => <div key={p} style={{ fontFamily: mono, fontSize: 12, color: COLORS.warning }}>warning: {p}</div>)}
        </div>
      )}
      {detail && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 18 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <Label>Description</Label>
              <p style={{ margin: "6px 0 0", fontSize: 13, lineHeight: 1.6, color: COLORS.text, fontFamily: sans, maxWidth: "65ch" }}>{data.description?.base || <em style={{ color: COLORS.textMuted }}>No description.</em>}</p>
              {Object.entries(data.description || {}).filter(([k]) => k !== "base").map(([k, v]) => (
                <p key={k} style={{ margin: "6px 0 0", fontSize: 12, color: COLORS.textMuted, fontFamily: sans }}><strong>{k}:</strong> {String(v)}</p>
              ))}
            </div>
            <div>
              <Label>Exits</Label>
              {exits.length === 0 && <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 6 }}>None.</div>}
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                {exits.map(([dir, ex]) => {
                  const dest = ex?.destination || "";
                  const [dz, ds] = dest.split(":");
                  return (
                    <div key={dir} style={{ fontSize: 13, fontFamily: sans, color: COLORS.text }}>
                      <strong style={{ fontFamily: mono }}>{dir}</strong> →{" "}
                      {ds ? <button type="button" onClick={() => onOpenRoom?.(dz, ds)} style={{ background: "none", border: "none", padding: 0, color: COLORS.accent, cursor: "pointer", fontFamily: mono, fontSize: 12 }}>{dest}</button> : <span style={{ fontFamily: mono }}>{dest || "—"}</span>}
                      {ex?.one_way && <Badge color={COLORS.info}>one-way</Badge>}
                      {ex?.description && <span style={{ color: COLORS.textMuted }}> · {ex.description}</span>}
                    </div>
                  );
                })}
              </div>
            </div>
            <div>
              <Label>Features</Label>
              {features.length === 0 && <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 6 }}>None.</div>}
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
                {features.map((f) => (
                  <div key={f.id || f.name} style={{ fontSize: 13, fontFamily: sans, color: COLORS.text }}>
                    <strong>{f.name}</strong> <span style={{ fontFamily: mono, fontSize: 11, color: COLORS.textDim }}>({(f.keywords || []).join(", ")})</span>
                    <div style={{ color: COLORS.textMuted, fontSize: 12 }}>{f.description}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <Label>Right now</Label>
              {!live && <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 6 }}>Live state unavailable.</div>}
              {live && (
                <div style={{ fontSize: 13, fontFamily: sans, color: COLORS.text, marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                  <span>Characters: {live.players.length ? live.players.join(", ") : <span style={{ color: COLORS.textMuted }}>none</span>}</span>
                  <span>Entities: {live.entities.length ? live.entities.map((e) => `${e.name || e.template} (${e.hp}/${e.max_hp})`).join(", ") : <span style={{ color: COLORS.textMuted }}>none</span>}</span>
                  <span>Items on the floor: {live.floor_items.length ? live.floor_items.map((i) => i.name || i.template || i.id).join(", ") : <span style={{ color: COLORS.textMuted }}>none</span>}</span>
                </div>
              )}
            </div>
            <div>
              <Label>Spawns</Label>
              {spawns.length === 0 && <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 6 }}>None.</div>}
              {spawns.map((s) => <div key={s.template} style={{ fontFamily: mono, fontSize: 12, color: COLORS.text, marginTop: 4 }}>{s.template} · chance {s.chance ?? 1} · max {s.max_count ?? 1}</div>)}
            </div>
            {Object.keys(extra).length > 0 && (
              <div>
                <Label>Plugin fields</Label>
                <pre style={{ margin: "6px 0 0", padding: 10, background: COLORS.bgInput, borderRadius: 6, fontSize: 11, fontFamily: mono, color: COLORS.text, overflowX: "auto", maxHeight: 220 }}>{JSON.stringify(extra, null, 2)}</pre>
              </div>
            )}
            {Array.isArray(data.tags) && data.tags.length > 0 && (
              <div><Label>Tags</Label><div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>{data.tags.map((t) => <Badge key={t}>{t}</Badge>)}</div></div>
            )}
          </div>
        </div>
      )}
      {detail && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, borderTop: `1px solid ${COLORS.border}`, paddingTop: 10 }}>
          <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: sans }}>Rooms, exits and features are edited in WorldForge; saves there reload here.</span>
          <div style={{ display: "flex", gap: 8 }}>
            <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={load}>Refresh</ActionButton>
            <ActionButton small variant="ghost" icon={<Icons.Code />} onClick={() => setShowYaml((v) => !v)}>{showYaml ? "Hide YAML" : "Show YAML"}</ActionButton>
          </div>
        </div>
      )}
      {showYaml && detail && (
        <pre style={{ margin: 0, padding: 12, background: COLORS.bgInput, borderRadius: 6, fontSize: 12, fontFamily: mono, color: COLORS.text, overflowX: "auto", maxHeight: 360 }}>{detail.yaml}</pre>
      )}
    </Panel>
  );
}

export function TemplateEditor({ kind, templateId, onClose, onSaved }) {
  const { colors: COLORS } = useAdminTheme();
  const label = kind === "entities" ? "Entity template" : "Item template";
  const [text, setText] = useState("");
  const [original, setOriginal] = useState("");
  const [error, setError] = useState(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Each template gets a fresh editor (keyed by id), so there is no earlier state to reset here.
    let alive = true;
    axios.get(`${API_BASE}/content/${kind}/${templateId}/yaml`)
      .then(({ data }) => { if (alive) { setText(data.yaml); setOriginal(data.yaml); } })
      .catch((e) => alive && setError(errorText(e)));
    return () => { alive = false; };
  }, [kind, templateId]);

  const dirty = text !== original;

  const save = async () => {
    setBusy(true);
    setError(null);
    setStatus("");
    try {
      await axios.put(`${API_BASE}/content/${kind}/${templateId}/yaml`, { path: `${kind}/${templateId}`, yaml_content: text });
      setOriginal(text);
      setStatus("Saved. The server reloads this template the next time it is used.");
      onSaved?.();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title={`${label}: ${templateId}`} subtitle={`content/world/${kind}/${templateId}.yaml`} onClose={onClose}>
      <textarea
        id={`template-${kind}-${templateId}`}
        aria-label={`${label} YAML`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        rows={Math.min(28, Math.max(10, text.split("\n").length + 1))}
        style={{ width: "100%", padding: 12, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontFamily: mono, fontSize: 12, lineHeight: 1.5, resize: "vertical" }}
      />
      {error && <div role="alert" style={{ fontSize: 12, color: COLORS.danger, fontFamily: mono, overflowWrap: "anywhere" }}>Not saved: {error}</div>}
      {status && <div style={{ fontSize: 12, color: COLORS.success, fontFamily: sans }}>{status}</div>}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: sans }}>Saving checks that the YAML parses, matches the {label.toLowerCase()} fields and keeps <code>id: {templateId}</code>.</span>
        <div style={{ display: "flex", gap: 8 }}>
          <ActionButton small variant="ghost" onClick={() => { setText(original); setError(null); }} disabled={!dirty || busy}>Discard changes</ActionButton>
          <ActionButton small variant="primary" icon={<Icons.Save />} onClick={save} disabled={!dirty || busy}>{busy ? "Saving…" : "Save"}</ActionButton>
        </div>
      </div>
    </Panel>
  );
}
