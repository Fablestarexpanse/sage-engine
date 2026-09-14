import { useAdminTheme } from "../AdminThemeContext.jsx";
import CharacterTools from "../characterTools.jsx";

// Players › Characters: find a character and act on it (move, money, items, kick).

export default function CharactersPage() {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Characters</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>Changes apply to the live character, so they are not undone by the next save, and a connected player sees a notice.</p>
      </div>
      <section style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16 }}>
        <CharacterTools />
      </section>
    </div>
  );
}
