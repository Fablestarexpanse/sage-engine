import { useState, useEffect, useRef, useCallback } from "react";
import { usePlayTheme } from "../PlayThemeContext.jsx";
import { EntitySpan } from "./02-entity.jsx";
import {
  playSuggestScenePrompt,
  playListSceneGallery,
  playApplySceneFromGallery,
  playMediaUrl,
} from "../playApi.js";

const LS_PORTRAIT_BACKDROP_ON = "sage_narrative_portrait_backdrop_on";
const LS_PORTRAIT_BACKDROP_OPACITY = "sage_narrative_portrait_backdrop_opacity";
const LS_PORTRAIT_BACKDROP_SCALE = "sage_narrative_portrait_backdrop_scale";
const LS_PORTRAIT_BACKDROP_X_OFFSET = "sage_narrative_portrait_backdrop_x_offset";

function readPortraitBackdropOnFromLs() {
  try {
    const s = localStorage.getItem(LS_PORTRAIT_BACKDROP_ON);
    if (s === "0") return false;
    if (s === "1") return true;
  } catch {
    /* ignore */
  }
  return true;
}

const PORTRAIT_BACKDROP_OPACITY_MIN = 4;
const PORTRAIT_BACKDROP_OPACITY_MAX = 92;

function readPortraitBackdropOpacityFromLs() {
  try {
    const n = parseInt(localStorage.getItem(LS_PORTRAIT_BACKDROP_OPACITY), 10);
    if (Number.isFinite(n)) {
      return Math.max(PORTRAIT_BACKDROP_OPACITY_MIN, Math.min(PORTRAIT_BACKDROP_OPACITY_MAX, n));
    }
  } catch {
    /* ignore */
  }
  return 26;
}

const PORTRAIT_BACKDROP_SCALE_MIN = 45;
const PORTRAIT_BACKDROP_SCALE_MAX = 275;

function readPortraitBackdropScaleFromLs() {
  try {
    const n = parseInt(localStorage.getItem(LS_PORTRAIT_BACKDROP_SCALE), 10);
    if (Number.isFinite(n)) return Math.max(PORTRAIT_BACKDROP_SCALE_MIN, Math.min(PORTRAIT_BACKDROP_SCALE_MAX, n));
  } catch {
    /* ignore */
  }
  return 100;
}

const PORTRAIT_BACKDROP_X_OFFSET_MIN = -45;
const PORTRAIT_BACKDROP_X_OFFSET_MAX = 45;

function readPortraitBackdropXOffsetFromLs() {
  try {
    const n = parseInt(localStorage.getItem(LS_PORTRAIT_BACKDROP_X_OFFSET), 10);
    if (Number.isFinite(n)) {
      return Math.max(PORTRAIT_BACKDROP_X_OFFSET_MIN, Math.min(PORTRAIT_BACKDROP_X_OFFSET_MAX, n));
    }
  } catch {
    /* ignore */
  }
  return 0;
}

export const DEFAULT_NARRATIVE = [
  { type: "system", text: "— Connected —", ts: "" },
];

export function stripMudMarkup(text) {
  if (text == null || text === "") return "";
  return String(text).replace(/\|(\w+):([^:|]+):[^|]+\|/g, "$2");
}

/** Recent narrative lines → plain text for scene / LLM context (newest paragraphs last). */
export function buildSceneNarrativeContext(lines, maxLen = 4000) {
  const chunks = [];
  let size = 0;
  for (let idx = lines.length - 1; idx >= 0; idx--) {
    const l = lines[idx];
    let t = "";
    switch (l.type) {
      case "raw":
      case "server_message":
        t = l.text;
        break;
      case "room_title":
        t = l.text;
        break;
      case "room_desc":
        t = l.text;
        break;
      case "response":
        t = l.text;
        break;
      case "entity":
        t = l.text;
        break;
      case "glyph_cast":
        t = l.text;
        break;
      case "action":
        t = l.text ? String(l.text).replace(/^>\s*/, "").replace(/^Command sent:\s*/i, "") : "";
        break;
      case "staff_notice":
        t = l.text || "";
        break;
      default:
        break;
    }
    if (!t) continue;
    t = stripMudMarkup(t).trim();
    if (!t) continue;
    const block = t + "\n\n";
    if (size + block.length > maxLen) break;
    chunks.unshift(block.trimEnd());
    size += block.length;
  }
  return chunks.join("\n\n").trim();
}

export function lastRoomTitleHint(lines) {
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i]?.type === "room_title" && lines[i].text) return String(lines[i].text).trim();
  }
  return "";
}

