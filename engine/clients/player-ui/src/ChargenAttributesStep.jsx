import { usePlayTheme } from "./PlayThemeContext.jsx";

/**
 * Character creation choices of kind "attribute_points": set each attribute within its range, all
 * of them together at most `budget`. Sent back as {"attributes": {key: value}}.
 */
export function ChargenAttributesStep({ options, value, onChange, disabled, onBack }) {
  const { T } = usePlayTheme();
  const attributes = options?.attributes || [];
  const budget = Number(options?.budget) || 0;
  const current = (a) => (value && Number.isFinite(value[a.key]) ? value[a.key] : a.default);
  const used = attributes.reduce((sum, a) => sum + current(a), 0);
  const remaining = budget - used;

  const set = (a, next) => {
    if (next < a.min || next > a.max) return;
    if (next > current(a) && remaining <= 0) return;
    onChange({ ...Object.fromEntries(attributes.map((x) => [x.key, current(x)])), [a.key]: next });
  };

  const stepBtn = (label, onClick, off) => (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || off}
      aria-label={label}
      style={{
        width: 30,
        height: 30,
        borderRadius: T.radius.md,
        border: `1px solid ${T.border.medium}`,
        background: T.bg.surface,
        color: T.text.primary,
        fontSize: 16,
        cursor: disabled || off ? "not-allowed" : "pointer",
        opacity: disabled || off ? 0.4 : 1,
      }}
    >
      {label === "Lower" ? "−" : "+"}
    </button>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 520, width: "100%", alignSelf: "center" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          padding: "12px 14px",
          borderRadius: T.radius.lg,
          border: `1px solid ${T.border.accent}`,
          background: T.hue.violetDim,
        }}
      >
        <span style={{ fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em" }}>Points remaining</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          <span style={{ fontFamily: T.font.display, fontSize: 24, color: remaining < 0 ? T.text.danger : T.text.accent, fontWeight: 700 }}>{remaining}</span>
          <span style={{ fontSize: 12, color: T.text.muted }}> / {budget}</span>
        </span>
      </div>
      {attributes.map((a) => (
        <div
          key={a.key}
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto auto auto",
            gap: 10,
            alignItems: "center",
            padding: "10px 12px",
            borderRadius: T.radius.md,
            border: `1px solid ${T.border.dim}`,
            background: T.bg.panel,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, color: T.text.primary, fontWeight: 600 }}>{a.label}</div>
            <div style={{ fontSize: 10, color: T.text.muted }}>
              {a.short} · {a.min}–{a.max}
            </div>
          </div>
          {stepBtn("Lower", () => set(a, current(a) - 1), current(a) <= a.min)}
          <span style={{ minWidth: 24, textAlign: "center", fontFamily: T.font.display, fontSize: 18, color: T.text.accent, fontVariantNumeric: "tabular-nums" }}>
            {current(a)}
          </span>
          {stepBtn("Raise", () => set(a, current(a) + 1), current(a) >= a.max || remaining <= 0)}
        </div>
      ))}
      <button
        type="button"
        disabled={disabled}
        onClick={onBack}
        style={{
          alignSelf: "flex-start",
          padding: "10px 16px",
          borderRadius: T.radius.md,
          border: `1px solid ${T.border.medium}`,
          background: T.bg.surface,
          color: T.text.secondary,
          fontSize: 12,
          fontWeight: 600,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      >
        ← Back to identity & portrait
      </button>
    </div>
  );
}
