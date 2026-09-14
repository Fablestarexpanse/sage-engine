import { useCallback, useEffect, useMemo, useState } from "react";
import { useTheme } from "../ThemeContext.jsx";
import { joinPaths } from "../utils/paths.js";
import * as fs from "../utils/fsBridge.js";
import { roomPanelChrome } from "../panels/roomPanelChrome.js";

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

function fmtApiError(data) {
  const d = data?.detail;
  if (Array.isArray(d)) return d.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join("; ");
  if (typeof d === "string") return d;
  if (d && typeof d === "object") return JSON.stringify(d);
  return data?.error || JSON.stringify(data || {});
}

/**
 * ComfyUI scene-art subsystem for the room panel's "Scene" tab: status polling,
 * LLM prompt suggestion, image generation, and the bundled-art gallery
 * (scan/select/delete). Extracted out of RoomPanel.jsx, which renders this in
 * the same tab position and owns which room/tab is active.
 *
 * Props:
 * - worldRoot, zoneId, roomSlug: room identity, used for fs paths and API calls.
 * - bundleSceneArtIntoWorld: whether generated art is bundled under
 *   zones/<zone>/rooms/art/<room>/ vs. kept server-side.
 * - nexusUrl, nexusToken: Nexus API base + auth for forge endpoints.
 * - areaImageUrl: current room.area_image_url.
 * - onAreaImageUrlChange(url): called when a gallery image is selected, an
 *   image is generated, the URL is edited directly, or cleared.
 * - roomName, roomType, roomDepth, descriptionBase: room fields used to seed
 *   the LLM prompt-suggestion request.
 */
export default function SceneArtPanel({
  worldRoot = "",
  zoneId,
  roomSlug,
  bundleSceneArtIntoWorld = false,
  nexusUrl,
  nexusToken,
  areaImageUrl,
  onAreaImageUrlChange,
  roomName,
  roomType,
  roomDepth,
  descriptionBase,
}) {
  const { colors: COLORS } = useTheme();
  const { lbl, inp, btn, btnPrimary, btnDanger } = useMemo(() => roomPanelChrome(COLORS), [COLORS]);

  const [areaPrompt, setAreaPrompt] = useState("");
  const [comfyStatus, setComfyStatus] = useState(null);
  const [areaBusy, setAreaBusy] = useState(false);
  const [areaDebug, setAreaDebug] = useState("");
  const [comfyRefreshTick, setComfyRefreshTick] = useState(0);
  const [sceneGallery, setSceneGallery] = useState([]);
  const [galleryLoading, setGalleryLoading] = useState(false);
  const [galleryTick, setGalleryTick] = useState(0);

  const nexusBase = (nexusUrl || "").replace(/\/$/, "");

  const forgeHeaders = () => {
    const h = { "Content-Type": "application/json" };
    if (nexusToken) h.Authorization = `Bearer ${nexusToken}`;
    return h;
  };

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
    let cancelled = false;
    (async () => {
      setGalleryLoading(true);
      try {
        const entries = [];
        const cur = String(areaImageUrl || "").trim();

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
            label: "Current URL (runtime — delete file on server if needed)",
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
  }, [bundleSceneArtIntoWorld, worldRoot, zoneId, roomSlug, galleryTick, areaImageUrl]);

  const deleteSceneImage = async (item) => {
    if (!item?.deletable || !item.filePath) {
      alert("This image has no local file path (or is protected). Clear the URL in YAML or pick another.");
      return;
    }
    if (!window.confirm(`Delete ${item.label} from disk?`)) return;
    try {
      await fs.deleteFile(item.filePath);
      appendAreaDebug(`Gallery: deleted ${item.filePath}`);
      if (String(areaImageUrl || "").trim() === item.url) {
        onAreaImageUrlChange("");
      }
      refreshSceneGallery();
    } catch (e) {
      alert(e?.message || String(e));
    }
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
          room_name: roomName || roomSlug,
          room_type: roomType || "chamber",
          depth: roomDepth || 1,
          description_base: descriptionBase || "",
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
      onAreaImageUrlChange(data.area_image_url);
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

  return (
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
          const active = String(areaImageUrl || "").trim() === item.url;
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
                  onAreaImageUrlChange(item.url);
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
          value={areaImageUrl || ""}
          onChange={(e) => onAreaImageUrlChange(e.target.value)}
          placeholder="/media/room-art/… or /media/rooms/…"
        />
        <button type="button" style={btn} onClick={() => onAreaImageUrlChange("")}>
          Clear URL
        </button>
      </div>
      {nexusBase && areaImageUrl && String(areaImageUrl).startsWith("/") ? (
        <img
          alt="Active scene preview"
          src={`${nexusBase}${areaImageUrl}`}
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
  );
}
