import { useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "../ThemeContext.jsx";

/**
 * Centered themed prompt (replaces window.prompt) for SAGE WorldForge.
 */
export default function TextPromptModal({
  open,
  title,
  hint,
  initialValue = "",
  confirmLabel = "OK",
  cancelLabel = "Cancel",
  validate = () => true,
  invalidMessage = "Invalid value.",
  onConfirm,
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
      fontFamily: "'JetBrains Mono', monospace",
    }),
    [COLORS]
  );
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setValue(initialValue);
    setError("");
    const t = window.setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select?.();
    }, 0);
    return () => window.clearTimeout(t);
  }, [open, initialValue]);

  if (!open) return null;

  const trySubmit = () => {
    const v = value.trim();
    if (!validate(v)) {
      setError(invalidMessage);
      return;
    }
    setError("");
    onConfirm(v);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="text-prompt-title"
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
        <h2 id="text-prompt-title" style={{ marginTop: 0, marginBottom: 12, fontSize: 17, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>
          {title}
        </h2>
        {hint ? <p style={{ margin: "0 0 14px", fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5 }}>{hint}</p> : null}
        <input
          ref={inputRef}
          style={inp}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError("");
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              trySubmit();
            }
            if (e.key === "Escape") onCancel();
          }}
        />
        {error ? <p style={{ margin: "10px 0 0", fontSize: 12, color: COLORS.danger }}>{error}</p> : null}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 20 }}>
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
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={trySubmit}
            style={{
              padding: "10px 18px",
              borderRadius: 8,
              border: `1px solid ${COLORS.accent}`,
              background: `${COLORS.accent}33`,
              color: COLORS.accent,
              fontWeight: 600,
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
