import ExtensionBlocks from "../components/ExtensionBlocks.jsx";
import { ALL_DIRECTIONS } from "../utils/worldSchema.js";
import { useMemo, useState } from "react";
import yaml from "js-yaml";
import { useTheme } from "../ThemeContext.jsx";
import SceneArtPanel from "../components/SceneArtPanel.jsx";
import { roomPanelChrome } from "./roomPanelChrome.js";

const TABS = ["General", "Scene", "Exits", "Features", "Plugins", "Entities", "YAML"];


export { roomPanelChrome };

export default function RoomPanel({
  bundleSceneArtIntoWorld = false,
  worldRoot = "",
  zoneId,
  roomSlug,
  room,
  groups,
  layoutBorderColor,
  layoutBorderColorMixed = false,
  layoutBorderAppliesToCount = 1,
  onLayoutBorderColorChange,
  onChangeRoom,
  onSave,
  onRevert,
  dirty,
  roomIndexForPicker,
  nexusUrl,
  nexusToken,
  roomTypes = [],
  exitDirs,
  worldSchema = null,
}) {
  const { colors: COLORS } = useTheme();
  const { lbl, inp, btn, btnPrimary, btnDanger } = useMemo(() => roomPanelChrome(COLORS), [COLORS]);
  function pill(active, onClick, children) {
    return (
      <button
        type="button"
        onClick={onClick}
        style={{
          padding: "4px 10px",
          borderRadius: 6,
          border: `1px solid ${active ? COLORS.accent : COLORS.border}`,
          background: active ? `${COLORS.accent}22` : COLORS.bgInput,
          color: active ? COLORS.accent : COLORS.textMuted,
          fontSize: 10,
          cursor: "pointer",
        }}
      >
        {children}
      </button>
    );
  }
  const [tab, setTab] = useState("General");
  const [yamlText, setYamlText] = useState("");
  const [yamlError, setYamlError] = useState("");
  const [colorClipboardHint, setColorClipboardHint] = useState("");

  const merged = room || {};

  const desc = merged.description && typeof merged.description === "object" ? merged.description : { base: "" };

  const updateField = (path, value) => {
    const next = JSON.parse(JSON.stringify(merged));
    if (path === "name") {
      next.name = value;
    } else if (path === "type") {
      next.type = value;
    } else if (path === "depth") {
      next.depth = Number(value) || 0;
    } else if (path === "group") {
      next.group = value || undefined;
    } else if (path === "description.base") {
      next.description = { ...(next.description || {}), base: value };
    } else if (path === "description.dawn") {
      next.description = { ...(next.description || {}), dawn: value };
    } else if (path === "description.dusk") {
      next.description = { ...(next.description || {}), dusk: value };
    } else if (path === "description.night") {
      next.description = { ...(next.description || {}), night: value };
    } else if (path === "area_image_url") {
      const v = String(value || "").trim();
      next.area_image_url = v || undefined;
    }
    onChangeRoom(next);
  };

  const exits = merged.exits && typeof merged.exits === "object" ? merged.exits : {};

  const setExit = (dir, patch) => {
    const next = JSON.parse(JSON.stringify(merged));
    next.exits = { ...(next.exits || {}) };
    next.exits[dir] = { destination: "", description: "", ...(next.exits[dir] || {}), ...patch };
    const ex = next.exits[dir];
    for (const k of Object.keys(ex)) {
      if (ex[k] === undefined) delete ex[k];
    }
    onChangeRoom(next);
  };

  const removeExit = (dir) => {
    const next = JSON.parse(JSON.stringify(merged));
    next.exits = { ...(next.exits || {}) };
    delete next.exits[dir];
    onChangeRoom(next);
  };

  const features = Array.isArray(merged.features) ? merged.features : [];
  const spawns = Array.isArray(merged.entity_spawns) ? merged.entity_spawns : [];

  const pickerOptions = useMemo(() => {
    const opts = [];
    for (const [z, rooms] of Object.entries(roomIndexForPicker || {})) {
      for (const slug of Object.keys(rooms || {})) {
        if (z === zoneId && slug === roomSlug) continue;
        const rid = rooms[slug]?.id || `${z}:${slug}`;
        opts.push({ z, slug, rid, label: `${z} → ${slug}` });
      }
    }
    return opts;
  }, [roomIndexForPicker, zoneId, roomSlug]);

  const copyLayoutBorderColor = async () => {
    const v = String(layoutBorderColor ?? "").trim();
    if (!v) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(v);
      } else {
        throw new Error("clipboard api");
      }
    } catch {
      const ta = document.createElement("textarea");
      ta.value = v;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setColorClipboardHint("Copied");
    window.setTimeout(() => setColorClipboardHint(""), 2000);
  };

  const normalizePastedHex = (raw) => {
    let s = String(raw ?? "").trim();
    if (!s) return null;
    s = s.replace(/\s+/g, "");
    if (!s.startsWith("#")) s = `#${s}`;
    if (!/^#[0-9A-Fa-f]{3,8}$/.test(s)) return null;
    return s;
  };

  const pasteLayoutBorderColor = async () => {
    if (!onLayoutBorderColorChange) return;
    let text = "";
    try {
      if (!navigator.clipboard?.readText) {
        setColorClipboardHint("No paste API");
        window.setTimeout(() => setColorClipboardHint(""), 2000);
        return;
      }
      text = await navigator.clipboard.readText();
    } catch {
      setColorClipboardHint("Paste blocked");
      window.setTimeout(() => setColorClipboardHint(""), 2000);
      return;
    }
    const hex = normalizePastedHex(text);
    if (!hex) {
      setColorClipboardHint("Invalid hex");
      window.setTimeout(() => setColorClipboardHint(""), 2000);
      return;
    }
    onLayoutBorderColorChange(hex);
    setColorClipboardHint("Pasted");
    window.setTimeout(() => setColorClipboardHint(""), 2000);
  };

  const nexusBase = (nexusUrl || "").replace(/\/$/, "");

  const forgeHeaders = () => {
    const h = { "Content-Type": "application/json" };
    if (nexusToken) h.Authorization = `Bearer ${nexusToken}`;
    return h;
  };

  const aiGenerate = async () => {
    if (!nexusUrl) return;
    const res = await fetch(`${nexusBase}/forge/generate`, {
      method: "POST",
      headers: forgeHeaders(),
      body: JSON.stringify({
        seed: `Describe ${merged.type} room depth ${merged.depth}`,
        room_type: merged.type || "chamber",
        depth: merged.depth || 1,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const parsed = data.data || yaml.load(data.yaml || "");
    if (parsed?.description?.base) {
      updateField("description.base", parsed.description.base);
    }
  };

  if (!roomSlug || !room) {
    return (
      <div style={{ padding: 24, color: COLORS.textMuted, fontSize: 13 }}>
        Select a room on the canvas.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: COLORS.bgPanel }}>
      <div style={{ display: "flex", gap: 4, padding: "8px 10px", borderBottom: `1px solid ${COLORS.border}`, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => {
              setTab(t);
              if (t === "YAML") setYamlText(yaml.dump(merged, { lineWidth: 120, quotingType: '"' }));
            }}
            style={{
              padding: "6px 10px",
              borderRadius: 6,
              border: "none",
              background: tab === t ? COLORS.bgHover : "transparent",
              color: tab === t ? COLORS.text : COLORS.textMuted,
              fontSize: 11,
              cursor: "pointer",
            }}
          >
            {t}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 12 }}>
        {tab === "General" && (
          <>
            <label style={lbl}>Display name</label>
            <input
              style={inp}
              value={merged.name ?? ""}
              onChange={(e) => updateField("name", e.target.value)}
            />
            <label style={lbl}>Type</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
              {(merged.type && !roomTypes.includes(merged.type) ? [...roomTypes, merged.type] : roomTypes).map((rt) =>
                pill(merged.type === rt, () => updateField("type", rt), rt)
              )}
            </div>
            <label style={lbl}>Depth</label>
            <input
              type="number"
              style={inp}
              value={merged.depth ?? 1}
              onChange={(e) => updateField("depth", e.target.value)}
            />
            {groups?.length ? (
              <>
                <label style={lbl}>Group</label>
                <select
                  style={inp}
                  value={merged.group || ""}
                  onChange={(e) => updateField("group", e.target.value || undefined)}
                >
                  <option value="">— None —</option>
                  {(groups || []).map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name || g.id}
                    </option>
                  ))}
                </select>
              </>
            ) : null}
            <label style={lbl}>Description (base)</label>
            <textarea style={{ ...inp, minHeight: 100, resize: "vertical" }} value={desc.base || ""} onChange={(e) => updateField("description.base", e.target.value)} />
            <button type="button" style={btnPrimary} onClick={() => aiGenerate().catch((e) => alert(e.message))} disabled={!nexusUrl}>
              AI Generate description
            </button>
            {onLayoutBorderColorChange ? (
              <>
                <label style={{ ...lbl, marginTop: 14 }}>Map border color (editor only)</label>
                <p style={{ fontSize: 10, color: COLORS.textDim, margin: "0 0 8px", lineHeight: 1.4 }}>
                  Stored in <code style={{ color: COLORS.accent }}>.positions.json</code>. Resize room boxes from corner handles when selected; save layout to persist size.
                  {layoutBorderAppliesToCount > 1 ? (
                    <> When several rooms are selected, changes apply to all {layoutBorderAppliesToCount} selected unlocked rooms.</>
                  ) : null}
                  {layoutBorderColorMixed ? (
                    <> Selected rooms use different border colors; the swatch shows a placeholder until you pick one.</>
                  ) : null}
                </p>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <input
                    type="color"
                    aria-label="Pick border color"
                    value={/^#[0-9A-Fa-f]{6}$/i.test(String(layoutBorderColor || "").trim()) ? layoutBorderColor.trim() : "#6b7280"}
                    onChange={(e) => onLayoutBorderColorChange(e.target.value)}
                    style={{ width: 44, height: 32, padding: 0, border: `1px solid ${COLORS.border}`, borderRadius: 6, cursor: "pointer", background: COLORS.bgInput }}
                  />
                  <input
                    style={{ ...inp, flex: 1, minWidth: 120, fontFamily: "monospace", fontSize: 11 }}
                    value={layoutBorderColor ?? ""}
                    placeholder="#aabbcc"
                    onChange={(e) => onLayoutBorderColorChange(e.target.value)}
                  />
                  <button
                    type="button"
                    style={{ ...btn, minWidth: 32, padding: "8px 10px" }}
                    title="Copy color (hex)"
                    disabled={!String(layoutBorderColor ?? "").trim()}
                    onClick={() => copyLayoutBorderColor().catch(() => {})}
                  >
                    C
                  </button>
                  <button
                    type="button"
                    style={{ ...btn, minWidth: 32, padding: "8px 10px" }}
                    title="Paste color from clipboard (#rgb or #rrggbb)"
                    onClick={() => pasteLayoutBorderColor().catch(() => {})}
                  >
                    P
                  </button>
                  <button
                    type="button"
                    style={{ ...btn, minWidth: 32, padding: "8px 10px" }}
                    title="Default (clear custom border)"
                    onClick={() => onLayoutBorderColorChange("")}
                  >
                    D
                  </button>
                  {colorClipboardHint ? (
                    <span style={{ fontSize: 10, color: COLORS.accent, fontWeight: 600 }}>{colorClipboardHint}</span>
                  ) : null}
                </div>
              </>
            ) : null}
            <details style={{ marginTop: 12 }}>
              <summary style={{ color: COLORS.textMuted, fontSize: 12, cursor: "pointer" }}>Time-of-day variants</summary>
              <label style={{ ...lbl, marginTop: 8 }}>Dawn</label>
              <textarea style={{ ...inp, minHeight: 48 }} value={desc.dawn || ""} onChange={(e) => updateField("description.dawn", e.target.value)} />
              <label style={lbl}>Dusk</label>
              <textarea style={{ ...inp, minHeight: 48 }} value={desc.dusk || ""} onChange={(e) => updateField("description.dusk", e.target.value)} />
              <label style={lbl}>Night</label>
              <textarea style={{ ...inp, minHeight: 48 }} value={desc.night || ""} onChange={(e) => updateField("description.night", e.target.value)} />
            </details>
          </>
        )}

        {tab === "Scene" && (
          <SceneArtPanel
            worldRoot={worldRoot}
            zoneId={zoneId}
            roomSlug={roomSlug}
            bundleSceneArtIntoWorld={bundleSceneArtIntoWorld}
            nexusUrl={nexusUrl}
            nexusToken={nexusToken}
            areaImageUrl={merged.area_image_url}
            onAreaImageUrlChange={(v) => updateField("area_image_url", v)}
            roomName={merged.name}
            roomType={merged.type}
            roomDepth={merged.depth}
            descriptionBase={desc.base}
          />
        )}

        {tab === "Exits" && (
          <div>
            <p style={{ fontSize: 11, color: COLORS.textMuted, margin: "0 0 12px", lineHeight: 1.45 }}>
              Pick a destination below, or drag from a <strong>door port</strong> (square on a room edge) to a port on another room — both directions are written at once.
            </p>
            {Object.entries(exits).map(([dir, ex]) => (
              <div key={dir} style={{ marginBottom: 10, padding: 8, background: COLORS.bgCard, borderRadius: 8 }}>
                <div style={{ fontWeight: 700, fontSize: 11, color: COLORS.accent, marginBottom: 6 }}>{dir}</div>
                <label style={lbl}>Destination</label>
                <input
                  style={inp}
                  value={ex.destination || ""}
                  onChange={(e) => setExit(dir, { destination: e.target.value })}
                />
                <select
                  style={{ ...inp, marginTop: 6 }}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v) setExit(dir, { destination: v });
                    e.target.value = "";
                  }}
                >
                  <option value="">Pick room…</option>
                  {pickerOptions.map((o) => (
                    <option key={o.rid} value={o.rid}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <label style={lbl}>Description</label>
                <input style={inp} value={ex.description || ""} onChange={(e) => setExit(dir, { description: e.target.value })} />
                <label style={lbl}>Map link label (editor)</label>
                <input
                  style={{ ...inp, fontFamily: "monospace", fontSize: 11 }}
                  value={ex.map_label ?? ""}
                  placeholder={`default: ${dir}`}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v.trim() === "") setExit(dir, { map_label: undefined });
                    else setExit(dir, { map_label: v });
                  }}
                />
                <p style={{ fontSize: 9, color: COLORS.textDim, margin: "4px 0 0", lineHeight: 1.35 }}>Shown on the zone map on this exit line; empty uses the direction name.</p>
                <label style={{ ...lbl, display: "flex", alignItems: "center", gap: 8 }}>
                  <input type="checkbox" checked={Boolean(ex.one_way)} onChange={(e) => setExit(dir, { one_way: e.target.checked })} />
                  One-way exit
                </label>
                <button type="button" style={{ ...btnDanger, marginTop: 6 }} onClick={() => removeExit(dir)}>
                  Remove exit
                </button>
              </div>
            ))}
            <AddExitForm
              existing={Object.keys(exits)}
              directions={exitDirs}
              onAdd={(dir) => setExit(dir, { destination: "", description: "" })}
            />
          </div>
        )}

        {tab === "Features" && (
          <FeatureList features={features} worldSchema={worldSchema} onChange={(nf) => onChangeRoom({ ...merged, features: nf })} />
        )}

        {tab === "Plugins" && (
          <ExtensionBlocks
            worldSchema={worldSchema}
            kind="room"
            doc={merged}
            onChange={(next) => onChangeRoom(next)}
            emptyNote="No enabled plugin adds fields to rooms in this world."
          />
        )}

        {tab === "Entities" && (
          <SpawnList spawns={spawns} onChange={(ns) => onChangeRoom({ ...merged, entity_spawns: ns })} />
        )}

        {tab === "YAML" && (
          <>
            <textarea style={{ ...inp, minHeight: 280, fontFamily: "monospace", fontSize: 11 }} value={yamlText} onChange={(e) => setYamlText(e.target.value)} />
            <button
              type="button"
              style={btnPrimary}
              onClick={() => {
                try {
                  onChangeRoom(yaml.load(yamlText));
                  setYamlError("");
                } catch (e) {
                  setYamlError(String(e?.message || e));
                }
              }}
            >
              Parse into form
            </button>
            {yamlError ? (
              <div style={{ color: COLORS.danger, fontSize: 11, marginTop: 6, whiteSpace: "pre-wrap" }}>
                YAML parse error: {yamlError}
              </div>
            ) : null}
          </>
        )}
      </div>

      <div style={{ padding: "10px 12px", borderTop: `1px solid ${COLORS.border}`, display: "flex", alignItems: "center", gap: 12 }}>
        {dirty ? (
          <span style={{ fontSize: 11, color: COLORS.warning }}>
            <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: COLORS.warning, marginRight: 6 }} />
            Unsaved
          </span>
        ) : (
          <span style={{ fontSize: 11, color: COLORS.textDim }}>Saved</span>
        )}
        <button type="button" style={btnPrimary} onClick={onSave}>
          Save
        </button>
        <button type="button" style={btn} onClick={onRevert}>
          Revert
        </button>
      </div>
    </div>
  );
}

