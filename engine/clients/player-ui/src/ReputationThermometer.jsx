import { clamp } from "./theme.js";
import { usePlayTheme } from "./PlayThemeContext.jsx";

/** Red (evil) → amber → green (good); marker shows current reputation on -100..+100 scale. */
export function ReputationThermometer({ reputation = 0, compact = false }) {
  const { T } = usePlayTheme();
  const r = clamp(Number(reputation) || 0, -100, 100);
  const pct = ((r + 100) / 200) * 100;
  const tone =
    r <= -20
      ? { word: "Hostile", color: T.reputation.evil }
      : r >= 20
        ? { word: "Honored", color: T.reputation.good }
        : { word: "Neutral", color: T.text.muted };
  const barH = compact ? 8 : 12;
  const insetShadow = compact ? "inset 0 1px 1px rgba(0,0,0,0.2)" : "inset 0 1px 2px rgba(0,0,0,0.35)";
  const repTitle = `Reputation ${r} (-100 hostile … +100 virtuous)`;
  return (
    <div style={{ marginBottom: compact ? 0 : 10 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 8,
          marginBottom: compact ? 4 : 5,
        }}
      >
        <div
          style={{
            fontSize: compact ? 7 : 8,
            fontFamily: T.font.body,
            color: T.text.muted,
            textTransform: "uppercase",
            letterSpacing: compact ? "0.08em" : "0.11em",
          }}
        >
          Reputation
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span style={{ fontSize: compact ? 8 : 9, fontFamily: T.font.body, color: tone.color, fontWeight: 600 }}>
            {tone.word}
          </span>
          <span style={{ fontSize: compact ? 10 : 11, fontFamily: T.font.mono, color: T.text.secondary }}>
            {r > 0 ? `+${r}` : r}
          </span>
        </div>
      </div>
      <div
        style={{
          position: "relative",
          height: barH,
          borderRadius: barH / 2,
          overflow: "hidden",
          border: `1px solid ${T.border.dim}`,
          boxShadow: insetShadow,
        }}
        title={repTitle}
      >
        <div
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            background: `linear-gradient(90deg, ${T.reputation.evil} 0%, ${T.reputation.mid} 50%, ${T.reputation.good} 100%)`,
            opacity: 0.85,
          }}
        />
        <div
          aria-hidden
          style={{
            position: "absolute",
            left: `${pct}%`,
            top: 1,
            bottom: 1,
            width: compact ? 2 : 3,
            marginLeft: compact ? -1 : -1.5,
            borderRadius: 1,
            background: "#f8fafc",
            boxShadow: "0 0 0 1px rgba(0,0,0,0.75), 0 0 8px rgba(255,255,255,0.35)",
          }}
        />
      </div>
      {!compact ? (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 3,
            fontSize: 7,
            fontFamily: T.font.body,
            color: T.text.muted,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
          }}
        >
          <span style={{ color: `${T.reputation.evil}cc` }}>Evil</span>
          <span style={{ color: `${T.reputation.good}cc` }}>Good</span>
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 2,
            fontSize: 6,
            fontFamily: T.font.body,
            color: T.text.muted,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
          }}
        >
          <span style={{ color: `${T.reputation.evil}cc` }}>Evil</span>
          <span style={{ color: `${T.reputation.good}cc` }}>Good</span>
        </div>
      )}
    </div>
  );
}
