import { useCallback, useRef, useState } from "react";
import { useTheme } from "../ThemeContext.jsx";

const CONN_DEBUG_PANEL_POS_KEY = "worldforge_conn_debug_panel_pos";

function readConnDebugPanelPos() {
  try {
    const raw = localStorage.getItem(CONN_DEBUG_PANEL_POS_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    if (
      typeof p.left === "number" &&
      typeof p.top === "number" &&
      Number.isFinite(p.left) &&
      Number.isFinite(p.top)
    ) {
      return { left: p.left, top: p.top };
    }
  } catch {
    /* ignore */
  }
  return null;
}

/**
 * Draggable, dockable overlay showing the connection-drag debug log (see
 * ZoneEditor's pushConnectionDebug). Position persists to localStorage;
 * double-clicking the title re-docks it bottom-right.
 *
 * Props:
 * - open: whether to render the panel at all (mirrors connectionDebugLog).
 * - entries: array of { t, kind, detail } rows, newest first.
 * - onClear: called when the Clear button is pressed.
 * - onStatusMsg: (text) => void, used to report copy success/failure.
 * - containerRef: ref to the bounding container the panel drags within.
 */
export default function ConnectionDebugPanel({ open, entries, onClear, onStatusMsg, containerRef }) {
  const { colors: COLORS } = useTheme();
  const panelRef = useRef(null);
  const [pos, setPos] = useState(() => readConnDebugPanelPos());

  const tbBtn = {
    padding: "6px 10px",
    borderRadius: 6,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgCard,
    color: COLORS.text,
    cursor: "pointer",
    fontSize: 11,
  };

  const onHeaderPointerDown = useCallback(
    (e) => {
      if (e.button !== 0 || e.target.closest("button")) return;
      const root = containerRef.current;
      const panel = panelRef.current;
      if (!root || !panel) return;
      e.preventDefault();
      const rootR = root.getBoundingClientRect();
      const pr = panel.getBoundingClientRect();
      const curLeft = pos != null ? pos.left : pr.left - rootR.left;
      const curTop = pos != null ? pos.top : pr.top - rootR.top;
      const drag = { startX: e.clientX, startY: e.clientY, origLeft: curLeft, origTop: curTop };
      let lastPos = { left: curLeft, top: curTop };

      const onMove = (ev) => {
        const w = panel.offsetWidth;
        const h = panel.offsetHeight;
        const dx = ev.clientX - drag.startX;
        const dy = ev.clientY - drag.startY;
        let left = drag.origLeft + dx;
        let top = drag.origTop + dy;
        left = Math.max(4, Math.min(left, rootR.width - w - 4));
        top = Math.max(4, Math.min(top, rootR.height - h - 4));
        lastPos = { left, top };
        setPos(lastPos);
      };

      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        try {
          localStorage.setItem(CONN_DEBUG_PANEL_POS_KEY, JSON.stringify(lastPos));
        } catch {
          /* ignore */
        }
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    },
    [pos, containerRef]
  );

  if (!open) return null;

  return (
    <div
      ref={panelRef}
      style={{
        position: "absolute",
        ...(pos
          ? { left: pos.left, top: pos.top, right: "auto", bottom: "auto" }
          : { right: 12, bottom: 12, left: "auto", top: "auto" }),
        zIndex: 1000,
        width: "min(440px, calc(100% - 24px))",
        maxHeight: 260,
        display: "flex",
        flexDirection: "column",
        background: `${COLORS.bgPanel}f2`,
        border: `1px solid ${COLORS.info}`,
        borderRadius: 8,
        boxShadow: `0 4px 20px ${COLORS.bg}aa`,
        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        fontSize: 10,
        color: COLORS.text,
      }}
    >
      <div
        onPointerDown={onHeaderPointerDown}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "6px 8px",
          borderBottom: `1px solid ${COLORS.border}`,
          flexShrink: 0,
          cursor: "grab",
          userSelect: "none",
        }}
        title="Drag to reposition (saved) · double-click the title to dock bottom-right again"
      >
        <span
          style={{ color: COLORS.textMuted, flex: 1, minWidth: 0 }}
          onDoubleClick={(e) => {
            e.stopPropagation();
            setPos(null);
            try {
              localStorage.removeItem(CONN_DEBUG_PANEL_POS_KEY);
            } catch {
              /* ignore */
            }
          }}
        >
          Connection debug (newest first)
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button type="button" style={{ ...tbBtn, fontSize: 9, padding: "2px 8px" }} onClick={onClear}>
            Clear
          </button>
          <button
            type="button"
            style={{ ...tbBtn, fontSize: 9, padding: "2px 8px" }}
            onClick={() => {
              const text = JSON.stringify(entries, null, 2);
              if (navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(text).then(
                  () => onStatusMsg("Connection log copied to clipboard"),
                  () => onStatusMsg("Copy failed")
                );
              } else onStatusMsg("Clipboard not available");
            }}
          >
            Copy JSON
          </button>
        </div>
      </div>
      <div style={{ overflow: "auto", padding: 8, lineHeight: 1.35, flex: 1, minHeight: 0 }}>
        {entries.length === 0 ? (
          <span style={{ color: COLORS.textDim }}>
            Each drag gets its own <code style={{ color: COLORS.text }}>seq</code> (connectStart → onConnect_fired →
            onConnect_applied → connectEnd). Multiple seq values = multiple drags. Same link twice in under 0.75s
            logs <code style={{ color: COLORS.text }}>onConnect_skipped_duplicate_link</code>. Compare{" "}
            <code style={{ color: COLORS.text }}>raw</code> to <code style={{ color: COLORS.text }}>domUnderPointer</code>{" "}
            on connectEnd. Each applied link still writes <strong>two</strong> YAML exits (out + return) by design.
          </span>
        ) : (
          entries.map((row, i) => (
            <div key={`${row.t}-${row.kind}-${i}`} style={{ marginBottom: 10, wordBreak: "break-word" }}>
              <div style={{ color: COLORS.info, marginBottom: 2 }}>
                {row.t} · {row.kind}
              </div>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap", color: COLORS.textMuted }}>
                {JSON.stringify(row.detail, null, 2)}
              </pre>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
