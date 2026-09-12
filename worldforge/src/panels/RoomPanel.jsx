import { useCallback, useEffect, useMemo, useState } from "react";
import yaml from "js-yaml";
import { useTheme } from "../ThemeContext.jsx";
import { joinPaths } from "../utils/paths.js";
import * as fs from "../utils/fsBridge.js";

const TABS = ["General", "Scene", "Exits", "Features", "Hazards", "Entities", "YAML"];

const roomTypes = ["chamber", "corridor", "junction", "alcove", "descent", "danger", "safe", "boss", "hub", "command", "engineering", "airlock"];

/** Nexus /play/comfyui/status: checkpoint_name hint only for workflows that use CheckpointLoaderSimple. */
function comfySuggestCheckpointNameToml(status) {
  if (!status || typeof status !== "object") return false;
  if (status.area_workflow_uses_checkpoint_loader === false) return false;
  const ap = String(status.area_workflow_path || "").replace(/\\/g, "/");
  if (
    ap.endsWith("comfyui_area_workflow.json") &&
    status.area_workflow_uses_checkpoint_loader === undefined
  ) {
    return false;
  }
  if (status.suggest_checkpoint_name_in_toml === true) return true;
  if (status.suggest_checkpoint_name_in_toml === false) return false;
  return status.area_ready === true && status.checkpoint_name_set === false;
}

