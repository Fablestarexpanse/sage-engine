import { useAdminTheme } from "./AdminThemeContext.jsx";

// "41–60 of 1,204" with previous and next, for server-paged lists.
export default function Pager({ offset, limit, total, onOffset }) {
  const { colors: COLORS } = useAdminTheme();
  if (!total) return null;
  const btn = (disabled) => ({ padding: "4px 10px", fontSize: 12, borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bgCard, color: disabled ? COLORS.textDim : COLORS.text, cursor: disabled ? "default" : "pointer" });
  const atStart = offset <= 0;
  const atEnd = offset + limit >= total;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>
      <span>{(offset + 1).toLocaleString()}–{Math.min(offset + limit, total).toLocaleString()} of {total.toLocaleString()}</span>
      <button type="button" disabled={atStart} onClick={() => onOffset(Math.max(0, offset - limit))} style={btn(atStart)}>Previous</button>
      <button type="button" disabled={atEnd} onClick={() => onOffset(offset + limit)} style={btn(atEnd)}>Next</button>
    </div>
  );
}
