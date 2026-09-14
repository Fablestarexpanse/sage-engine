import { useEffect, useMemo, useState } from "react";
import { useTheme } from "../ThemeContext.jsx";

export function stampSlugFromDisplayName(name) {
  return (
    String(name || "")
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 48) || "stamp"
  );
}

/**
 * @param {object} props
 * @param {boolean} props.open
 * @param {string} props.initialDisplayName
 * @param {string} props.initialSlug
 * @param {(slug: string) => boolean} [props.validateSlug]
 * @param {(slug: string) => boolean} [props.validate] — alias for validateSlug (TextPromptModal-style)
 * @param {string} props.invalidSlugMessage
 * @param {(payload: { displayName: string, stampSlug: string, preserve: { descriptions: boolean, gameplay: boolean, internalExits: boolean, layoutExtras: boolean } }) => void} props.onSave
 * @param {() => void} props.onCancel
 */
export default function SaveStampModal({
  open,
  initialDisplayName = "",
  initialSlug = "",
  validateSlug,
  validate,
  invalidSlugMessage = "Use only letters, numbers, underscore, hyphen.",
  onSave,
  onCancel,
}) {
  const { colors: COLORS } = useTheme();
  const inp = useMemo(
    () => ({
      width: "100%",
      boxSizing: "border-box",
      padding: "10px 12px",
      borderRadius: 8,
      border: `1px solid ${COLORS.border}`,
      background: COLORS.bgInput,
      color: COLORS.text,
      fontSize: 13,
    }),
    [COLORS]
  );
  const slugValidate = validateSlug ?? validate ?? ((s) => /^[a-zA-Z0-9_-]+$/.test(String(s || "")));
  const [displayName, setDisplayName] = useState(initialDisplayName);
  const [stampSlug, setStampSlug] = useState(initialSlug);
  const [preserveDesc, setPreserveDesc] = useState(false);
  const [preserveGame, setPreserveGame] = useState(false);
  const [preserveExits, setPreserveExits] = useState(false);
  const [preserveLayout, setPreserveLayout] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setDisplayName(initialDisplayName);
    setStampSlug(initialSlug || stampSlugFromDisplayName(initialDisplayName));
    setPreserveDesc(false);
    setPreserveGame(false);
    setPreserveExits(false);
    setPreserveLayout(false);
    setError("");
  }, [open, initialDisplayName, initialSlug]);

  if (!open) return null;

  const trySave = () => {
    const dn = displayName.trim();
    const slug = stampSlug.trim();
    if (!dn) {
      setError("Enter a display name.");
      return;
    }
    if (!slugValidate(slug)) {
      setError(invalidSlugMessage);
      return;
    }
    setError("");
    onSave({
      displayName: dn,
      stampSlug: slug,
      preserve: {
        descriptions: preserveDesc,
        gameplay: preserveGame,
        internalExits: preserveExits,
        layoutExtras: preserveLayout,
      },
    });
  };

  const chk = (id, checked, onChange, label, hint) => (
    <label
      key={id}
      style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer", fontSize: 12, color: COLORS.text, marginBottom: 8 }}
    >
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} style={{ marginTop: 2 }} />
      <span>
        <span style={{ fontWeight: 600 }}>{label}</span>
        {hint ? <span style={{ display: "block", color: COLORS.textDim, fontWeight: 400, marginTop: 2 }}>{hint}</span> : null}
      </span>
    </label>
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        background: `${COLORS.bg}dd`,
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 440,
          background: COLORS.bgCard,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 12,
          padding: 20,
          boxShadow: `0 12px 40px ${COLORS.bg}cc`,
        }}
      >
        <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text, marginBottom: 12 }}>Save selection as stamp</div>
        <div style={{ fontSize: 11, color: COLORS.textDim, marginBottom: 14 }}>
          Saves unlocked selected rooms as a reusable layout under <code style={{ color: COLORS.textMuted }}>world/stamps/</code>. Default is a blank
          template (no exits / content); use the checkboxes to keep more.
        </div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 4 }}>Display name</div>
          <input style={inp} value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="e.g. Corridor fork" />
        </div>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 4 }}>Folder slug</div>
          <input style={inp} value={stampSlug} onChange={(e) => setStampSlug(e.target.value)} placeholder="corridor_fork" />
        </div>
        <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 6 }}>Preserve when saving</div>
        <div style={{ marginBottom: 12, padding: 10, background: COLORS.bgPanel, borderRadius: 8, border: `1px solid ${COLORS.border}` }}>
          {chk("pd", preserveDesc, setPreserveDesc, "Descriptions", "Room descriptions (and exit descriptions when exits are kept).")}
          {chk("pg", preserveGame, setPreserveGame, "Gameplay", "entity_spawns, hazards, features, tags.")}
          {chk("pe", preserveExits, setPreserveExits, "Internal exits", "Links only between selected rooms; external exits are dropped.")}
          {chk("pl", preserveLayout, setPreserveLayout, "Layout extras", "Per-node border_color from the map (not locked state).")}
        </div>
        {error ? <div style={{ fontSize: 12, color: COLORS.danger, marginBottom: 10 }}>{error}</div> : null}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button type="button" style={{ padding: "8px 14px", borderRadius: 8, border: `1px solid ${COLORS.border}`, background: COLORS.bgPanel, color: COLORS.text }} onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            style={{ padding: "8px 14px", borderRadius: 8, border: `1px solid ${COLORS.accent}`, background: `${COLORS.accent}22`, color: COLORS.accent }}
            onClick={trySave}
          >
            Save stamp
          </button>
        </div>
      </div>
    </div>
  );
}
