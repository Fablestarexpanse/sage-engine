import { useState, useEffect, useCallback, useRef } from "react";
import { clamp } from "../theme.js";
import { usePlayTheme } from "../PlayThemeContext.jsx";

export function ContextMenu({ x, y, items, onClose }) {
  const { T } = usePlayTheme();
  const ref = useRef(null);
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);
  return (
    <div ref={ref} role="menu" aria-label="Entity actions" style={{
      position: "fixed", left: x, top: y, zIndex: 99999,
      background: T.bg.elevated, border: `1px solid ${T.border.medium}`,
      borderRadius: T.radius.md, padding: 4, minWidth: 160,
      boxShadow: "0 8px 32px rgba(0,0,0,0.6)", backdropFilter: "blur(8px)",
    }}>
      {items.map((item, i) => item.separator ? (
        <div key={i} style={{ height: 1, margin: "3px 8px", background: T.border.dim }} />
      ) : (
        <button key={i} role="menuitem" onClick={() => { item.action?.(); onClose(); }}
          style={{
            display: "flex", alignItems: "center", gap: 8, width: "100%",
            padding: "6px 10px", background: "none", border: "none",
            borderRadius: T.radius.sm, cursor: "pointer", textAlign: "left",
            color: item.danger ? T.text.danger : T.text.secondary,
            fontFamily: T.font.body, fontSize: 11, transition: "all 0.1s",
          }}
          onMouseEnter={e => { e.target.style.background = T.glyph.violetDim; e.target.style.color = T.text.primary; }}
          onMouseLeave={e => { e.target.style.background = "none"; e.target.style.color = item.danger ? T.text.danger : T.text.secondary; }}
        >
          <span style={{ width: 16, textAlign: "center", fontSize: 12, opacity: 0.7 }}>{item.icon}</span>
          <span>{item.label}</span>
          {item.hint && <span style={{ marginLeft: "auto", fontSize: 9, opacity: 0.4, fontFamily: T.font.mono }}>{item.hint}</span>}
        </button>
      ))}
    </div>
  );
}

export function Tooltip({ children, text, detail }) {
  const { T } = usePlayTheme();
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const ref = useRef(null);
  return (
    <span ref={ref} style={{ position: "relative", display: "inline" }}
      onMouseEnter={(e) => { setShow(true); const r = e.target.getBoundingClientRect(); setPos({ x: r.left + r.width / 2, y: r.top - 4 }); }}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <div style={{
          position: "fixed", left: pos.x, top: pos.y, transform: "translate(-50%,-100%)",
          background: T.bg.elevated, border: `1px solid ${T.border.medium}`,
          borderRadius: T.radius.sm, padding: "4px 8px", zIndex: 99998,
          boxShadow: "0 4px 16px rgba(0,0,0,0.5)", pointerEvents: "none",
          maxWidth: 220, whiteSpace: "normal",
        }}>
          <div style={{ fontSize: 11, fontFamily: T.font.body, color: T.text.primary, fontWeight: 600 }}>{text}</div>
          {detail && <div style={{ fontSize: 10, fontFamily: T.font.body, color: T.text.muted, marginTop: 2 }}>{detail}</div>}
        </div>
      )}
    </span>
  );
}

export function DraggablePanel({ id, title, icon, children, defaultPos, defaultSize, minW = 240, minH = 160, collapsed, onToggleCollapse, zIndex = 1, onFocus, accentColor, badge, resizable = true, locked = false }) {
  const { T } = usePlayTheme();
  const [pos, setPos] = useState(defaultPos);
  const [size, setSize] = useState(defaultSize);
  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);
  const accent = accentColor || T.glyph.violet;
  const onDragStart = useCallback((e) => {
    if (locked) return; e.preventDefault();
    const sx = e.clientX - pos.x, sy = e.clientY - pos.y;
    setDragging(true);
    const mv = (ev) => setPos({ x: clamp(ev.clientX - sx, 0, window.innerWidth - 100), y: clamp(ev.clientY - sy, 0, window.innerHeight - 40) });
    const up = () => { setDragging(false); window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }, [pos, locked]);
  const onResizeStart = useCallback((e) => {
    if (locked || !resizable) return; e.preventDefault(); e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, sw = size.w, sh = size.h;
    setResizing(true);
    const mv = (ev) => setSize({ w: Math.max(minW, sw + ev.clientX - sx), h: Math.max(minH, sh + ev.clientY - sy) });
    const up = () => { setResizing(false); window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }, [size, locked, resizable, minW, minH]);

  return (
    <section role="region" aria-label={title} tabIndex={-1}
      onMouseDown={() => onFocus?.(id)}
      style={{
        position: "absolute", left: pos.x, top: pos.y, width: size.w,
        height: collapsed ? 36 : size.h, background: T.bg.panel,
        border: `1px solid ${dragging || resizing ? accent + "60" : T.border.dim}`,
        borderRadius: T.radius.lg, boxShadow: dragging ? T.shadow.panelHover : T.shadow.panel,
        zIndex, display: "flex", flexDirection: "column", overflow: "hidden",
        transition: dragging || resizing ? "none" : "height 0.2s ease,box-shadow 0.2s",
        userSelect: dragging || resizing ? "none" : "auto",
      }}
    >
      <div onMouseDown={onDragStart} style={{
        height: 36, minHeight: 36, display: "flex", alignItems: "center",
        padding: "0 10px", gap: 8, cursor: locked ? "default" : "grab",
        background: `linear-gradient(90deg,${accent}08 0%,transparent 60%)`,
        borderBottom: collapsed ? "none" : `1px solid ${T.border.subtle}`, userSelect: "none",
      }}>
        <span style={{ fontSize: 14, opacity: 0.7 }}>{icon}</span>
        <span style={{ fontFamily: T.font.body, fontSize: 11, fontWeight: 600, color: T.text.secondary, letterSpacing: "0.06em", textTransform: "uppercase", flex: 1 }}>{title}</span>
        {badge > 0 && (
          <span aria-label={`${badge} unread`} style={{
            minWidth: 16, height: 16, borderRadius: 8, padding: "0 4px",
            background: T.glyph.crimson, color: "#fff", fontSize: 9,
            fontFamily: T.font.mono, fontWeight: 700, display: "flex",
            alignItems: "center", justifyContent: "center", lineHeight: 1,
          }}>{badge > 99 ? "99+" : badge}</span>
        )}
        <button onClick={(e) => { e.stopPropagation(); onToggleCollapse?.(id); }}
          aria-label={collapsed ? `Expand ${title}` : `Collapse ${title}`}
          style={{ background: "none", border: "none", color: T.text.muted, cursor: "pointer", fontSize: 14, padding: "2px 4px", borderRadius: 3, lineHeight: 1 }}
          onMouseEnter={e => e.target.style.color = T.text.primary}
          onMouseLeave={e => e.target.style.color = T.text.muted}
        >{collapsed ? "◻" : "—"}</button>
      </div>
      {!collapsed && (
        <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
          {children}
          {resizable && !locked && <div onMouseDown={onResizeStart} style={{ position: "absolute", bottom: 0, right: 0, width: 16, height: 16, cursor: "nwse-resize", background: `linear-gradient(135deg,transparent 50%,${accent}30 50%)`, borderRadius: `0 0 ${T.radius.lg}px 0` }} />}
        </div>
      )}
    </section>
  );
}
