import { useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "../ThemeContext.jsx";

export default function GroupFormModal({ open, onConfirm, onCancel }) {
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
  const lbl = useMemo(
    () => ({ display: "block", fontSize: 11, color: COLORS.textMuted, marginBottom: 6, marginTop: 12 }),
    [COLORS]
  );
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [color, setColor] = useState("#7c6aef");
  const idRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setId("");
    setName("");
    setColor("#7c6aef");
    const t = window.setTimeout(() => idRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open]);

  if (!open) return null;

  const submit = () => {
    const gid = id.trim();
    if (!gid) return;
    onConfirm({ id: gid, name: name.trim() || gid, color: color.trim() || "#7c6aef" });
  };

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
          maxWidth: 400,
          background: COLORS.bgPanel,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 12,
          padding: 24,
          boxShadow: `0 24px 64px ${COLORS.bg}`,
        }}
      >
        <h2 style={{ marginTop: 0, marginBottom: 8, fontSize: 17, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>New room group</h2>
        <p style={{ margin: "0 0 8px", fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5 }}>Groups tint room nodes on the map. Id is required.</p>

        <label style={{ ...lbl, marginTop: 0 }}>Group id</label>
        <input
          ref={idRef}
          style={inp}
          value={id}
          onChange={(e) => setId(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && onCancel()}
        />

        <label style={lbl}>Display name</label>
        <input style={inp} value={name} onChange={(e) => setName(e.target.value)} placeholder="Optional, defaults to id" />

        <label style={lbl}>Color</label>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input type="color" value={/^#[0-9A-Fa-f]{6}$/i.test(color) ? color : "#7c6aef"} onChange={(e) => setColor(e.target.value)} style={{ width: 48, height: 36, padding: 0, border: `1px solid ${COLORS.border}`, borderRadius: 6, cursor: "pointer", background: COLORS.bgInput }} />
          <input style={{ ...inp, flex: 1, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }} value={color} onChange={(e) => setColor(e.target.value)} placeholder="#7c6aef" />
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 22 }}>
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: "10px 18px",
              borderRadius: 8,
              border: `1px solid ${COLORS.border}`,
              background: COLORS.bgCard,
              color: COLORS.textMuted,
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!id.trim()}
            style={{
              padding: "10px 18px",
              borderRadius: 8,
              border: `1px solid ${COLORS.accent}`,
              background: `${COLORS.accent}33`,
              color: COLORS.accent,
              fontWeight: 600,
              fontSize: 13,
              cursor: id.trim() ? "pointer" : "not-allowed",
              opacity: id.trim() ? 1 : 0.5,
            }}
          >
            Add group
          </button>
        </div>
      </div>
    </div>
  );
}
