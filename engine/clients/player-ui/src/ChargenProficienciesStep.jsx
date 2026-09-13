import { useState } from "react";
import { ChargenSkillPicker } from "./ChargenSkillPicker.jsx";
import { playMediaUrl } from "./playApi.js";
import { PORTRAIT_ASPECT_RATIO_CSS } from "./portraitProfile.js";
import { usePlayTheme } from "./PlayThemeContext.jsx";

/**
 * Full-screen-style step for allocating starter proficiency points after identity/portrait.
 */
export function ChargenProficienciesStep({
  characterName,
  portraitUrl,
  portraitBust,
  budget,
  maxPerLeaf,
  leaves,
  catalogLoading,
  catalogErr,
  value,
  onChange,
  disabled,
  onBack,
}) {
  const { T } = usePlayTheme();
  const used = Object.values(value || {}).reduce((a, n) => a + (Number(n) || 0), 0);
  const remaining = Math.max(0, budget - used);
  const pct = budget > 0 ? Math.min(100, (used / budget) * 100) : 0;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) minmax(320px, 2fr)",
        gap: 20,
        alignItems: "start",
      }}
      className="chargen-prof-grid"
    >
      <aside
        style={{
          position: "sticky",
          top: 8,
          display: "flex",
          flexDirection: "column",
          gap: 14,
          minWidth: 0,
        }}
      >
        <div
          style={{
            borderRadius: T.radius.lg,
            border: `1px solid ${T.border.medium}`,
            background: T.bg.panel,
            padding: "14px 16px",
          }}
        >
          <div style={{ fontSize: 10, color: T.text.muted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
            Conduit preview
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div
              style={{
                width: 52,
                aspectRatio: PORTRAIT_ASPECT_RATIO_CSS,
                borderRadius: T.radius.md,
                border: `1px solid ${T.border.dim}`,
                overflow: "hidden",
                flexShrink: 0,
                background: portraitUrl ? undefined : T.bg.surface,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {portraitUrl ? (
                <img
                  src={playMediaUrl(portraitUrl, portraitBust)}
                  alt=""
                  style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "center" }}
                />
              ) : (
                <span style={{ fontSize: 18, color: T.glyph.violet }}>◈</span>
              )}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: T.font.display, fontSize: 16, color: T.text.primary, fontWeight: 700 }}>{characterName}</div>
              <p style={{ fontSize: 11, color: T.text.muted, margin: "6px 0 0", lineHeight: 1.45 }}>
                Portrait can still generate on the server if you skipped preview. This step only sets your optional starting ranks.
              </p>
            </div>
          </div>
        </div>

        <Explainer title="What you are doing" T={T} defaultOpen>
          You are placing a small number of <strong style={{ color: T.text.accent }}>starter ranks</strong> on individual skills from
          the world catalog. These are not a full build — they nudge your character’s early aptitude so the MUD has something to grow
          from.
        </Explainer>
        <Explainer title="Budget & caps" T={T}>
          You have <strong style={{ color: T.text.accent }}>{budget}</strong> points total. Any single skill can only receive up to{" "}
          <strong style={{ color: T.text.accent }}>{maxPerLeaf}</strong> points here. Leaving points unspent is normal; you earn more
          through play, training, and field experience.
        </Explainer>
        <Explainer title="How to think about it" T={T}>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, lineHeight: 1.55 }}>
            <li>
              <strong style={{ color: T.text.secondary }}>Concept first:</strong> pick domains that match how you imagine this person
              solving problems (piloting, medicine, social, tech, etc.).
            </li>
            <li>
              <strong style={{ color: T.text.secondary }}>Breadth vs spike:</strong> a few 1s across related skills reads as well-rounded;
              one 4–5 reads as a signature strength you lean on early.
            </li>
            <li>
              <strong style={{ color: T.text.secondary }}>Ignore noise:</strong> use search and domain filters — the full list is large by
              design.
            </li>
          </ul>
        </Explainer>
        <Explainer title="After you enter the world" T={T}>
          Use the <code style={{ fontSize: 10, color: T.text.accent }}>score</code> command for conduit resonance and highlights, and{" "}
          <code style={{ fontSize: 10, color: T.text.accent }}>prof</code> for the full proficiency sheet. Ranks change with time and
          story; this screen is only the opening stance.
        </Explainer>

        <div
          style={{
            borderRadius: T.radius.lg,
            border: `1px solid ${T.border.glyph}`,
            background: T.glyph.violetDim,
            padding: "12px 14px",
          }}
        >
          <div style={{ fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
            Points remaining
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontFamily: T.font.display, fontSize: 28, color: T.text.accent, fontWeight: 700 }}>{remaining}</span>
            <span style={{ fontSize: 12, color: T.text.muted }}>/ {budget}</span>
          </div>
          <div
            style={{
              marginTop: 10,
              height: 6,
              borderRadius: 99,
              background: T.bg.deep,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${pct}%`,
                height: "100%",
                borderRadius: 99,
                background: `linear-gradient(90deg, ${T.glyph.violet}, ${T.glyph.cyan})`,
                transition: "width 0.2s ease",
              }}
            />
          </div>
        </div>
      </aside>

      <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 12 }}>
        {catalogLoading ? (
          <p style={{ fontSize: 12, color: T.text.muted }}>Loading skill catalog…</p>
        ) : catalogErr ? (
          <p style={{ fontSize: 12, color: T.text.danger, lineHeight: 1.5 }}>
            {catalogErr}{" "}
            <span style={{ color: T.text.muted }}>You can still finish creation — starter ranks will be skipped.</span>
          </p>
        ) : leaves?.length ? (
          <ChargenSkillPicker
            variant="full"
            budget={budget}
            maxPerLeaf={maxPerLeaf}
            leaves={leaves}
            value={value}
            onChange={onChange}
            disabled={disabled}
          />
        ) : (
          <p style={{ fontSize: 12, color: T.text.muted }}>
            Catalog not ready yet — use <strong style={{ color: T.text.secondary }}>Back</strong> and try Continue again in a moment, or
            create without ranks.
          </p>
        )}

        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
          <button
            type="button"
            disabled={disabled}
            onClick={onBack}
            style={{
              padding: "10px 16px",
              borderRadius: T.radius.md,
              border: `1px solid ${T.border.medium}`,
              background: T.bg.surface,
              color: T.text.secondary,
              fontSize: 12,
              fontWeight: 600,
              cursor: disabled ? "not-allowed" : "pointer",
            }}
          >
            ← Back to identity & portrait
          </button>
        </div>
      </div>

      <style>{`
        @media (max-width: 900px) {
          .chargen-prof-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
}

function Explainer({ title, children, T, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      style={{
        borderRadius: T.radius.lg,
        border: `1px solid ${T.border.dim}`,
        background: T.bg.surface,
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          textAlign: "left",
          padding: "10px 12px",
          border: "none",
          background: open ? T.bg.panel : T.bg.surface,
          color: T.text.primary,
          fontSize: 11,
          fontWeight: 700,
          fontFamily: T.font.display,
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
        }}
      >
        {title}
        <span style={{ fontSize: 10, color: T.text.muted }}>{open ? "−" : "+"}</span>
      </button>
      {open ? (
        <div style={{ fontSize: 11, color: T.text.secondary, lineHeight: 1.55, padding: "0 12px 12px" }}>{children}</div>
      ) : null}
    </div>
  );
}
