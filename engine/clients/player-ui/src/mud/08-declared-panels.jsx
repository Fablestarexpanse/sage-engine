import { useContext, useState } from "react";
import { usePlayTheme } from "../PlayThemeContext.jsx";
import { GameCmdContext } from "./00-ctx.jsx";

/**
 * Panels declared by server plugins (engine sage/network/panels.py documents every kind's data).
 * One generic renderer per kind; the server sends titles and all text, so nothing here is
 * specific to a world. Tree actions are ordinary commands sent as if typed.
 */

function toneColor(tone, T) {
  if (tone === "good") return T.text.success;
  if (tone === "warn") return T.text.gold;
  if (tone === "bad") return T.text.danger;
  return T.text.secondary;
}

function Empty({ T, text }) {
  return (
    <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", padding: 10 }}>
      <span style={{ fontSize: 10, fontFamily: T.font.body, color: T.text.muted }}>{text}</span>
    </div>
  );
}

function Bar({ value, min = 0, max, T, tone }) {
  const span = Number(max) - Number(min || 0);
  const pct = span > 0 ? Math.max(0, Math.min(100, ((Number(value) - Number(min || 0)) / span) * 100)) : 0;
  return (
    <div style={{ height: 6, borderRadius: 3, background: T.bg.void, border: `1px solid ${T.border.subtle}`, overflow: "hidden" }}>
      <div style={{ width: `${pct}%`, height: "100%", background: tone ? toneColor(tone, T) : T.text.accent, transition: "width 0.3s ease" }} />
    </div>
  );
}

const rowStyle = (T) => ({
  display: "flex",
  alignItems: "baseline",
  gap: 8,
  padding: "4px 6px",
  borderBottom: `1px solid ${T.border.subtle}`,
  fontFamily: T.font.body,
  fontSize: 11,
});

function KeyValue({ data, T }) {
  const rows = Array.isArray(data?.rows) ? data.rows : [];
  if (!rows.length) return <Empty T={T} text={data?.empty || "—"} />;
  return (
    <div style={{ height: "100%", overflow: "auto", padding: 6 }}>
      {rows.map((r, i) => (
        <div key={i} style={rowStyle(T)}>
          <span style={{ flex: "0 0 40%", color: T.text.muted, textTransform: "capitalize" }}>{String(r.label ?? "")}</span>
          <span style={{ flex: 1, color: T.text.primary, fontVariantNumeric: "tabular-nums" }}>{String(r.value ?? "")}</span>
        </div>
      ))}
    </div>
  );
}

function List({ data, T }) {
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) return <Empty T={T} text={data?.empty || "—"} />;
  return (
    <div style={{ height: "100%", overflow: "auto", padding: 6 }}>
      {items.map((it, i) => (
        <div key={i} style={{ ...rowStyle(T), borderLeft: `3px solid ${toneColor(it.tone, T)}` }}>
          <span style={{ flex: 1, color: T.text.primary }}>{String(it.label ?? "")}</span>
          {it.detail != null && <span style={{ color: toneColor(it.tone, T) }}>{String(it.detail)}</span>}
          {it.value != null && (
            <span style={{ fontFamily: T.font.mono, fontSize: 10, color: T.text.muted, fontVariantNumeric: "tabular-nums" }}>{String(it.value)}</span>
          )}
        </div>
      ))}
    </div>
  );
}

function StatSheet({ data, T }) {
  const stats = Array.isArray(data?.stats) ? data.stats : [];
  if (!stats.length) return <Empty T={T} text={data?.empty || "—"} />;
  return (
    <div style={{ height: "100%", overflow: "auto", padding: 8, display: "flex", flexDirection: "column", gap: 8 }}>
      {stats.map((s, i) => (
        <div key={i} title={s.note || undefined}>
          <div style={{ display: "flex", justifyContent: "space-between", fontFamily: T.font.body, fontSize: 11, marginBottom: 3 }}>
            <span style={{ color: T.text.secondary }}>{String(s.label ?? "")}</span>
            <span style={{ fontFamily: T.font.mono, color: T.text.primary, fontVariantNumeric: "tabular-nums" }}>
              {String(s.value ?? "")}
              {s.max != null && s.min == null ? <span style={{ color: T.text.muted }}> / {String(s.max)}</span> : null}
              {s.min != null && s.note ? <span style={{ color: T.text.muted }}> · {String(s.note)}</span> : null}
            </span>
          </div>
          {s.max != null && <Bar value={s.value} min={s.min} max={s.max} T={T} tone={s.tone} />}
        </div>
      ))}
    </div>
  );
}

