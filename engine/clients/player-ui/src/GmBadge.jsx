import { usePlayTheme } from "./PlayThemeContext.jsx";

/** In-game GM marker: pink crown + label (account flag, not staff console login). */
export function GmBadge({ style = {} }) {
  const { T } = usePlayTheme();
  const g = T.gmBadge;
  return (
    <span
      title="Game Master"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        marginLeft: 6,
        padding: "2px 8px",
        borderRadius: T.radius.md,
        background: g.bg,
        border: `1px solid ${g.border}`,
        color: g.text,
        fontSize: 9,
        fontWeight: 700,
        fontFamily: T.font.body,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        verticalAlign: "middle",
        lineHeight: 1.2,
        ...style,
      }}
    >
      <span aria-hidden style={{ fontSize: 11, lineHeight: 1 }}>
        👑
      </span>
      GM
    </span>
  );
}
