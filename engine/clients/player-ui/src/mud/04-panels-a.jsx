import { Tooltip } from "./01-primitives.jsx";
import { usePlayTheme } from "../PlayThemeContext.jsx";

export function AfflictionTracker({ effects = null }) {
  const { T } = usePlayTheme();
  // Server-pushed live effects only ({name, description, debuff, seconds_left}) —
  // no invented demo entries.
  const live = effects || [];
  const fmtDur = (s) => (s == null ? "∞" : `${s}s`);
  const afflictions = live
    .filter((e) => e.debuff)
    .map((e) => ({ name: e.name, icon: "⊘", dur: fmtDur(e.seconds_left), desc: e.description || "", color: T.hue.crimson }));
  const buffs = live
    .filter((e) => !e.debuff)
    .map((e) => ({ name: e.name, icon: "◈", dur: fmtDur(e.seconds_left), desc: e.description || "", color: T.hue.emerald }));
  if (!live.length) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", padding: 10 }}>
        <span style={{ fontSize: 10, fontFamily: T.font.body, color: T.text.muted }}>
          {effects === null ? "Waiting for server…" : "Nothing ails or aids you."}
        </span>
      </div>
    );
  }
  return (
    <div style={{ height: "100%", overflow: "auto", padding: 6 }}>
      {afflictions.length > 0 && (
        <>
          <div style={{ fontSize: 9, fontFamily: T.font.body, color: T.text.danger, textTransform: "uppercase", letterSpacing: "0.1em", padding: "2px 6px", marginBottom: 3 }}>Afflictions ({afflictions.length})</div>
          {afflictions.map((a, i) => (
            <Tooltip key={i} text={a.name} detail={a.desc}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 6px", marginBottom: 2, background: T.hue.crimsonDim, borderRadius: T.radius.sm, borderLeft: `3px solid ${a.color}`, cursor: "default" }}>
                <span style={{ fontSize: 13, width: 18, textAlign: "center" }}>{a.icon}</span>
                <span style={{ flex: 1, fontSize: 11, fontFamily: T.font.body, color: T.text.danger }}>{a.name}</span>
                <span style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted }}>{a.dur}</span>
              </div>
            </Tooltip>
          ))}
        </>
      )}
      <div style={{ fontSize: 9, fontFamily: T.font.body, color: T.text.success, textTransform: "uppercase", letterSpacing: "0.1em", padding: "2px 6px", margin: "6px 0 3px" }}>Buffs ({buffs.length})</div>
      {buffs.map((b, i) => (
        <Tooltip key={i} text={b.name} detail={b.desc}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 6px", marginBottom: 2, background: `${b.color}12`, borderRadius: T.radius.sm, borderLeft: `3px solid ${b.color}40`, cursor: "default" }}>
            <span style={{ fontSize: 13, width: 18, textAlign: "center" }}>{b.icon}</span>
            <span style={{ flex: 1, fontSize: 11, fontFamily: T.font.body, color: b.color }}>{b.name}</span>
            <span style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted }}>{b.dur}</span>
          </div>
        </Tooltip>
      ))}
    </div>
  );
}
