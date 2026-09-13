import { useTheme } from "../ThemeContext.jsx";

function ValidationPanel({ issues, onPick }) {
  const { colors: COLORS } = useTheme();
  if (!issues?.length) {
    return (
      <div style={{ fontSize: 12, color: COLORS.success, fontFamily: "'DM Sans', sans-serif" }}>No issues detected.</div>
    );
  }
  return (
    <div
      style={{
        maxHeight: 220,
        overflow: "auto",
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
        color: COLORS.textMuted,
      }}
    >
      {issues.map((it, i) => (
        <div
          key={i}
          onClick={() => {
            if (it.nodeId) onPick?.(it);
          }}
          style={{
            marginBottom: 6,
            cursor: it.nodeId ? "pointer" : "default",
            color: it.level === "error" ? COLORS.danger : it.level === "warn" ? COLORS.warning : COLORS.info,
          }}
        >
          [{it.level}] {it.msg}
        </div>
      ))}
    </div>
  );
}

export default ValidationPanel;