function AddExitForm({ existing, onAdd, directions = ALL_DIRECTIONS }) {
  const { colors: COLORS } = useTheme();
  const { btn } = useMemo(() => roomPanelChrome(COLORS), [COLORS]);
  const dirs = directions.filter((d) => !existing.includes(d));
  if (!dirs.length) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <span style={{ fontSize: 11, color: COLORS.textMuted }}>Add exit: </span>
      {dirs.map((d) => (
        <button key={d} type="button" style={{ ...btn, marginRight: 6, marginTop: 4 }} onClick={() => onAdd(d)}>
          + {d}
        </button>
      ))}
    </div>
  );
}

function FeatureList({ features, onChange, worldSchema }) {
  const { colors: COLORS } = useTheme();
  const { lbl, inp, btnPrimary, btnDanger } = useMemo(() => roomPanelChrome(COLORS), [COLORS]);
  const add = () => onChange([...features, { id: `f_${Date.now()}`, name: "", keywords: [], description: "", interaction: "examine" }]);
  return (
    <div>
      {features.map((f, i) => (
        <div key={i} style={{ marginBottom: 10, padding: 8, background: COLORS.bgCard, borderRadius: 8 }}>
          <input style={inp} placeholder="id" value={f.id || ""} onChange={(e) => {
            const nf = [...features];
            nf[i] = { ...f, id: e.target.value };
            onChange(nf);
          }} />
          <input style={{ ...inp, marginTop: 4 }} placeholder="name" value={f.name || ""} onChange={(e) => {
            const nf = [...features];
            nf[i] = { ...f, name: e.target.value };
            onChange(nf);
          }} />
          <textarea style={{ ...inp, marginTop: 4 }} placeholder="description" value={f.description || ""} onChange={(e) => {
            const nf = [...features];
            nf[i] = { ...f, description: e.target.value };
            onChange(nf);
          }} />
          <input style={{ ...inp, marginTop: 4 }} placeholder="interaction" value={f.interaction || ""} onChange={(e) => {
            const nf = [...features];
            nf[i] = { ...f, interaction: e.target.value };
            onChange(nf);
          }} />
          <div style={{ marginTop: 6 }}>
            <ExtensionBlocks
              worldSchema={worldSchema}
              kind="feature"
              doc={f}
              onChange={(next) => {
                const nf = [...features];
                nf[i] = next;
                onChange(nf);
              }}
            />
          </div>
          <button type="button" style={btnDanger} onClick={() => onChange(features.filter((_, j) => j !== i))}>
            Remove
          </button>
        </div>
      ))}
      <button type="button" style={btnPrimary} onClick={add}>
        + Feature
      </button>
    </div>
  );
}

