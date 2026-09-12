import { useEffect } from "react";
import { flowRectIntersects, getRoomRectFlow } from "../utils/layoutAlign.js";

/**
 * Right-drag marquee selection on the ZoneEditor canvas: paints a screen-space
 * selection rectangle (via setMarqueeScreen) while dragging with the right
 * mouse button, then on release converts it to flow coordinates and selects
 * every unlocked room node it intersects (additive with Ctrl/Cmd held).
 * Extracted verbatim from ZoneEditor's pointerdown-capture effect.
 *
 * Refs/setters are expected to be stable (useRef/useState setters) — only
 * `zoneId` is a real effect dependency, matching the original.
 */
export function useMarqueeSelect({ containerRef, rfRef, setNodesRef, setMarqueeScreen, suppressPaneContextUntilRef, zoneId }) {
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;

    const isChromeUi = (el) =>
      Boolean(
        el?.closest?.(".react-flow__minimap") ||
          el?.closest?.(".react-flow__controls") ||
          el?.closest?.(".react-flow__panel")
      );

    const onPointerDownCapture = (e) => {
      if (e.pointerType === "touch") return;

      const rightMarquee = e.button === 2;
      if (!rightMarquee) return;

      const viewport = root.querySelector(".react-flow__viewport");
      if (!viewport || !viewport.contains(e.target) || isChromeUi(e.target)) return;

      const startX = e.clientX;
      const startY = e.clientY;
      let curX = startX;
      let curY = startY;
      const additive = e.ctrlKey || e.metaKey;

      let pointerCaptureHeld = false;
      try {
        viewport.setPointerCapture(e.pointerId);
        pointerCaptureHeld = true;
      } catch {
        /* WebView may omit setPointerCapture */
      }

      const paint = () => {
        const rr = root.getBoundingClientRect();
        setMarqueeScreen({
          left: Math.min(startX, curX) - rr.left,
          top: Math.min(startY, curY) - rr.top,
          width: Math.abs(curX - startX),
          height: Math.abs(curY - startY),
        });
      };
      paint();

      const onContextMenuWhileDrag = (ev) => {
        if (Math.abs(curX - startX) > 2 || Math.abs(curY - startY) > 2) {
          ev.preventDefault();
          ev.stopPropagation();
        }
      };
      window.addEventListener("contextmenu", onContextMenuWhileDrag, true);

      const onMove = (ev) => {
        curX = ev.clientX;
        curY = ev.clientY;
        paint();
      };

      const finish = (ev) => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", finish);
        window.removeEventListener("pointercancel", finish);
        window.removeEventListener("contextmenu", onContextMenuWhileDrag, true);

        if (pointerCaptureHeld) {
          try {
            viewport.releasePointerCapture(ev.pointerId);
          } catch {
            /* ignore */
          }
        }

        const endX = ev.clientX;
        const endY = ev.clientY;
        setMarqueeScreen(null);

        if (Math.abs(endX - startX) < 5 && Math.abs(endY - startY) < 5) return;

        if (rightMarquee) suppressPaneContextUntilRef.current = Date.now() + 400;

        const flow = rfRef.current;
        const xMin = Math.min(startX, endX);
        const yMin = Math.min(startY, endY);
        const xMax = Math.max(startX, endX);
        const yMax = Math.max(startY, endY);
        const p1 = flow.screenToFlowPosition({ x: xMin, y: yMin });
        const p2 = flow.screenToFlowPosition({ x: xMax, y: yMax });
        const rect = {
          x1: Math.min(p1.x, p2.x),
          y1: Math.min(p1.y, p2.y),
          x2: Math.max(p1.x, p2.x),
          y2: Math.max(p1.y, p2.y),
        };

        const hits = new Set();
        for (const n of flow.getNodes()) {
          if (n.type !== "room" || n.data?.locked) continue;
          if (flowRectIntersects(rect, getRoomRectFlow(n))) hits.add(n.id);
        }

        setNodesRef.current((nds) => {
          const prevSel = new Set(nds.filter((n) => n.type === "room" && n.selected && !n.data?.locked).map((n) => n.id));
          const nextSel = additive ? new Set([...prevSel, ...hits]) : hits;
          return nds.map((n) => ({
            ...n,
            selected: n.type === "room" && !n.data?.locked ? nextSel.has(n.id) : false,
          }));
        });
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", finish);
      window.addEventListener("pointercancel", finish);
    };

    root.addEventListener("pointerdown", onPointerDownCapture, true);
    return () => root.removeEventListener("pointerdown", onPointerDownCapture, true);
  }, [zoneId, containerRef, rfRef, setNodesRef, setMarqueeScreen, suppressPaneContextUntilRef]);
}