function Wallet({ data, T }) {
  const balances = Array.isArray(data?.balances) ? data.balances : [];
  if (!balances.length) return <Empty T={T} text={data?.empty || "—"} />;
  return (
    <div style={{ height: "100%", overflow: "auto", padding: 8, display: "flex", flexWrap: "wrap", gap: 8, alignContent: "flex-start" }}>
      {balances.map((b, i) => (
        <div key={i} style={{ padding: "6px 10px", borderRadius: T.radius.md, border: `1px solid ${T.border.dim}`, background: T.bg.surface }}>
          <div style={{ fontSize: 8, fontFamily: T.font.body, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.07em" }}>{String(b.label ?? "")}</div>
          <div style={{ fontSize: 14, fontFamily: T.font.mono, color: T.text.primary, fontVariantNumeric: "tabular-nums" }}>{String(b.amount ?? 0)}</div>
        </div>
      ))}
    </div>
  );
}

function Table({ data, T }) {
  const columns = Array.isArray(data?.columns) ? data.columns : [];
  const rows = Array.isArray(data?.rows) ? data.rows : [];
  if (!rows.length) return <Empty T={T} text={data?.empty || "—"} />;
  const cell = { padding: "3px 6px", borderBottom: `1px solid ${T.border.subtle}`, textAlign: "left", whiteSpace: "nowrap" };
  return (
    <div style={{ height: "100%", overflow: "auto", padding: 6 }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontFamily: T.font.body, fontSize: 11, fontVariantNumeric: "tabular-nums" }}>
        <thead>
          <tr>{columns.map((c, i) => <th key={i} style={{ ...cell, color: T.text.muted, fontWeight: 600 }}>{String(c)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{(Array.isArray(r) ? r : []).map((v, j) => <td key={j} style={{ ...cell, color: T.text.primary }}>{String(v ?? "")}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TreeNode({ node, depth, T, sendCommand, open, toggle }) {
  const kids = Array.isArray(node.children) ? node.children : [];
  const isOpen = open.has(node.id);
  const actions = Array.isArray(node.actions) ? node.actions : [];
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 6px", paddingLeft: 6 + depth * 12, fontFamily: T.font.body, fontSize: 11 }} title={node.note || undefined}>
        <button
          type="button"
          onClick={() => kids.length && toggle(node.id)}
          aria-label={kids.length ? `${isOpen ? "Collapse" : "Expand"} ${node.label}` : undefined}
          aria-expanded={kids.length ? isOpen : undefined}
          disabled={!kids.length}
          style={{ width: 14, border: "none", background: "transparent", color: T.text.muted, cursor: kids.length ? "pointer" : "default", fontSize: 9, padding: 0 }}
        >
          {kids.length ? (isOpen ? "▾" : "▸") : "·"}
        </button>
        <span style={{ flex: 1, minWidth: 0, color: node.tone ? toneColor(node.tone, T) : T.text.primary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{String(node.label ?? node.id)}</span>
        {node.max != null ? (
          <span style={{ width: 70 }}><Bar value={node.value} max={node.max} T={T} tone={node.tone} /></span>
        ) : null}
        {node.value != null && (
          <span style={{ fontFamily: T.font.mono, fontSize: 10, color: T.text.secondary, minWidth: 24, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{String(node.value)}</span>
        )}
        {actions.map((a, i) => (
          <button
            key={i}
            type="button"
            onClick={() => sendCommand?.(a.command)}
            title={a.command}
            style={{ padding: "1px 6px", borderRadius: T.radius.sm, border: `1px solid ${T.border.medium}`, background: T.bg.surface, color: T.text.secondary, fontFamily: T.font.body, fontSize: 9, cursor: "pointer" }}
          >
            {String(a.label)}
          </button>
        ))}
      </div>
      {isOpen && kids.map((k) => <TreeNode key={k.id} node={k} depth={depth + 1} T={T} sendCommand={sendCommand} open={open} toggle={toggle} />)}
    </div>
  );
}

function Tree({ data, T }) {
  const { sendCommand } = useContext(GameCmdContext);
  const [open, setOpen] = useState(() => new Set());
  const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
  if (!nodes.length) return <Empty T={T} text={data?.empty || "—"} />;
  const toggle = (id) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <div style={{ height: "100%", overflow: "auto", padding: "4px 0" }}>
      {nodes.map((n) => <TreeNode key={n.id} node={n} depth={0} T={T} sendCommand={sendCommand} open={open} toggle={toggle} />)}
    </div>
  );
}

const RENDERERS = { key_value: KeyValue, list: List, stat_sheet: StatSheet, wallet: Wallet, table: Table, tree: Tree };

export function DeclaredPanel({ spec, data }) {
  const { T } = usePlayTheme();
  const Renderer = RENDERERS[spec?.kind];
  if (!Renderer) return <Empty T={T} text={`Unsupported panel kind: ${spec?.kind}`} />;
  if (data === undefined) return <Empty T={T} text="Waiting for server…" />;
  return <Renderer data={data} T={T} />;
}