function SceneGalleryModal({ onClose, sceneGen }) {
  const { T } = usePlayTheme();
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(true);
  const [err, setErr] = useState("");
  const [applyingId, setApplyingId] = useState(null);

  const cid = sceneGen?.characterId;
  const load = useCallback(async () => {
    if (!sceneGen) return;
    setErr("");
    setBusy(true);
    try {
      const res = await playListSceneGallery(sceneGen.username, sceneGen.getPassword());
      if (!res.ok) {
        const map = {
          invalid_credentials: "Session expired — sign in again.",
        };
        setErr(map[res.error] || res.detail || res.error || "Could not load gallery");
        setItems([]);
        return;
      }
      setItems(Array.isArray(res.items) ? res.items : []);
    } catch (e) {
      setErr(e.message || "Could not load gallery");
      setItems([]);
    } finally {
      setBusy(false);
    }
  }, [sceneGen]);

  useEffect(() => {
    load();
  }, [load]);

  const applyOne = async (galleryId) => {
    if (cid == null || cid < 1) {
      setErr("No character selected.");
      return;
    }
    setErr("");
    setApplyingId(galleryId);
    try {
      const res = await playApplySceneFromGallery(
        sceneGen.username,
        sceneGen.getPassword(),
        galleryId,
        cid
      );
      if (!res.ok) {
        const map = {
          invalid_credentials: "Session expired — sign in again.",
          gallery_item_not_found: "That image is no longer in your gallery.",
          character_not_owned: "Character not found on your account.",
          invalid_stored_url: "That image cannot be used.",
        };
        setErr(map[res.error] || res.detail || res.error || "Could not apply image");
        return;
      }
      if (res.scene_image_url) {
        sceneGen.onSceneGenerated?.(res.scene_image_url);
        onClose();
      }
    } catch (e) {
      setErr(e.message || "Could not apply image");
    } finally {
      setApplyingId(null);
    }
  };

  if (!sceneGen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="My scene art"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 4000,
        background: "rgba(6,6,10,0.88)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        boxSizing: "border-box",
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 720,
          maxHeight: "90vh",
          overflow: "auto",
          borderRadius: T.radius.xl,
          border: `1px solid ${T.border.medium}`,
          background: T.bg.panel,
          boxShadow: T.shadow.panel,
          padding: "18px 18px 14px",
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h3 style={{ fontFamily: T.font.display, fontSize: 15, color: T.text.primary, margin: "0 0 6px" }}>
          My scene art
        </h3>
        <p style={{ fontSize: 11, color: T.text.muted, margin: "0 0 12px", lineHeight: 1.45 }}>
          Images you have generated with ComfyUI on this account. Pick one to show it in the Scene panel for{" "}
          <strong style={{ color: T.text.secondary }}>this character</strong> (no extra cost).
        </p>
        {cid == null || cid < 1 ? (
          <p role="alert" style={{ fontSize: 11, color: T.text.danger, margin: "0 0 10px" }}>
            Select a character to apply a saved scene.
          </p>
        ) : null}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12, alignItems: "center" }}>
          <button
            type="button"
            disabled={busy}
            onClick={load}
            style={{
              padding: "6px 12px",
              borderRadius: T.radius.md,
              border: `1px solid ${T.border.dim}`,
              background: T.bg.surface,
              color: T.text.muted,
              fontSize: 10,
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {busy ? "Loading…" : "Refresh"}
          </button>
        </div>
        {err ? (
          <div role="alert" style={{ fontSize: 11, color: T.text.danger, marginBottom: 10 }}>
            {err}
          </div>
        ) : null}
        {busy && items.length === 0 ? (
          <p style={{ fontSize: 11, color: T.text.muted }}>Loading your images…</p>
        ) : null}
        {!busy && items.length === 0 ? (
          <p style={{ fontSize: 12, color: T.text.secondary, lineHeight: 1.5 }}>
            No saved scene images yet. Use <strong style={{ color: T.text.accent }}>Scene art (ComfyUI)</strong> to generate one; new images appear here automatically.
          </p>
        ) : null}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
            gap: 10,
          }}
        >
          {items.map((it) => {
            const src = playMediaUrl(it.image_url, it.id);
            const when = it.created_at
              ? (() => {
                  try {
                    const d = new Date(it.created_at);
                    return Number.isNaN(d.getTime()) ? it.created_at : d.toLocaleString();
                  } catch {
                    return it.created_at;
                  }
                })()
              : "";
            const who = it.character_name ? String(it.character_name) : "";
            const preview = (it.prompt_preview || "").trim();
            return (
              <div
                key={it.id}
                style={{
                  borderRadius: T.radius.md,
                  border: `1px solid ${T.border.subtle}`,
                  overflow: "hidden",
                  background: T.bg.surface,
                  display: "flex",
                  flexDirection: "column",
                }}
              >
                <div
                  style={{
                    aspectRatio: "4 / 3",
                    background: T.bg.deep,
                    position: "relative",
                  }}
                >
                  {src ? (
                    <img
                      src={src}
                      alt=""
                      loading="lazy"
                      style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                    />
                  ) : null}
                </div>
                <div style={{ padding: "8px 8px 10px", flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
                  {when ? (
                    <div style={{ fontSize: 9, color: T.text.muted, fontFamily: T.font.mono }}>{when}</div>
                  ) : null}
                  {who ? (
                    <div style={{ fontSize: 9, color: T.text.secondary }}>As: {who}</div>
                  ) : null}
                  {preview ? (
                    <div
                      style={{
                        fontSize: 9,
                        color: T.text.muted,
                        lineHeight: 1.35,
                        maxHeight: 36,
                        overflow: "hidden",
                      }}
                      title={preview}
                    >
                      {preview}
                    </div>
                  ) : null}
                  <button
                    type="button"
                    disabled={cid == null || cid < 1 || applyingId != null}
                    onClick={() => applyOne(it.id)}
                    style={{
                      marginTop: "auto",
                      padding: "6px 8px",
                      borderRadius: T.radius.sm,
                      border: "none",
                      background:
                        cid != null && cid >= 1 && applyingId == null
                          ? `linear-gradient(135deg,${T.hue.violet},${T.hue.cyan})`
                          : T.bg.void,
                      color: cid != null && cid >= 1 && applyingId == null ? "#0a0a0f" : T.text.muted,
                      fontSize: 9,
                      fontWeight: 700,
                      cursor: cid != null && cid >= 1 && applyingId == null ? "pointer" : "not-allowed",
                    }}
                  >
                    {applyingId === it.id ? "Applying…" : "Use in Scene"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: "7px 12px",
              borderRadius: T.radius.md,
              border: `1px solid ${T.border.medium}`,
              background: "transparent",
              color: T.text.muted,
              fontSize: 10,
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function SceneArtModal({ onClose, lines, sceneGen }) {
  const { T } = usePlayTheme();
  const [prompt, setPrompt] = useState("");
  const [err, setErr] = useState("");
  const [busyS, setBusyS] = useState(true);
  /** idle → user must confirm spend; confirm → showing spend confirmation */
  const [costStep, setCostStep] = useState("idle");

  const lab = sceneGen.currencyLabel || "credits";
  const cost = typeof sceneGen.areaGenerationCost === "number" ? sceneGen.areaGenerationCost : 3;
  const economyOn = sceneGen.economyEnabled !== false;
  const bal = sceneGen.aiCredits;
  const willCharge = economyOn && cost > 0;
  const broke = willCharge && typeof bal === "number" && bal < cost;
  const afterBal = typeof bal === "number" && willCharge ? Math.max(0, bal - cost) : null;

  useEffect(() => {
    setCostStep("idle");
  }, [prompt]);

  const refillFromNarrative = useCallback(() => {
    setErr("");
    setPrompt(buildSceneNarrativeContext(lines, 5000));
  }, [lines]);

  const runSuggest = useCallback(async () => {
    setErr("");
    setBusyS(true);
    const roomHint = lastRoomTitleHint(lines);
    const ctx = buildSceneNarrativeContext(lines, 8000);
    const fallback = buildSceneNarrativeContext(lines, 5000);
    try {
      const res = await playSuggestScenePrompt(
        sceneGen.username,
        sceneGen.getPassword(),
        ctx,
        roomHint
      );
      if (!res.ok) {
        const map = {
          llm_prompt_too_short: "The model returned an empty prompt — add a bit more narrative or type a scene line.",
          llm_failed: "LLM unavailable — check LM Studio / Ollama or config/llm.toml on Nexus.",
          invalid_credentials: "Session expired — sign in again.",
        };
        setErr(map[res.error] || res.detail || res.error || "Suggest failed");
        setPrompt(fallback);
        return;
      }
      if (res.prompt) setPrompt(res.prompt);
    } catch (e) {
      setErr(e.message || "Suggest failed");
      setPrompt(fallback);
    } finally {
      setBusyS(false);
    }
  }, [lines, sceneGen]);

  useEffect(() => {
    let cancelled = false;
    setPrompt("");
    setErr("");
    setBusyS(true);
    const roomHint = lastRoomTitleHint(lines);
    const ctx = buildSceneNarrativeContext(lines, 8000);
    const fallback = buildSceneNarrativeContext(lines, 5000);
    (async () => {
      try {
        const res = await playSuggestScenePrompt(
          sceneGen.username,
          sceneGen.getPassword(),
          ctx,
          roomHint
        );
        if (cancelled) return;
        if (!res.ok) {
          const map = {
            llm_prompt_too_short: "The model returned an empty prompt — raw narrative is shown below; edit and try Generate or Rebuild.",
            llm_failed: "LM Studio / LLM unreachable from Nexus — raw narrative is shown below; fix config/llm.toml or edit the prompt manually.",
            invalid_credentials: "Session expired — sign in again.",
          };
          setErr(map[res.error] || res.detail || res.error || "LLM request failed");
          setPrompt(fallback);
          return;
        }
        if (res.prompt) setPrompt(res.prompt);
      } catch (e) {
        if (!cancelled) {
          setErr(e.message || "LLM request failed");
          setPrompt(fallback);
        }
      } finally {
        if (!cancelled) setBusyS(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Snapshot lines at open; modal remounts when reopened (key).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!sceneGen) return null;

  const roomHint = lastRoomTitleHint(lines);
  const disabled = busyS;

  const kickOffBackgroundGenerate = () => {
    const p = prompt.trim();
    if (p.length < 3) {
      setErr("Enter at least a few words for the image prompt.");
      return;
    }
    if (typeof sceneGen.beginBackgroundSceneGenerate !== "function") {
      setErr("Background generation is not available — reload the player client.");
      return;
    }
    setErr("");
    setCostStep("idle");
    sceneGen.beginBackgroundSceneGenerate(p);
    onClose();
  };

  const startGenerateFlow = () => {
    const p = prompt.trim();
    if (p.length < 3) {
      setErr("Enter at least a few words for the image prompt.");
      return;
    }
    setErr("");
    if (broke) {
      setErr(
        `You need ${cost} ${lab} for this scene; you have ${bal}. Use “How to get more” below or ask your server host to add ${lab} to your account.`
      );
      return;
    }
    if (willCharge) {
      setCostStep("confirm");
      return;
    }
    kickOffBackgroundGenerate();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Generate scene art"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 4000,
        background: "rgba(6,6,10,0.88)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        boxSizing: "border-box",
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 520,
          maxHeight: "90vh",
          overflow: "auto",
          borderRadius: T.radius.xl,
          border: `1px solid ${T.border.medium}`,
          background: T.bg.panel,
          boxShadow: T.shadow.panel,
          padding: "18px 18px 14px",
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h3 style={{ fontFamily: T.font.display, fontSize: 15, color: T.text.primary, margin: "0 0 6px" }}>
          Scene from narrative
        </h3>
        <p style={{ fontSize: 11, color: T.text.muted, margin: "0 0 12px", lineHeight: 1.45 }}>
          Recent narrative is sent to Nexus, which runs your <strong style={{ color: T.text.secondary }}>LM Studio</strong> (or configured LLM) to build a ComfyUI-style prompt. When you generate, this dialog closes and the <strong style={{ color: T.text.secondary }}>Scene</strong> panel shows progress until ComfyUI finishes.
        </p>
        {roomHint ? (
          <p style={{ fontSize: 10, color: T.text.muted, margin: "0 0 8px" }}>
            Last room title: <span style={{ color: T.text.accent }}>{roomHint}</span>
          </p>
        ) : null}
        {!sceneGen.areaReady ? (
          <p role="status" style={{ fontSize: 11, color: T.text.danger, margin: "0 0 10px" }}>
            Area workflow not ready — enable ComfyUI and ensure <code style={{ fontSize: 10 }}>area_workflow_path</code> exists on Nexus.
          </p>
        ) : null}
        {sceneGen.areaReady ? (
          <div
            style={{
              marginBottom: 12,
              padding: "10px 12px",
              borderRadius: T.radius.md,
              border: `1px solid ${T.currency.art.border}`,
              background: `linear-gradient(135deg, ${T.currency.art.bg}, ${T.bg.surface})`,
            }}
          >
            <div style={{ fontSize: 9, fontWeight: 700, color: T.currency.art.label, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
              Art wallet (account)
            </div>
            <div style={{ fontSize: 12, color: T.text.primary, lineHeight: 1.5, fontFamily: T.font.body }}>
              {typeof bal === "number" ? (
                <>
                  You have <strong style={{ color: T.currency.art.fg, fontFamily: T.font.mono }}>{bal}</strong> {lab}.
                </>
              ) : (
                <>Balance will be checked on the server when you generate.</>
              )}
            </div>
            {willCharge ? (
              <div style={{ fontSize: 12, color: T.text.secondary, marginTop: 6, lineHeight: 1.45 }}>
                One scene image costs{" "}
                <strong style={{ color: T.currency.art.fg, fontFamily: T.font.mono }}>{cost}</strong> {lab}.
                {afterBal != null ? (
                  <>
                    {" "}
                    After a successful run you would have <strong style={{ fontFamily: T.font.mono }}>{afterBal}</strong> {lab}.
                  </>
                ) : null}
              </div>
            ) : (
              <div style={{ fontSize: 11, color: T.text.muted, marginTop: 6 }}>
                Art economy is off or this generation is free — no {lab} will be charged.
              </div>
            )}
            {broke ? (
              <p role="alert" style={{ fontSize: 11, color: T.text.danger, margin: "8px 0 0" }}>
                Not enough {lab} to generate. Add more before continuing.
              </p>
            ) : null}
            <button
              type="button"
              onClick={() => sceneGen.onCreditsHelp?.()}
              style={{
                marginTop: 8,
                padding: "5px 10px",
                borderRadius: T.radius.sm,
                border: `1px solid ${T.currency.art.border}`,
                background: T.bg.deep,
                color: T.currency.art.fg,
                fontSize: 10,
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: T.font.body,
              }}
            >
              How to get more {lab}
            </button>
          </div>
        ) : null}
        {costStep === "confirm" && willCharge ? (
          <div
            role="status"
            style={{
              marginBottom: 12,
              padding: "12px 14px",
              borderRadius: T.radius.md,
              border: `1px solid ${T.border.accent}`,
              background: T.hue.violetDim,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 700, color: T.text.primary, marginBottom: 6 }}>Confirm spend</div>
            <p style={{ fontSize: 12, color: T.text.secondary, margin: 0, lineHeight: 1.5 }}>
              Spend <strong style={{ color: T.currency.art.fg }}>{cost}</strong> {lab} to run ComfyUI and replace the Scene panel image? This cannot be undone; if ComfyUI fails, Nexus may refund automatically. The dialog will close and progress shows on the Scene panel.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
              <button
                type="button"
                onClick={kickOffBackgroundGenerate}
                style={{
                  padding: "7px 14px",
                  borderRadius: T.radius.md,
                  border: "none",
                  background: `linear-gradient(135deg,${T.hue.violet},${T.hue.cyan})`,
                  color: "#0a0a0f",
                  fontSize: 10,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                {`Yes — spend ${cost} ${lab} and generate`}
              </button>
              <button
                type="button"
                onClick={() => setCostStep("idle")}
                style={{
                  padding: "7px 12px",
                  borderRadius: T.radius.md,
                  border: `1px solid ${T.border.medium}`,
                  background: T.bg.surface,
                  color: T.text.muted,
                  fontSize: 10,
                  cursor: "pointer",
                }}
              >
                Go back
              </button>
            </div>
          </div>
        ) : null}
        {busyS ? (
          <p role="status" style={{ fontSize: 11, color: T.text.accent, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 8 }}>
            <span
              className="sage-portrait-spin"
              style={{
                width: 14,
                height: 14,
                borderRadius: "50%",
                border: `2px solid ${T.border.dim}`,
                borderTopColor: T.hue.violet,
                flexShrink: 0,
              }}
            />
            Sending narrative to LM Studio (via Nexus) to build the image prompt…
          </p>
        ) : null}
        <label style={{ display: "block", fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
          Image prompt (edit freely)
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={10}
          disabled={disabled}
          placeholder={busyS ? "" : "Prompt from LLM appears here…"}
          style={{
            width: "100%",
            boxSizing: "border-box",
            marginBottom: 10,
            padding: "10px 12px",
            borderRadius: T.radius.md,
            border: `1px solid ${T.border.medium}`,
            background: T.bg.surface,
            color: T.text.primary,
            fontFamily: T.font.body,
            fontSize: 12,
            lineHeight: 1.45,
            resize: "vertical",
            minHeight: 160,
          }}
        />
        {err ? (
          <div role="alert" style={{ fontSize: 11, color: T.text.danger, marginBottom: 10 }}>
            {err}
          </div>
        ) : null}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "flex-end" }}>
          <button
            type="button"
            disabled={disabled}
            onClick={refillFromNarrative}
            style={{
              padding: "7px 12px",
              borderRadius: T.radius.md,
              border: `1px solid ${T.border.dim}`,
              background: T.bg.surface,
              color: T.text.muted,
              fontSize: 10,
              cursor: disabled ? "wait" : "pointer",
            }}
          >
            Fill from narrative
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => runSuggest()}
            style={{
              padding: "7px 12px",
              borderRadius: T.radius.md,
              border: `1px solid ${T.border.accent}`,
              background: T.hue.violetDim,
              color: T.text.primary,
              fontSize: 10,
              cursor: disabled ? "wait" : "pointer",
            }}
          >
            {busyS ? "LLM…" : "Rebuild prompt (LLM)"}
          </button>
          <button
            type="button"
            disabled={disabled || !sceneGen.areaReady || broke || costStep === "confirm"}
            onClick={startGenerateFlow}
            title={
              !sceneGen.areaReady
                ? "Area ComfyUI workflow not configured"
                : broke
                  ? `Need ${cost} ${lab}`
                  : willCharge
                    ? "Review cost, then confirm"
                    : "Run ComfyUI — progress appears in the Scene panel"
            }
            style={{
              padding: "7px 14px",
              borderRadius: T.radius.md,
              border: "none",
              background:
                sceneGen.areaReady && !disabled && !broke && costStep !== "confirm"
                  ? `linear-gradient(135deg,${T.hue.violet},${T.hue.cyan})`
                  : T.bg.void,
              color: sceneGen.areaReady && !disabled && !broke && costStep !== "confirm" ? "#0a0a0f" : T.text.muted,
              fontSize: 10,
              fontWeight: 700,
              cursor: sceneGen.areaReady && !disabled && !broke && costStep !== "confirm" ? "pointer" : "not-allowed",
            }}
          >
            {willCharge ? `Generate (${cost} ${lab})…` : "Generate in background"}
          </button>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: "7px 12px",
              borderRadius: T.radius.md,
              border: `1px solid ${T.border.medium}`,
              background: "transparent",
              color: T.text.muted,
              fontSize: 10,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export function NarrativePanel({
  onContextMenu,
  lines,
  sceneGen,
  portraitBackdropUrl = null,
  openSceneGallerySignal = 0,
}) {
  const { mode, T } = usePlayTheme();
  const scrollRef = useRef(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [showTimestamps, setShowTimestamps] = useState(true);
  const [sceneModalOpen, setSceneModalOpen] = useState(false);
  const [sceneModalKey, setSceneModalKey] = useState(0);
  const [galleryModalOpen, setGalleryModalOpen] = useState(false);
  const [galleryModalKey, setGalleryModalKey] = useState(0);
  const [portraitBackdropOn, setPortraitBackdropOn] = useState(readPortraitBackdropOnFromLs);
  const [portraitBackdropOpacity, setPortraitBackdropOpacity] = useState(readPortraitBackdropOpacityFromLs);
  const [portraitBackdropScale, setPortraitBackdropScale] = useState(readPortraitBackdropScaleFromLs);
  const [portraitBackdropXOffset, setPortraitBackdropXOffset] = useState(readPortraitBackdropXOffsetFromLs);

  const narrativePortraitScrim =
    mode === "dark"
      ? "linear-gradient(90deg, rgba(8,9,12,0.97) 0%, rgba(8,9,12,0.9) 30%, rgba(8,9,12,0.52) 50%, rgba(8,9,12,0.16) 66%, transparent 80%)"
      : "linear-gradient(90deg, rgba(232,234,242,0.98) 0%, rgba(232,234,242,0.92) 30%, rgba(232,234,242,0.55) 50%, rgba(232,234,242,0.18) 66%, transparent 80%)";

  const togglePortraitBackdrop = useCallback(() => {
    setPortraitBackdropOn((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(LS_PORTRAIT_BACKDROP_ON, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const onPortraitBackdropOpacityChange = useCallback((e) => {
    const v = +e.target.value;
    const clamped = Math.max(
      PORTRAIT_BACKDROP_OPACITY_MIN,
      Math.min(PORTRAIT_BACKDROP_OPACITY_MAX, Number.isFinite(v) ? v : 26)
    );
    setPortraitBackdropOpacity(clamped);
    try {
      localStorage.setItem(LS_PORTRAIT_BACKDROP_OPACITY, String(clamped));
    } catch {
      /* ignore */
    }
  }, []);

  const onPortraitBackdropScaleChange = useCallback((e) => {
    const v = +e.target.value;
    const clamped = Math.max(
      PORTRAIT_BACKDROP_SCALE_MIN,
      Math.min(PORTRAIT_BACKDROP_SCALE_MAX, Number.isFinite(v) ? v : 100)
    );
    setPortraitBackdropScale(clamped);
    try {
      localStorage.setItem(LS_PORTRAIT_BACKDROP_SCALE, String(clamped));
    } catch {
      /* ignore */
    }
  }, []);

  const onPortraitBackdropXOffsetChange = useCallback((e) => {
    const v = +e.target.value;
    const clamped = Math.max(
      PORTRAIT_BACKDROP_X_OFFSET_MIN,
      Math.min(PORTRAIT_BACKDROP_X_OFFSET_MAX, Number.isFinite(v) ? v : 0)
    );
    setPortraitBackdropXOffset(clamped);
    try {
      localStorage.setItem(LS_PORTRAIT_BACKDROP_X_OFFSET, String(clamped));
    } catch {
      /* ignore */
    }
  }, []);

  // Follow new output only while the reader is already at the bottom; someone
  // scrolled up into history keeps their place.
  const stickToBottomRef = useRef(true);
  const onNarrativeScroll = useCallback((e) => {
    const el = e.currentTarget;
    stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  }, []);
  useEffect(() => {
    if (scrollRef.current && stickToBottomRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [lines]);
  // Content can grow after the lines effect (late layout, merged lines), so
  // also follow DOM changes while pinned to the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof MutationObserver === "undefined") return undefined;
    const obs = new MutationObserver(() => {
      if (stickToBottomRef.current) el.scrollTop = el.scrollHeight;
    });
    obs.observe(el, { childList: true, subtree: true, characterData: true });
    return () => obs.disconnect();
  }, []);
  useEffect(() => {
    if (!sceneGen || !openSceneGallerySignal) return;
    setGalleryModalKey((k) => k + 1);
    setGalleryModalOpen(true);
  }, [openSceneGallerySignal, sceneGen]);

  const parseEntities = (text) => {
    const parts = text.split(/(\|[^|]+\|)/g);
    return parts.map((part, i) => {
      const match = part.match(/^\|(\w+):([^:]+):([^|]+)\|$/);
      if (match) return <EntitySpan key={i} type={match[1]} name={match[2]} id={match[3]} onContextMenu={onContextMenu}>{match[2]}</EntitySpan>;
      return <span key={i}>{part}</span>;
    });
  };

  const Ts = ({ ts }) => showTimestamps && ts ? <span style={{ color: T.text.muted, opacity: 0.35, fontSize: 10, fontFamily: T.font.mono, marginRight: 6, minWidth: 48, display: "inline-block" }}>{ts}</span> : null;

  const renderLine = (line, i) => {
    const base = { fontFamily: T.font.mono, fontSize: 13, lineHeight: 1.7, padding: "1px 14px" };
    switch (line.type) {
      case "system": return <div key={i} role="status" style={{ ...base, color: T.text.muted, fontStyle: "italic", fontSize: 11 }}><Ts ts={line.ts} />{line.text}</div>;
      case "raw": return <div key={i} style={{ ...base, color: T.text.narrative, fontFamily: T.font.body, fontSize: 13, whiteSpace: "pre-wrap" }}>{line.text}</div>;
      case "server_message": {
        const raw = line.text != null ? String(line.text) : "";
        const m = raw.match(/^\[Server\]\s*(.*)$/is);
        const body = ((m ? m[1] : raw) || "").trim() || raw.replace(/^\[Server\]\s*/i, "").trim() || raw;
        return (
          <div
            key={i}
            role="status"
            aria-live="polite"
            style={{
              ...base,
              margin: "10px 14px",
              padding: "12px 14px 14px",
              borderRadius: T.radius.md,
              borderLeft: `4px solid ${T.text.info}`,
              background: mode === "dark" ? "rgba(96,165,250,0.14)" : "rgba(37,99,235,0.1)",
              border: `1px solid ${mode === "dark" ? "rgba(96,165,250,0.42)" : "rgba(37,99,235,0.32)"}`,
              boxShadow:
                mode === "dark"
                  ? "0 0 0 1px rgba(96,165,250,0.06), 0 6px 20px rgba(0,0,0,0.22)"
                  : "0 2px 10px rgba(37,99,235,0.12)",
            }}
          >
            <div
              style={{
                fontFamily: T.font.display,
                fontSize: 10,
                fontWeight: 800,
                letterSpacing: "0.14em",
                color: T.text.info,
                marginBottom: 8,
                textTransform: "uppercase",
              }}
            >
              Server broadcast
            </div>
            <div
              style={{
                fontFamily: T.font.body,
                fontSize: 14,
                fontWeight: 600,
                lineHeight: 1.55,
                color: T.text.primary,
                whiteSpace: "pre-wrap",
              }}
            >
              {body}
            </div>
          </div>
        );
      }
      case "room_title": return (
        <div key={i} style={{ padding: "10px 14px 2px", display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontFamily: T.font.display, fontSize: 18, fontWeight: 700, color: T.text.accent }}>{line.text.split("—")[0].trim()}</span>
          {line.text.includes("—") && <span style={{ fontFamily: T.font.body, fontSize: 11, color: T.text.muted }}>{line.text.split("—").slice(1).join("—").trim()}</span>}
        </div>
      );
      case "room_desc": return <div key={i} style={{ ...base, color: T.text.narrative, fontFamily: T.font.body, fontSize: 14, lineHeight: 1.75, padding: "4px 14px 8px" }}>{parseEntities(line.text)}</div>;
      case "exits": return (
        <div key={i} style={{ ...base, padding: "4px 14px 8px", fontSize: 12 }}>
          <span style={{ color: T.text.muted }}>Exits: </span>
          {line.exits.map((ex, j) => (
            <span key={j}>
              {j > 0 && <span style={{ color: T.text.muted, margin: "0 6px" }}>·</span>}
              <EntitySpan type="exit" name={ex.label} id={ex.dir} onContextMenu={onContextMenu}>{ex.dir}</EntitySpan>
              <span style={{ color: T.text.secondary, marginLeft: 4, fontSize: 11 }}>{ex.label}</span>
            </span>
          ))}
        </div>
      );
      case "entity": return <div key={i} style={{ ...base, color: T.hue.amber, fontFamily: T.font.body, fontSize: 13 }}>⬡ {parseEntities(line.text)}</div>;
      case "sep": return <div key={i} style={{ height: 1, margin: "6px 14px", background: `linear-gradient(90deg,${T.border.dim},transparent)` }} />;
      case "action": return (
        <div key={i} style={{ ...base, color: T.text.primary, display: "flex", gap: 4 }}>
          <Ts ts={line.ts} /><span style={{ color: T.hue.cyan }}>❯</span><span>{line.text.replace("> ", "")}</span>
        </div>
      );
      case "response": return <div key={i} style={{ ...base, color: T.text.narrative, fontFamily: T.font.body, fontSize: 14, lineHeight: 1.75, padding: "4px 14px 6px" }}>{parseEntities(line.text)}</div>;
      case "alert": {
        const cfg = { warning: { bg: T.hue.amberDim, color: T.hue.amber, border: T.hue.amber, icon: "⚠" }, success: { bg: T.hue.emeraldDim, color: T.text.success, border: T.hue.emerald, icon: "✓" }, danger: { bg: T.hue.crimsonDim, color: T.text.danger, border: T.hue.crimson, icon: "✕" } }[line.level] || {};
        return <div key={i} role="alert" style={{ ...base, color: cfg.color, fontSize: 12, fontWeight: 600, background: cfg.bg, margin: "4px 14px", padding: "6px 12px", borderRadius: T.radius.sm, borderLeft: `3px solid ${cfg.border}` }}>{cfg.icon} {line.text}</div>;
      }
      case "glyph_cast": return (
        <div key={i} style={{ ...base, fontFamily: T.font.body, fontSize: 14, lineHeight: 1.75, color: T.text.accentStrong, padding: "6px 14px", background: `linear-gradient(90deg,${T.hue.violetDim},transparent 70%)`, borderLeft: `2px solid ${T.hue.violet}60`, margin: "4px 0" }}>
          {parseEntities(line.text)}
        </div>
      );
      case "image_gen": return (
        <div key={i} style={{ margin: "8px 14px", borderRadius: T.radius.md, height: 140, overflow: "hidden", position: "relative", background: `linear-gradient(135deg,${T.bg.deep},${T.hue.violetDim})`, border: `1px solid ${T.border.accent}` }}>
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: "50%", border: `2px solid ${T.hue.violet}50`, borderTopColor: T.hue.violet, animation: "spin 1s linear infinite" }} />
            <span style={{ fontFamily: T.font.body, fontSize: 11, color: T.text.muted }}>Generating · {line.label}</span>
          </div>
        </div>
      );
      case "discovery": return (
        <div key={i} role="alert" style={{ ...base, fontSize: 12, fontWeight: 600, color: T.hue.violet, background: T.hue.violetDim, margin: "6px 14px", padding: "8px 12px", borderRadius: T.radius.md, border: `1px solid ${T.border.accent}`, fontFamily: T.font.body }}>
          {line.text}
        </div>
      );
      case "credits_grant": return (
        <div
          key={i}
          role="status"
          style={{
            ...base,
            margin: "8px 14px",
            padding: "10px 14px",
            borderRadius: T.radius.md,
            fontFamily: T.font.body,
            fontSize: 13,
            lineHeight: 1.55,
            fontWeight: 600,
            color: T.currency.art.fg,
            background: T.currency.art.bg,
            border: `1px solid ${T.currency.art.border}`,
            boxShadow: `0 0 12px ${T.currency.art.dim}`,
          }}
        >
          {line.text}
        </div>
      );
      case "staff_notice": return (
        <div
          key={i}
          role="status"
          style={{
            ...base,
            margin: "8px 14px",
            padding: "10px 14px",
            borderRadius: T.radius.md,
            fontFamily: T.font.body,
            fontSize: 12,
            lineHeight: 1.55,
            fontWeight: 500,
            color: T.hue.cyan,
            background: `${T.hue.cyan}12`,
            border: `1px solid ${T.hue.cyan}55`,
            whiteSpace: "pre-wrap",
          }}
        >
          {line.text}
        </div>
      );
      default: return <div key={i} style={{ ...base, color: T.text.secondary }}>{line.text}</div>;
    }
  };

  const filtered = searchTerm.trim()
    ? lines.map((l, i) => ({ l, i })).filter(({ l }) => {
        const t = JSON.stringify(l).toLowerCase();
        return t.includes(searchTerm.toLowerCase());
      })
    : lines.map((l, i) => ({ l, i }));

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {sceneModalOpen && sceneGen ? (
        <SceneArtModal
          key={sceneModalKey}
          onClose={() => setSceneModalOpen(false)}
          lines={lines}
          sceneGen={sceneGen}
        />
      ) : null}
      {galleryModalOpen && sceneGen ? (
        <SceneGalleryModal
          key={galleryModalKey}
          onClose={() => setGalleryModalOpen(false)}
          sceneGen={sceneGen}
        />
      ) : null}
      {searchOpen && (
        <div style={{ padding: "4px 8px", borderBottom: `1px solid ${T.border.subtle}`, display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: T.text.muted }}>🔍</span>
          <input value={searchTerm} onChange={e => setSearchTerm(e.target.value)} autoFocus
            placeholder="Search scrollback..." aria-label="Search scrollback"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text.primary, fontFamily: T.font.mono, fontSize: 12 }} />
          <button onClick={() => { setSearchOpen(false); setSearchTerm(""); }}
            aria-label="Close search" style={{ background: "none", border: "none", color: T.text.muted, cursor: "pointer", fontSize: 12 }}>✕</button>
        </div>
      )}
      <div
        style={{
          flex: 1,
          position: "relative",
          minHeight: 0,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {portraitBackdropUrl && portraitBackdropOn ? (
          <div
            aria-hidden
            style={{
              position: "absolute",
              inset: 0,
              zIndex: 0,
              pointerEvents: "none",
              overflow: "hidden",
            }}
          >
            <img
              src={portraitBackdropUrl}
              alt=""
              style={{
                position: "absolute",
                top: "50%",
                right: "-3%",
                height: "100%",
                width: "auto",
                maxWidth: "50%",
                objectFit: "contain",
                objectPosition: "right center",
                opacity: portraitBackdropOpacity / 100,
                transform: `translate(${portraitBackdropXOffset}%, -50%) scale(${portraitBackdropScale / 100})`,
                transformOrigin: "right center",
              }}
            />
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: narrativePortraitScrim,
              }}
            />
          </div>
        ) : null}
        <div
          ref={scrollRef}
          onScroll={onNarrativeScroll}
          role="log"
          aria-live="polite"
          aria-label="Game narrative"
          style={{
            flex: 1,
            position: "relative",
            zIndex: 1,
            overflowY: "auto",
            overflowX: "hidden",
            paddingBottom: 8,
          }}
        >
        {filtered.map(({ l, i }) => renderLine(l, i))}
        </div>
      </div>
      <div style={{ display: "flex", gap: 2, padding: "2px 8px", borderTop: `1px solid ${T.border.subtle}`, alignItems: "center", flexWrap: "wrap" }}>
        {[
          { icon: "🔍", label: "Search", action: () => setSearchOpen(!searchOpen) },
          ...(sceneGen
            ? [
                {
                  icon: "🎨",
                  label: "Scene art (ComfyUI)",
                  action: () => {
                    setSceneModalKey((k) => k + 1);
                    setSceneModalOpen(true);
                  },
                },
                {
                  icon: "🖼",
                  label: "My scene art (gallery)",
                  action: () => {
                    setGalleryModalKey((k) => k + 1);
                    setGalleryModalOpen(true);
                  },
                },
              ]
            : []),
          ...(portraitBackdropUrl
            ? [
                {
                  icon: "👤",
                  label: portraitBackdropOn
                    ? "Hide character portrait behind narrative"
                    : "Show character portrait behind narrative",
                  action: togglePortraitBackdrop,
                  active: portraitBackdropOn,
                },
              ]
            : []),
          { icon: "🕐", label: "Timestamps", action: () => setShowTimestamps(!showTimestamps), active: showTimestamps },
          { icon: "📋", label: "Copy log", action: () => {} },
          { icon: "💾", label: "Save session", action: () => {} },
        ].map((btn, i) => (
          <button key={i} onClick={btn.action} title={btn.label} aria-label={btn.label}
            style={{ padding: "3px 6px", borderRadius: T.radius.sm, border: "none", background: btn.active ? T.hue.violetDim : "transparent", color: btn.active ? T.text.accent : T.text.muted, cursor: "pointer", fontSize: 11, transition: "all 0.1s" }}
            onMouseEnter={e => e.target.style.color = T.text.primary}
            onMouseLeave={e => e.target.style.color = btn.active ? T.text.accent : T.text.muted}
          >{btn.icon}</button>
        ))}
        {portraitBackdropUrl && portraitBackdropOn ? (
          <>
            <label
              title="Portrait fade (opacity)"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                marginLeft: 2,
                padding: "0 4px",
                flex: "1 1 100px",
                minWidth: 64,
                maxWidth: 130,
              }}
            >
              <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" }}>
                Portrait backdrop fade
              </span>
              <span style={{ fontSize: 9, color: T.text.muted, flexShrink: 0, fontFamily: T.font.body }}>◐</span>
              <input
                type="range"
                min={PORTRAIT_BACKDROP_OPACITY_MIN}
                max={PORTRAIT_BACKDROP_OPACITY_MAX}
                step={1}
                value={portraitBackdropOpacity}
                onChange={onPortraitBackdropOpacityChange}
                aria-label="Portrait backdrop fade"
                style={{
                  flex: 1,
                  minWidth: 40,
                  height: 4,
                  accentColor: T.hue.violet,
                }}
              />
            </label>
            <label
              title="Portrait size (scale)"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                padding: "0 4px",
                flex: "1 1 100px",
                minWidth: 64,
                maxWidth: 130,
              }}
            >
              <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" }}>
                Portrait backdrop size
              </span>
              <span style={{ fontSize: 9, color: T.text.muted, flexShrink: 0, fontFamily: T.font.body }}>⇲</span>
              <input
                type="range"
                min={PORTRAIT_BACKDROP_SCALE_MIN}
                max={PORTRAIT_BACKDROP_SCALE_MAX}
                step={1}
                value={portraitBackdropScale}
                onChange={onPortraitBackdropScaleChange}
                aria-label="Portrait backdrop size"
                style={{
                  flex: 1,
                  minWidth: 40,
                  height: 4,
                  accentColor: T.hue.cyan,
                }}
              />
            </label>
            <label
              title="Portrait horizontal position"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                padding: "0 4px",
                flex: "1 1 100px",
                minWidth: 64,
                maxWidth: 130,
              }}
            >
              <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" }}>
                Portrait backdrop horizontal position
              </span>
              <span style={{ fontSize: 9, color: T.text.muted, flexShrink: 0, fontFamily: T.font.body }}>↔</span>
              <input
                type="range"
                min={PORTRAIT_BACKDROP_X_OFFSET_MIN}
                max={PORTRAIT_BACKDROP_X_OFFSET_MAX}
                step={1}
                value={portraitBackdropXOffset}
                onChange={onPortraitBackdropXOffsetChange}
                aria-label="Portrait backdrop horizontal position"
                style={{
                  flex: 1,
                  minWidth: 40,
                  height: 4,
                  accentColor: T.hue.amber,
                }}
              />
            </label>
          </>
        ) : null}
      </div>
    </div>
  );
}

export function CommandInput({ onSubmitCommand }) {
  const { T } = usePlayTheme();
  const [value, setValue] = useState("");
  const [history, setHistory] = useState([]);
  const [histIdx, setHistIdx] = useState(-1);
  const [suggestions, setSuggestions] = useState([]);
  const inputRef = useRef(null);
  // Mirrors the server's command registry (engine/src/sage/commands); keep in sync when adding commands.
  const CMDS = ["achievements","attack","bonus","browse","buy","cap","craft","deconstruct","down","drop","east","effects","emote","equip","examine","factions","flee","help","inventory","lock","look","lower","map","missions","north","northeast","northwest","prof","quit","raise","recipes","rent","rest","say","score","search","sell","south","southeast","southwest","take","tell","unequip","up","use","wallet","west","who"];
  const handleKey = (e) => {
    if (e.key === "Enter" && value.trim()) {
      const cmd = value.trim();
      onSubmitCommand?.(cmd);
      setHistory(h => [cmd, ...h.filter(x => x !== cmd)].slice(0, 50));
      setValue(""); setHistIdx(-1); setSuggestions([]);
    }
    else if (e.key === "ArrowUp") { e.preventDefault(); const n = Math.min(histIdx + 1, history.length - 1); setHistIdx(n); setValue(history[n] || ""); }
    else if (e.key === "ArrowDown") { e.preventDefault(); const n = histIdx - 1; if (n < 0) { setHistIdx(-1); setValue(""); } else { setHistIdx(n); setValue(history[n] || ""); } }
    else if (e.key === "Tab") { e.preventDefault(); if (suggestions.length === 1) { setValue(suggestions[0] + " "); setSuggestions([]); } }
    else if (e.key === "Escape") { setSuggestions([]); }
  };
  useEffect(() => {
    if (value.trim() && !value.includes(" ")) { setSuggestions(CMDS.filter(c => c.startsWith(value.toLowerCase())).slice(0, 6)); }
    else setSuggestions([]);
  }, [value]);

  return (
    <div style={{ position: "relative" }}>
      {suggestions.length > 0 && (
        <div role="listbox" aria-label="Command suggestions" style={{ position: "absolute", bottom: "100%", left: 0, right: 0, background: T.bg.elevated, border: `1px solid ${T.border.medium}`, borderBottom: "none", borderRadius: `${T.radius.md}px ${T.radius.md}px 0 0`, padding: "4px 0" }}>
          {suggestions.map((s, i) => (
            <div key={i} role="option" onClick={() => { setValue(s + " "); setSuggestions([]); inputRef.current?.focus(); }}
              style={{ padding: "4px 14px", fontFamily: T.font.mono, fontSize: 12, color: T.text.secondary, cursor: "pointer" }}
              onMouseEnter={e => { e.target.style.background = T.hue.violetDim; e.target.style.color = T.text.accent; }}
              onMouseLeave={e => { e.target.style.background = "transparent"; e.target.style.color = T.text.secondary; }}
            ><span style={{ color: T.text.accent }}>{s.slice(0, value.length)}</span>{s.slice(value.length)}</div>
          ))}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 8, background: T.bg.surface, padding: "6px 12px", borderTop: `1px solid ${T.border.dim}` }}>
        <span style={{ color: T.hue.violet, fontFamily: T.font.mono, fontSize: 14, fontWeight: 700 }}>❯</span>
        <input ref={inputRef} value={value} onChange={e => setValue(e.target.value)} onKeyDown={handleKey}
          role="textbox" aria-label="Command input" placeholder="Enter command..."
          style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: T.text.primary, fontFamily: T.font.mono, fontSize: 13, caretColor: T.hue.violet }} />
        <span style={{ fontFamily: T.font.mono, fontSize: 9, color: T.text.muted, opacity: 0.35 }}>↑↓ Tab Esc</span>
      </div>
    </div>
  );
}
