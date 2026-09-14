import { useAdminTheme } from "./AdminThemeContext.jsx";

// Read-only drawings of the panels plugins declare for the player client (sage.network.panels):
// key_value, list, stat_sheet, wallet, table and tree. Staff see the same data the player sees,
// so a world's levels, skills, gear or standings appear here with no console code for them.
// Tree actions (commands the player can run) are listed but not runnable from the console.

const mono = "'JetBrains Mono', monospace";

function toneColor(COLORS, tone) {
  return tone === "good" ? COLORS.success : tone === "warn" ? COLORS.warning : tone === "bad" ? COLORS.danger : COLORS.text;
}

function Bar({ value, min = 0, max }) {
  const { colors: COLORS } = useAdminTheme();
  const pct = max > min ? Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100)) : 0;
  return (
    <div style={{ height: 5, background: COLORS.bgInput, borderRadius: 3, overflow: "hidden" }}>
      <div style={{ width: `${pct}%`, height: "100%", background: COLORS.accent }} />
    </div>
  );
}

function TreeNode({ node, depth }) {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ paddingLeft: depth ? 14 : 0 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12 }}>
        <span style={{ color: toneColor(COLORS, node.tone) }}>{node.label}</span>
        {node.value != null && <span style={{ fontFamily: mono, color: COLORS.textMuted }}>{node.value}{node.max != null ? `/${node.max}` : ""}</span>}
        {node.note && <span style={{ color: COLORS.textDim, fontSize: 11 }}>{node.note}</span>}
      </div>
      {(node.children || []).map((child) => <TreeNode key={child.id} node={child} depth={depth + 1} />)}
    </div>
  );
}

function PanelBody({ kind, data }) {
  const { colors: COLORS } = useAdminTheme();
  if (data == null) return <div style={{ fontSize: 12, color: COLORS.textDim }}>No data.</div>;
  if (kind === "key_value") {
    return (
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "3px 12px", fontSize: 12 }}>
        {(data.rows || []).map((r, i) => [
          <span key={`l${i}`} style={{ color: COLORS.textMuted }}>{r.label}</span>,
          <span key={`v${i}`} style={{ fontFamily: mono }}>{String(r.value)}</span>,
        ])}
      </div>
    );
  }
  if (kind === "list") {
    const items = data.items || [];
    if (!items.length) return <div style={{ fontSize: 12, color: COLORS.textDim }}>{data.empty || "Nothing."}</div>;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 12 }}>
        {items.map((it, i) => (
          <div key={i} style={{ display: "flex", gap: 8 }}>
            <span style={{ color: toneColor(COLORS, it.tone) }}>{it.label}</span>
            {it.detail && <span style={{ color: COLORS.textDim }}>{it.detail}</span>}
            {it.value != null && <span style={{ marginLeft: "auto", fontFamily: mono }}>{it.value}</span>}
          </div>
        ))}
      </div>
    );
  }
  if (kind === "stat_sheet") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
        {(data.stats || []).map((s, i) => (
          <div key={i}>
            <div style={{ display: "flex", gap: 8 }}>
              <span style={{ color: toneColor(COLORS, s.tone) }}>{s.label}</span>
              <span style={{ marginLeft: "auto", fontFamily: mono }}>{s.value}{s.max != null ? `/${s.max}` : ""}</span>
            </div>
            {s.max != null && <Bar value={s.value} min={s.min} max={s.max} />}
            {s.note && <div style={{ fontSize: 11, color: COLORS.textDim }}>{s.note}</div>}
          </div>
        ))}
      </div>
    );
  }
  if (kind === "wallet") {
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px", fontSize: 12 }}>
        {(data.balances || []).map((b, i) => <span key={i}>{b.label} <b style={{ fontFamily: mono }}>{b.amount}</b></span>)}
      </div>
    );
  }
  if (kind === "table") {
    return (
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", fontSize: 12 }}>
          <thead><tr>{(data.columns || []).map((c, i) => <th key={i} style={{ textAlign: "left", padding: "2px 10px 2px 0", color: COLORS.textMuted, fontWeight: 600 }}>{c}</th>)}</tr></thead>
          <tbody>{(data.rows || []).map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j} style={{ padding: "2px 10px 2px 0", fontFamily: typeof cell === "number" ? mono : undefined }}>{cell}</td>)}</tr>)}</tbody>
        </table>
      </div>
    );
  }
  if (kind === "tree") {
    const nodes = data.nodes || [];
    if (!nodes.length) return <div style={{ fontSize: 12, color: COLORS.textDim }}>Nothing.</div>;
    return <div style={{ maxHeight: 260, overflowY: "auto" }}>{nodes.map((n) => <TreeNode key={n.id} node={n} depth={0} />)}</div>;
  }
  return <pre style={{ fontSize: 11, margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(data, null, 2)}</pre>;
}

export default function PanelViews({ panels, sections }) {
  const { colors: COLORS } = useAdminTheme();
  if (!panels?.length) return null;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
      {panels.map((p) => (
        <div key={p.id} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: COLORS.text }} title={p.id}>{p.title}</div>
          <PanelBody kind={p.kind} data={sections?.[p.section]} />
        </div>
      ))}
    </div>
  );
}
