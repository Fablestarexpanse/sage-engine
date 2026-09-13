import { useTheme } from "../ThemeContext.jsx";

export const floorLabel = (n) => (n === 0 ? "Ground" : n > 0 ? `F${n}` : `B${Math.abs(n)}`);

/**
 * Z-level floor switcher (top-left column of floor buttons) plus the
 * "pending stair link" mode banner (top-center), extracted from ZoneEditor.
 *
 * Props:
 * - floors: array of floor numbers to show, already deduped/sorted (see
 *   ZoneEditor's `[...new Set([0, ...floors])].sort((a, b) => b - a)`).
 * - currentFloor: the active floor number.
 * - onChange(floor): called with a floor number (from a floor button or the
 *   ▲/▼ steppers, which pass an updater the same way `setCurrentFloor` did —
 *   ZoneEditor still owns the `currentFloor` state).
 * - pendingStairLink: { slug, ghostFloor, ghostDir: "up"|"down" } | null.
 * - onCancelStairLink(): called from the banner's ✕ button.
 */
export default function FloorSwitcher({ floors, currentFloor, onChange, pendingStairLink, onCancelStairLink }) {
  const { colors: COLORS } = useTheme();

  return (
    <>
      <div
        style={{
          position: "absolute",
          left: 10,
          top: 10,
          zIndex: 100,
          display: "flex",
          flexDirection: "column",
          gap: 2,
          background: COLORS.bgPanel,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 8,
          padding: "4px 2px",
          pointerEvents: "all",
          boxShadow: `0 2px 8px ${COLORS.bg}88`,
        }}
      >
        <button
          type="button"
          title="Go up one floor"
          onClick={() => onChange((f) => f + 1)}
          style={{ fontSize: 13, lineHeight: 1, padding: "3px 10px", background: "none", border: "none", color: COLORS.info, cursor: "pointer", borderRadius: 5 }}
        >
          ▲
        </button>
        {floors.map((f) => (
          <button
            key={f}
            type="button"
            title={`Switch to ${floorLabel(f)}`}
            onClick={() => onChange(f)}
            style={{
              fontSize: 10,
              fontWeight: 700,
              fontFamily: "'JetBrains Mono', monospace",
              padding: "3px 10px",
              background: f === currentFloor ? COLORS.accent : "none",
              border: f === currentFloor ? `1px solid ${COLORS.accent}` : "1px solid transparent",
              borderRadius: 5,
              color: f === currentFloor ? "#fff" : COLORS.textDim,
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            {floorLabel(f)}
          </button>
        ))}
        <button
          type="button"
          title="Go down one floor"
          onClick={() => onChange((f) => f - 1)}
          style={{ fontSize: 13, lineHeight: 1, padding: "3px 10px", background: "none", border: "none", color: COLORS.forge, cursor: "pointer", borderRadius: 5 }}
        >
          ▼
        </button>
      </div>

      {pendingStairLink ? (
        <div
          style={{
            position: "absolute",
            top: 10,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 200,
            background: pendingStairLink.ghostDir === "up" ? COLORS.info : COLORS.forge,
            color: "#fff",
            padding: "6px 16px",
            borderRadius: 8,
            fontSize: 12,
            fontWeight: 700,
            fontFamily: "'DM Sans', sans-serif",
            display: "flex",
            alignItems: "center",
            gap: 10,
            boxShadow: "0 2px 10px #0009",
            pointerEvents: "all",
          }}
        >
          <span>
            {pendingStairLink.ghostDir === "up" ? "↑" : "↓"} Click a room to link {pendingStairLink.ghostDir} from{" "}
            <b>{pendingStairLink.slug}</b> ({floorLabel(pendingStairLink.ghostFloor)}) — ESC to cancel
          </span>
          <button
            type="button"
            onClick={onCancelStairLink}
            style={{ background: "none", border: "none", color: "#ffffffcc", cursor: "pointer", fontSize: 16, lineHeight: 1, padding: 0 }}
          >
            ✕
          </button>
        </div>
      ) : null}
    </>
  );
}
