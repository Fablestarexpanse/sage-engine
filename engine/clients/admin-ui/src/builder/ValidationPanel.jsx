import { useAdminTheme } from "../AdminThemeContext.jsx";

/**
 * @param {import('@xyflow/react').Node[]} nodes
 * @param {import('@xyflow/react').Edge[]} edges
 * @param {any[]} externalExits
 */
export function runZoneValidation(nodes, edges, externalExits = []) {
  const issues = [];
  const ids = new Set(nodes.map((n) => n.id));
  const connected = new Set();

  edges.forEach((e) => {
    connected.add(e.source);
    connected.add(e.target);
  });

  nodes.forEach((n) => {
    const d = n.data || {};
    if (!d.hasDescription) {
      issues.push({ level: "warn", msg: `Missing description: ${d.label || n.id}` });
    }
  });

  nodes.forEach((n) => {
    if (!connected.has(n.id) && nodes.length > 1) {
      issues.push({ level: "warn", msg: `Disconnected room: ${n.data?.label || n.id}` });
    }
  });

  edges.forEach((e) => {
    if (!ids.has(e.source) || !ids.has(e.target)) {
      issues.push({ level: "error", msg: `Broken edge ${e.id}` });
    }
  });

  const exitPairs = new Map();
  edges.forEach((e) => {
    const key = [e.source, e.target].sort().join("|");
    exitPairs.set(key, (exitPairs.get(key) || 0) + 1);
  });

  edges.forEach((e) => {
    const rev = edges.some(
      (x) => x.source === e.target && x.target === e.source && x.id !== e.id
    );
    if (!rev && e.data?.direction) {
      issues.push({
        level: "info",
        msg: `One-way: ${e.source} → ${e.target} (${e.data.direction})`,
      });
    }
  });

  externalExits.forEach((ex) => {
    issues.push({
      level: "info",
      msg: `External exit ${ex.from} ${ex.direction} → ${ex.destination}`,
    });
  });

  return issues;
}

export default function ValidationPanel({ issues }) {
  const { colors: COLORS } = useAdminTheme();
  if (!issues?.length) {
    return (
      <div style={{ fontSize: 12, color: COLORS.success, fontFamily: "'DM Sans', sans-serif" }}>
        No issues detected.
      </div>
    );
  }
  return (
    <div
      style={{
        maxHeight: 200,
        overflow: "auto",
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
        color: COLORS.textMuted,
      }}
    >
      {issues.map((it, i) => (
        <div key={i} style={{ marginBottom: 6, color: it.level === "error" ? COLORS.danger : it.level === "warn" ? COLORS.warning : COLORS.textDim }}>
          [{it.level}] {it.msg}
        </div>
      ))}
    </div>
  );
}
