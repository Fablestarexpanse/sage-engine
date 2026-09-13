/** Shared style tokens for RoomPanel and its extracted sub-panels (SceneArtPanel, etc.). */
export function roomPanelChrome(COLORS) {
  const lbl = { display: "block", fontSize: 10, color: COLORS.textMuted, marginBottom: 4, marginTop: 8 };
  const inp = {
    width: "100%",
    boxSizing: "border-box",
    padding: "8px 10px",
    borderRadius: 6,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgInput,
    color: COLORS.text,
    fontSize: 12,
  };
  const btn = {
    padding: "8px 14px",
    borderRadius: 6,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgCard,
    color: COLORS.text,
    cursor: "pointer",
    fontSize: 12,
  };
  return {
    lbl,
    inp,
    btn,
    btnPrimary: { ...btn, background: `${COLORS.accent}33`, borderColor: COLORS.accent },
    btnDanger: { ...btn, color: COLORS.danger, borderColor: COLORS.danger },
  };
}