function SpawnList({ spawns, onChange }) {
  const { colors: COLORS } = useTheme();
  const { lbl, inp, btnPrimary, btnDanger } = useMemo(() => roomPanelChrome(COLORS), [COLORS]);
  const add = () => onChange([...spawns, { template: "", chance: 1, max_count: 1 }]);
  return (
    <div>
      {spawns.map((s, i) => (
        <div key={i} style={{ marginBottom: 10, padding: 8, background: COLORS.bgCard, borderRadius: 8 }}>
          <input style={inp} placeholder="template id" value={s.template || ""} onChange={(e) => {
            const ns = [...spawns];
            ns[i] = { ...s, template: e.target.value };
            onChange(ns);
          }} />
          <label style={lbl}>Chance</label>
          <input type="number" step={0.1} style={inp} value={s.chance ?? 1} onChange={(e) => {
            const ns = [...spawns];
            ns[i] = { ...s, chance: Number(e.target.value) };
            onChange(ns);
          }} />
          <label style={lbl}>Max count</label>
          <input type="number" style={inp} value={s.max_count ?? 1} onChange={(e) => {
            const ns = [...spawns];
            ns[i] = { ...s, max_count: Number(e.target.value) };
            onChange(ns);
          }} />
          <button type="button" style={btnDanger} onClick={() => onChange(spawns.filter((_, j) => j !== i))}>
            Remove
          </button>
        </div>
      ))}
      <button type="button" style={btnPrimary} onClick={add}>
        + Spawn
      </button>
    </div>
  );
}