function roomPanelChrome(COLORS) {
  const lbl = { display: "block", fontSize: 10, color: COLORS.textMuted, marginBottom: 4, marginTop: 8 };
  const inp = {
    width: "100%",
    boxSizing: "border-box",
    padding: "8px 10px",
    borderRadius: 6,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgInput,
    color: COLORS.text,
    fontSize: 12,
  };
  const btn = {
    padding: "8px 14px",
    borderRadius: 6,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgCard,
    color: COLORS.text,
    cursor: "pointer",
    fontSize: 12,
  };
  return {
    lbl,
    inp,
    btn,
    btnPrimary: { ...btn, background: `${COLORS.accent}33`, borderColor: COLORS.accent },
    btnDanger: { ...btn, color: COLORS.danger, borderColor: COLORS.danger },
  };
}

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
  shipMode,
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
  const [areaPrompt, setAreaPrompt] = useState("");
  const [comfyStatus, setComfyStatus] = useState(null);
  const [areaBusy, setAreaBusy] = useState(false);
  const [areaDebug, setAreaDebug] = useState("");
  const [comfyRefreshTick, setComfyRefreshTick] = useState(0);
  const [sceneGallery, setSceneGallery] = useState([]);
  const [galleryLoading, setGalleryLoading] = useState(false);
  const [galleryTick, setGalleryTick] = useState(0);

  const refreshSceneGallery = useCallback(() => setGalleryTick((t) => t + 1), []);

  const appendAreaDebug = useCallback((msg) => {
    const line = `${new Date().toLocaleTimeString([], { hour12: false })} ${msg}`;
    console.info("[WorldForge scene art]", line);
    setAreaDebug((prev) => {
      const next = (prev ? `${prev}\n` : "") + line;
      const lines = next.split("\n");
      return lines.length > 50 ? lines.slice(-50).join("\n") : next;
    });
  }, []);

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
  const hazards = Array.isArray(merged.hazards) ? merged.hazards : [];
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

  useEffect(() => {
    setAreaPrompt("");
  }, [roomSlug, zoneId]);

  useEffect(() => {
    setComfyRefreshTick(0);
    setComfyStatus(null);
  }, [nexusBase]);

  useEffect(() => {
    if (comfyRefreshTick === 0) return;
    if (!nexusBase) {
      setComfyStatus(null);
      appendAreaDebug("(no Nexus URL — set in Settings)");
      return;
    }
    let cancelled = false;
    (async () => {
      const url = `${nexusBase}/play/comfyui/status`;
      appendAreaDebug(`GET ${url}`);
      try {
        const r = await fetch(url);
        const text = await r.text();
        let j = {};
        try {
          j = JSON.parse(text);
        } catch {
          appendAreaDebug(`status HTTP ${r.status} non-JSON: ${text.slice(0, 200)}`);
        }
        if (!cancelled && j && typeof j === "object") {
          setComfyStatus(j);
          appendAreaDebug(
            `status HTTP ${r.status} → area_workflow=${j.area_workflow_path || "?"} uses_ckpt_loader=${j.area_workflow_uses_checkpoint_loader} suggest_ckpt_toml=${j.suggest_checkpoint_name_in_toml} reachable=${j.comfy_reachable}`
          );
        }
      } catch (e) {
        if (!cancelled) {
          setComfyStatus(null);
          appendAreaDebug(`status fetch error: ${e?.message || e}`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nexusBase, comfyRefreshTick, appendAreaDebug]);

  useEffect(() => {
    if (tab !== "Scene") return;
    let cancelled = false;
    (async () => {
      setGalleryLoading(true);
      try {
        const entries = [];
        const cur = String(merged.area_image_url || "").trim();

        if (bundleSceneArtIntoWorld && worldRoot && zoneId && roomSlug) {
          const artDir = joinPaths(worldRoot, "zones", zoneId, "rooms", "art");
          const flat = joinPaths(artDir, `${roomSlug}.png`);
          if (await fs.pathExists(flat).catch(() => false)) {
            entries.push({
              key: `flat:${roomSlug}`,
              url: `/media/room-art/${zoneId}/${roomSlug}.png`,
              filePath: flat,
              deletable: true,
              label: `${roomSlug}.png (legacy)`,
            });
          }
          const sub = joinPaths(artDir, roomSlug);
          const list = await fs.listDir(sub).catch(() => []);
          for (const ent of list) {
            if (ent.is_dir || !String(ent.name).toLowerCase().endsWith(".png")) continue;
            entries.push({
              key: `v:${ent.name}`,
              url: `/media/room-art/${zoneId}/${roomSlug}/v/${ent.name}`,
              filePath: ent.path,
              deletable: true,
              label: ent.name,
            });
          }
          entries.sort((a, b) => {
            if (a.key.startsWith("flat")) return 1;
            if (b.key.startsWith("flat")) return -1;
            return b.label.localeCompare(a.label);
          });
          const urls = new Set(entries.map((e) => e.url));
          if (cur && cur.startsWith("/") && !urls.has(cur)) {
            entries.unshift({
              key: `orphan:${cur}`,
              url: cur,
              filePath: null,
              deletable: false,
              label: "Linked in YAML (file not under art folder)",
            });
          }
        } else if (cur && cur.startsWith("/")) {
          entries.push({
            key: "runtime",
            url: cur,
            filePath: null,
            deletable: false,
            label: "Current URL (ship/runtime — delete file on server if needed)",
          });
        }

        if (!cancelled) setSceneGallery(entries);
      } finally {
        if (!cancelled) setGalleryLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, bundleSceneArtIntoWorld, worldRoot, zoneId, roomSlug, galleryTick, merged.area_image_url]);

  const deleteSceneImage = async (item) => {
    if (!item?.deletable || !item.filePath) {
      alert("This image has no local file path (or is protected). Clear the URL in YAML or pick another.");
      return;
    }
    if (!window.confirm(`Delete ${item.label} from disk?`)) return;
    try {
      await fs.deleteFile(item.filePath);
      appendAreaDebug(`Gallery: deleted ${item.filePath}`);
      if (String(merged.area_image_url || "").trim() === item.url) {
        updateField("area_image_url", "");
      }
      refreshSceneGallery();
    } catch (e) {
      alert(e?.message || String(e));
    }
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

  const fmtApiError = (data) => {
    const d = data?.detail;
    if (Array.isArray(d)) return d.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join("; ");
    if (typeof d === "string") return d;
    if (d && typeof d === "object") return JSON.stringify(d);
    return data?.error || JSON.stringify(data || {});
  };

  const suggestAreaImagePrompt = async () => {
    if (!nexusBase) {
      appendAreaDebug("Suggest: blocked — no Nexus URL");
      alert("Set Nexus URL in Settings.");
      return;
    }
    const url = `${nexusBase}/forge/generate-area-prompt`;
    appendAreaDebug(`Suggest: POST ${url} (auth=${nexusToken ? "Bearer ***" : "none"})`);
    setAreaBusy(true);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: forgeHeaders(),
        body: JSON.stringify({
          room_name: merged.name || roomSlug,
          room_type: merged.type || "chamber",
          depth: merged.depth || 1,
          description_base: desc.base || "",
        }),
      });
      const rawText = await res.text();
      appendAreaDebug(`Suggest: HTTP ${res.status} body(${rawText.length} chars) ${rawText.slice(0, 280)}${rawText.length > 280 ? "…" : ""}`);
      let data = {};
      try {
        data = JSON.parse(rawText);
      } catch {
        throw new Error(`Not JSON: ${rawText.slice(0, 120)}`);
      }
      if (!res.ok) throw new Error(fmtApiError(data) || res.statusText);
      if (!data.ok || !data.prompt) throw new Error(fmtApiError(data) || "No prompt returned");
      setAreaPrompt(data.prompt);
      appendAreaDebug(`Suggest: ok, prompt length ${data.prompt.length}`);
    } catch (e) {
      appendAreaDebug(`Suggest: ERROR ${e?.message || e}`);
      alert(e.message || String(e));
    } finally {
      setAreaBusy(false);
    }
  };

  const generateAreaImage = async () => {
    appendAreaDebug("Generate: click");
    if (!nexusBase) {
      appendAreaDebug("Generate: blocked — no Nexus URL");
      alert("Set Nexus URL in Settings.");
      return;
    }
    const p = areaPrompt.trim();
    if (p.length < 3) {
      appendAreaDebug(`Generate: blocked — prompt too short (${p.length} chars)`);
      alert("Enter or generate an image prompt (at least 3 characters).");
      return;
    }
    appendAreaDebug(
      `Generate: comfyStatus=${JSON.stringify(comfyStatus || {})} area_ready=${comfyStatus?.area_ready === true}`
    );
    if (comfyStatus && comfyStatus.area_ready !== true) {
      appendAreaDebug(
        "Generate: server says ComfyUI not ready — check comfyui.toml enabled=true and workflow file on Nexus host (see status line above). Still attempting POST in case status is stale."
      );
    }
    if (comfySuggestCheckpointNameToml(comfyStatus)) {
      appendAreaDebug(
        "Generate: set checkpoint_name in config/comfyui.toml (Nexus host) — area workflow uses CheckpointLoaderSimple / example template."
      );
    }
    const awf = String(comfyStatus?.area_workflow_path || "").replace(/\\/g, "/");
    if (awf.includes("example.json") && comfyStatus?.area_ready) {
      appendAreaDebug(
        `Generate: area_workflow_path ends with example JSON — ComfyUI node 4 is often CheckpointLoaderSimple + model.safetensors. Use config/comfyui_area_workflow.json (Z-Image graph) or set checkpoint_name.`
      );
    }
    const url = `${nexusBase}/forge/room-area-image`;
    const bundle = Boolean(bundleSceneArtIntoWorld && zoneId && roomSlug);
    appendAreaDebug(
      `Generate: POST ${url} promptLen=${p.length} bundle=${bundle} auth=${nexusToken ? "Bearer ***" : "none"}`
    );
    setAreaBusy(true);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: forgeHeaders(),
        body: JSON.stringify(
          bundle
            ? { prompt: p, zone_id: zoneId, room_slug: roomSlug }
            : { prompt: p }
        ),
      });
      const rawText = await res.text();
      appendAreaDebug(`Generate: HTTP ${res.status} body(${rawText.length} chars) ${rawText.slice(0, 400)}${rawText.length > 400 ? "…" : ""}`);
      let data = {};
      try {
        data = JSON.parse(rawText);
      } catch {
        throw new Error(`Not JSON: ${rawText.slice(0, 160)}`);
      }
      if (!res.ok) throw new Error(fmtApiError(data) || res.statusText);
      if (!data.ok || !data.area_image_url) throw new Error(fmtApiError(data) || "No image URL");
      updateField("area_image_url", data.area_image_url);
      refreshSceneGallery();
      appendAreaDebug(
        `Generate: ok → ${data.area_image_url}${data.bundled ? " (zones/…/rooms/art/<room>/ — save room YAML)" : ""}`
      );
    } catch (e) {
      appendAreaDebug(`Generate: ERROR ${e?.message || e}`);
      alert(e.message || String(e));
    } finally {
      setAreaBusy(false);
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
              {roomTypes.map((rt) =>
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
            {!shipMode && onLayoutBorderColorChange ? (
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
          <div>
            <p style={{ fontSize: 10, color: COLORS.textDim, margin: "0 0 10px", lineHeight: 1.45 }}>
              <strong>Player UI</strong> uses <code style={{ color: COLORS.accent }}>area_image_url</code> on this room. In zones, new PNGs go under{" "}
              <code style={{ color: COLORS.accent }}>zones/&lt;zone&gt;/rooms/art/&lt;room&gt;/gen_*.png</code>; pick one below and <strong>Save</strong> the room.
            </p>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 8,
                marginBottom: 10,
                padding: "8px 10px",
                borderRadius: 8,
                border: `1px solid ${COLORS.border}`,
                background: COLORS.bgCard,
              }}
            >
              <span
                title={
                  comfyRefreshTick === 0
                    ? "Status is fetched only when you click Check connection (or rely on Generate errors)."
                    : comfyStatus?.enabled
                      ? comfyStatus?.comfy_reachable
                        ? "Nexus reached ComfyUI HTTP API (/system_stats or /queue)"
                        : comfyStatus?.comfy_ping_error || "ComfyUI not reachable"
                      : "ComfyUI integration disabled in comfyui.toml"
                }
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  flexShrink: 0,
                  background:
                    comfyRefreshTick === 0
                      ? COLORS.textDim
                      : !comfyStatus || comfyStatus.enabled === false
                        ? COLORS.textDim
                        : comfyStatus.comfy_reachable
                          ? COLORS.success
                          : COLORS.danger,
                  boxShadow: `0 0 6px ${
                    comfyRefreshTick === 0 || !comfyStatus || comfyStatus.enabled === false
                      ? "transparent"
                      : comfyStatus.comfy_reachable
                        ? `${COLORS.success}88`
                        : `${COLORS.danger}88`
                  }`,
                }}
              />
              <div style={{ flex: "1 1 140px", minWidth: 0 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.text }}>
                  {comfyRefreshTick === 0
                    ? "ComfyUI: not probed yet"
                    : !comfyStatus
                      ? "ComfyUI: …"
                      : comfyStatus.enabled === false
                        ? "ComfyUI off (comfyui.toml)"
                        : comfyStatus.comfy_reachable
                          ? "ComfyUI API reachable"
                          : "ComfyUI API not reachable"}
                </div>
                <div style={{ fontSize: 10, color: COLORS.textDim, wordBreak: "break-word", marginTop: 2 }}>
                  {comfyRefreshTick === 0 ? (
                    <span>Optional — Check connection before Generate, or generate and use the debug log.</span>
                  ) : null}
                  {comfyRefreshTick > 0 && comfyStatus?.enabled && comfyStatus?.base_url ? (
                    <span style={{ fontFamily: "monospace" }}>{comfyStatus.base_url}</span>
                  ) : null}
                  {comfyRefreshTick > 0 &&
                  comfyStatus?.enabled &&
                  comfyStatus?.comfy_reachable === false &&
                  comfyStatus?.comfy_ping_error ? (
                    <span> — {comfyStatus.comfy_ping_error}</span>
                  ) : null}
                </div>
              </div>
              <button
                type="button"
                style={{ ...btn, padding: "6px 12px", fontSize: 10 }}
                disabled={!nexusBase || areaBusy}
                onClick={() => setComfyRefreshTick((n) => n + 1)}
                title="Re-fetch /play/comfyui/status from Nexus"
              >
                Check connection
              </button>
            </div>
            {comfyStatus?.enabled && comfyStatus?.area_ready && comfySuggestCheckpointNameToml(comfyStatus) ? (
              <p
                style={{
                  fontSize: 10,
                  color: COLORS.warning,
                  margin: "0 0 8px",
                  lineHeight: 1.45,
                  padding: "8px 10px",
                  borderRadius: 8,
                  border: `1px solid ${COLORS.warning}55`,
                  background: `${COLORS.warning}14`,
                }}
              >
                Set <code style={{ color: COLORS.accent }}>checkpoint_name</code> in{" "}
                <code style={{ color: COLORS.accent }}>config/comfyui.toml</code> on the machine running Nexus (exact filename from{" "}
                <code style={{ color: COLORS.accent }}>ComfyUI/models/checkpoints/</code>
                ). Without it, example templates still use <code style={{ color: COLORS.accent }}>model.safetensors</code> and ComfyUI returns HTTP 400.
              </p>
            ) : null}
            <label style={lbl}>Image prompt</label>
            <textarea
              style={{ ...inp, minHeight: 64, resize: "vertical" }}
              value={areaPrompt}
              onChange={(e) => setAreaPrompt(e.target.value)}
              placeholder="e.g. wide shot, derelict corridor, violet emergency strips, volumetric haze, cinematic sci-fi interior"
            />
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
              <button
                type="button"
                style={btnPrimary}
                disabled={!nexusUrl || areaBusy}
                onClick={() => suggestAreaImagePrompt()}
                title="Uses server LLM (LM Studio) to draft a ComfyUI-style prompt from name, type, and description"
              >
                {areaBusy ? "…" : "Suggest prompt (LLM)"}
              </button>
              <button
                type="button"
                style={{
                  ...btnPrimary,
                  opacity: comfyStatus?.area_ready === true ? 1 : 0.75,
                  borderColor: comfyStatus?.area_ready === true ? COLORS.accent : COLORS.warning,
                }}
                disabled={!nexusUrl || areaBusy}
                onClick={() => generateAreaImage()}
                title={
                  comfyStatus?.area_ready
                    ? "Run ComfyUI and set this image as the active scene"
                    : "ComfyUI may be off — click anyway to see debug log / server error"
                }
              >
                {areaBusy ? "…" : "Generate image (ComfyUI)"}
              </button>
            </div>

            <label style={{ ...lbl, marginTop: 4 }}>Gallery — pick scene for this room</label>
            <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }}>
              <button
                type="button"
                style={{ ...btn, padding: "4px 10px", fontSize: 10 }}
                disabled={!bundleSceneArtIntoWorld || !worldRoot}
                onClick={() => refreshSceneGallery()}
                title={!worldRoot ? "Open a content folder to scan art files" : "Rescan zones/…/rooms/art/"}
              >
                Refresh gallery
              </button>
              {galleryLoading ? <span style={{ fontSize: 10, color: COLORS.textDim }}>Loading…</span> : null}
            </div>
            {bundleSceneArtIntoWorld && !worldRoot ? (
              <p style={{ fontSize: 10, color: COLORS.warning, marginBottom: 8 }}>Open a world content folder in WorldForge to list and delete bundled PNGs.</p>
            ) : null}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                gap: 10,
                marginBottom: 12,
              }}
            >
              {sceneGallery.map((item) => {
                const active = String(merged.area_image_url || "").trim() === item.url;
                const src = nexusBase && item.url.startsWith("/") ? `${nexusBase}${item.url}` : null;
                return (
                  <div
                    key={item.key}
                    style={{
                      borderRadius: 8,
                      border: `2px solid ${active ? COLORS.accent : COLORS.border}`,
                      padding: 8,
                      background: COLORS.bgCard,
                    }}
                  >
                    <div style={{ fontSize: 9, color: COLORS.textMuted, marginBottom: 4, wordBreak: "break-all" }}>
                      {item.label}
                      {active ? (
                        <span style={{ color: COLORS.accent, fontWeight: 700, marginLeft: 4 }}>· active</span>
                      ) : null}
                    </div>
                    {src ? (
                      <img
                        alt=""
                        src={src}
                        style={{
                          width: "100%",
                          height: 100,
                          objectFit: "cover",
                          borderRadius: 4,
                          border: `1px solid ${COLORS.border}`,
                          marginBottom: 6,
                        }}
                      />
                    ) : (
                      <div style={{ height: 100, background: COLORS.bgInput, borderRadius: 4, marginBottom: 6 }} />
                    )}
                    <button
                      type="button"
                      style={{ ...btnPrimary, width: "100%", padding: "4px 6px", fontSize: 10, marginBottom: 4 }}
                      disabled={active}
                      onClick={() => {
                        updateField("area_image_url", item.url);
                      }}
                    >
                      Use for scene
                    </button>
                    <button
                      type="button"
                      style={{ ...btnDanger, width: "100%", padding: "4px 6px", fontSize: 10 }}
                      disabled={!item.deletable}
                      onClick={() => deleteSceneImage(item)}
                    >
                      Delete file
                    </button>
                  </div>
                );
              })}
            </div>
            {sceneGallery.length === 0 && !galleryLoading ? (
              <p style={{ fontSize: 10, color: COLORS.textDim, marginBottom: 10 }}>No images yet — generate one or add a legacy flat PNG under art/.</p>
            ) : null}

            <label style={lbl}>Active URL (YAML)</label>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
              <input
                style={{ ...inp, flex: 1, minWidth: 160, fontSize: 11, fontFamily: "monospace" }}
                value={merged.area_image_url || ""}
                onChange={(e) => updateField("area_image_url", e.target.value)}
                placeholder="/media/room-art/… or /media/rooms/…"
              />
              <button type="button" style={btn} onClick={() => updateField("area_image_url", "")}>
                Clear URL
              </button>
            </div>
            {nexusBase && merged.area_image_url && String(merged.area_image_url).startsWith("/") ? (
              <img
                alt="Active scene preview"
                src={`${nexusBase}${merged.area_image_url}`}
                style={{ maxWidth: "100%", maxHeight: 220, borderRadius: 8, border: `1px solid ${COLORS.border}`, marginBottom: 10 }}
              />
            ) : null}

            <details style={{ marginBottom: 10, fontSize: 10 }}>
              <summary style={{ color: COLORS.warning, cursor: "pointer", userSelect: "none" }}>
                Scene art debug log (DevTools → [WorldForge scene art])
              </summary>
              <div style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center" }}>
                <button type="button" style={{ ...btn, padding: "4px 10px", fontSize: 10 }} onClick={() => setAreaDebug("")}>
                  Clear log
                </button>
                <span style={{ color: COLORS.textDim }}>Status: {comfyStatus ? JSON.stringify(comfyStatus) : "—"}</span>
              </div>
              <pre
                style={{
                  marginTop: 6,
                  padding: 8,
                  maxHeight: 160,
                  overflow: "auto",
                  background: COLORS.bgCard,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 6,
                  color: COLORS.textMuted,
                  fontSize: 10,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {areaDebug || "(no events yet)"}
              </pre>
            </details>
          </div>
        )}

        {tab === "Exits" && (
          <div>
            {!shipMode ? (
              <p style={{ fontSize: 11, color: COLORS.textMuted, margin: "0 0 12px", lineHeight: 1.45 }}>
                Pick a destination below, or drag from a <strong>door port</strong> (square on a room edge) to a port on another room — both directions are written at once.
              </p>
            ) : null}
            {Object.entries(exits).map(([dir, ex]) => (
              <div key={dir} style={{ marginBottom: 10, padding: 8, background: COLORS.bgCard, borderRadius: 8 }}>
                <div style={{ fontWeight: 700, fontSize: 11, color: COLORS.accent, marginBottom: 6 }}>{dir}</div>
                <label style={lbl}>Destination {shipMode ? "(self:slug or @airlock)" : ""}</label>
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
                {!shipMode ? (
                  <>
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
                  </>
                ) : null}
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
              onAdd={(dir) => setExit(dir, { destination: "", description: "" })}
            />
          </div>
        )}

        {tab === "Features" && (
          <FeatureList features={features} onChange={(nf) => onChangeRoom({ ...merged, features: nf })} />
        )}

        {tab === "Hazards" && (
          <HazardList hazards={hazards} onChange={(nh) => onChangeRoom({ ...merged, hazards: nh })} />
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

function AddExitForm({ existing, onAdd }) {
  const { colors: COLORS } = useTheme();
  const { btn } = useMemo(() => roomPanelChrome(COLORS), [COLORS]);
  const dirs = [
    "north",
    "south",
    "east",
    "west",
    "northeast",
    "northwest",
    "southeast",
    "southwest",
    "up",
    "down",
  ].filter((d) => !existing.includes(d));
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

function FeatureList({ features, onChange }) {
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

function HazardList({ hazards, onChange }) {
  const { colors: COLORS } = useTheme();
  const { lbl, inp, btnPrimary, btnDanger } = useMemo(() => roomPanelChrome(COLORS), [COLORS]);
  const add = () => onChange([...hazards, { id: `h_${Date.now()}`, type: "trap", severity: 1, description: "" }]);
  return (
    <div>
      {hazards.map((h, i) => (
        <div key={i} style={{ marginBottom: 10, padding: 8, background: COLORS.bgCard, borderRadius: 8 }}>
          <input style={inp} value={h.id || ""} onChange={(e) => {
            const nh = [...hazards];
            nh[i] = { ...h, id: e.target.value };
            onChange(nh);
          }} />
          <input style={{ ...inp, marginTop: 4 }} value={h.type || ""} onChange={(e) => {
            const nh = [...hazards];
            nh[i] = { ...h, type: e.target.value };
            onChange(nh);
          }} />
          <input type="range" min={1} max={5} value={h.severity || 1} onChange={(e) => {
            const nh = [...hazards];
            nh[i] = { ...h, severity: Number(e.target.value) };
            onChange(nh);
          }} />
          <textarea style={{ ...inp, marginTop: 4 }} value={h.description || ""} onChange={(e) => {
            const nh = [...hazards];
            nh[i] = { ...h, description: e.target.value };
            onChange(nh);
          }} />
          <button type="button" style={btnDanger} onClick={() => onChange(hazards.filter((_, j) => j !== i))}>
            Remove
          </button>
        </div>
      ))}
      <button type="button" style={btnPrimary} onClick={add}>
        + Hazard
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
