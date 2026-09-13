import { useCallback, useEffect, useMemo, useState } from "react";
import { useTheme } from "../ThemeContext.jsx";
import { deleteStampFolder, listStampSlugs, loadStampBundle, stampFolderPath } from "../utils/stampBundle.js";
import StampPreviewMini from "./StampPreviewMini.jsx";

/**
 * @param {object} props
 * @param {boolean} props.open
 * @param {string} props.worldRoot
 * @param {(stampSlug: string) => void} props.onPlaceInZone
 * @param {() => void} props.onClose
 */
export default function StampLibraryModal({ open, worldRoot, onPlaceInZone, onClose }) {
  const { colors: COLORS } = useTheme();
  const btn = useMemo(
    () => ({
      padding: "6px 12px",
      borderRadius: 8,
      border: `1px solid ${COLORS.border}`,
      background: COLORS.bgCard,
      color: COLORS.text,
      fontSize: 12,
      cursor: "pointer",
    }),
    [COLORS]
  );
  const [slugs, setSlugs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const refresh = useCallback(async () => {
    if (!worldRoot) {
      setSlugs([]);
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const list = await listStampSlugs(worldRoot);
      setSlugs(list);
      setSelected((cur) => (cur && list.includes(cur) ? cur : list[0] || null));
    } catch {
      setSlugs([]);
      setMsg("Could not list stamps.");
    } finally {
      setBusy(false);
    }
  }, [worldRoot]);

  useEffect(() => {
    if (!open) return;
    refresh();
  }, [open, refresh]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!open || !worldRoot || !selected) {
        setPreview(null);
        return;
      }
      const b = await loadStampBundle(worldRoot, selected);
      if (cancelled) return;
      setPreview(b);
    })();
    return () => {
      cancelled = true;
    };
  }, [open, worldRoot, selected]);

  if (!open) return null;

  const onDelete = async () => {
    if (!selected || !worldRoot) return;
    if (!window.confirm(`Delete stamp “${selected}” and its folder?`)) return;
    setBusy(true);
    try {
      await deleteStampFolder(worldRoot, selected);
      setPreview(null);
      await refresh();
      setMsg("Stamp deleted.");
    } catch {
      setMsg("Delete failed.");
    } finally {
      setBusy(false);
    }
  };

  const meta = preview?.meta;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        background: `${COLORS.bg}dd`,
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 720,
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          background: COLORS.bgCard,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 12,
          overflow: "hidden",
          boxShadow: `0 12px 40px ${COLORS.bg}cc`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: `1px solid ${COLORS.border}` }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text }}>Stamp library</div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" style={btn} disabled={busy} onClick={() => refresh()}>
              Refresh
            </button>
            <button type="button" style={btn} onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div style={{ display: "flex", flex: 1, minHeight: 320, overflow: "hidden" }}>
          <div
            style={{
              width: 200,
              flexShrink: 0,
              borderRight: `1px solid ${COLORS.border}`,
              overflowY: "auto",
              background: COLORS.bgPanel,
            }}
          >
            {slugs.length === 0 ? (
              <div style={{ padding: 12, fontSize: 11, color: COLORS.textDim }}>{busy ? "Loading…" : "No stamps yet."}</div>
            ) : (
              slugs.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSelected(s)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 12px",
                    border: "none",
                    borderBottom: `1px solid ${COLORS.border}`,
                    background: selected === s ? `${COLORS.accent}22` : "transparent",
                    color: COLORS.text,
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {s}
                </button>
              ))
            )}
          </div>
          <div style={{ flex: 1, padding: 16, overflowY: "auto", minWidth: 0 }}>
            {selected && meta ? (
              <>
                <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.text, marginBottom: 4 }}>{meta.display_name || selected}</div>
                <div style={{ fontSize: 11, color: COLORS.textDim, marginBottom: 12 }}>
                  <code>{stampFolderPath(worldRoot, selected)}</code>
                  {meta.created_at ? <span> · {meta.created_at}</span> : null}
                </div>
                {preview?.roomsMap && preview?.positionsDoc ? <StampPreviewMini roomsMap={preview.roomsMap} positionsDoc={preview.positionsDoc} /> : null}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
                  <button
                    type="button"
                    style={{ ...btn, borderColor: COLORS.accent, background: `${COLORS.accent}18`, color: COLORS.accent }}
                    disabled={busy}
                    onClick={() => {
                      onPlaceInZone(selected);
                      onClose();
                    }}
                  >
                    Place in current zone…
                  </button>
                  <button
                    type="button"
                    style={{ ...btn, borderColor: COLORS.danger, color: COLORS.danger, background: `${COLORS.danger}12` }}
                    disabled={busy}
                    onClick={() => onDelete()}
                  >
                    Delete stamp
                  </button>
                </div>
              </>
            ) : selected ? (
              <div style={{ fontSize: 12, color: COLORS.textDim }}>Loading preview…</div>
            ) : (
              <div style={{ fontSize: 12, color: COLORS.textDim }}>Select a stamp or save one from the zone toolbar.</div>
            )}
            {msg ? <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 10 }}>{msg}</div> : null}
          </div>
        </div>
      </div>
    </div>
  );
}
