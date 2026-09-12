import { useEffect, useMemo, useState, useRef } from "react";
import { deepClone } from "../utils/clone.js";
import yaml from "js-yaml";
import { joinPaths } from "../utils/paths.js";
import { useTheme } from "../ThemeContext.jsx";
import * as fs from "../hooks/useFileSystem.js";
import TextPromptModal from "../components/TextPromptModal.jsx";
import { useContent } from "../hooks/useContentStore.js";

const CATEGORIES = ["combat", "defense", "utility", "perception", "movement", "social"];
const SLOTS = ["forearm", "upper_arm", "chest", "back", "calf", "thigh", "palm", "temple", "spine", "shoulder"];
const EFFECT_TYPES = ["damage", "heal", "buff", "debuff", "movement", "utility"];

export default function GlyphEditor({ worldRoot, selectedId, onSelect }) {
  const { colors: COLORS } = useTheme();
  const btn = useMemo(
    () => ({
      padding: "8px 12px",
      margin: 8,
      borderRadius: 6,
      border: `1px solid ${COLORS.border}`,
      background: COLORS.bgCard,
      color: COLORS.text,
      cursor: "pointer",
      fontSize: 12,
    }),
    [COLORS]
  );
  const listBtn = useMemo(
    () => ({
      display: "block",
      width: "100%",
      textAlign: "left",
      padding: "8px 10px",
      border: "none",
      color: COLORS.text,
      cursor: "pointer",
      fontSize: 12,
    }),
    [COLORS]
  );
  const lbl = useMemo(
    () => ({ display: "block", fontSize: 10, color: COLORS.textMuted, marginTop: 10, marginBottom: 4 }),
    [COLORS]
  );
  const inp = useMemo(
    () => ({
      width: "100%",
      maxWidth: 480,
      boxSizing: "border-box",
      padding: 8,
      borderRadius: 6,
      border: `1px solid ${COLORS.border}`,
      background: COLORS.bgInput,
      color: COLORS.text,
      fontSize: 12,
    }),
    [COLORS]
  );
  const { glyphs, glyphIds, dispatch, saveGlyph } = useContent();
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [newIdOpen, setNewIdOpen] = useState(false);

  // Reset the draft when selection changes; on live-watch store refreshes,
  // never clobber in-progress (dirty) edits.
  const lastSelectedRef = useRef(null);
  useEffect(() => {
    if (!selectedId || !glyphs[selectedId]) return;
    const switched = lastSelectedRef.current !== selectedId;
    lastSelectedRef.current = selectedId;
    if (!switched && dirty) return;
    setDraft(deepClone(glyphs[selectedId]));
    setDirty(false);
  }, [selectedId, glyphs, dirty]);

  const save = async () => {
    if (!selectedId || !draft) return;
    try {
      await saveGlyph(worldRoot, selectedId, draft);
    } catch (e) {
      window.alert(`Save failed: ${e}`);
      return;
    }
    setDirty(false);
  };

  const del = async () => {
    if (!selectedId || !window.confirm("Delete glyph?")) return;
    await fs.deleteFile(joinPaths(worldRoot, "glyphs", `${selectedId}.yaml`));
    dispatch({ type: "DELETE_GLYPH", id: selectedId });
    onSelect(null);
  };

  const block = draft || {};

  return (
    <div style={{ display: "flex", height: "100%", background: COLORS.bg }}>
      <div style={{ width: 220, borderRight: `1px solid ${COLORS.border}`, overflow: "auto", background: COLORS.bgPanel }}>
        <button type="button" style={btn} onClick={() => setNewIdOpen(true)}>+ New</button>
        {glyphIds.map((id) => (
          <button key={id} type="button" onClick={() => onSelect(id)} style={{ ...listBtn, background: id === selectedId ? COLORS.bgHover : "transparent" }}>{id}</button>
        ))}
      </div>
      <div style={{ flex: 1, padding: 16, overflow: "auto" }}>
        {draft ? (
          <>
            <div style={{ color: COLORS.textDim, fontSize: 11 }}>ID: {block.id}</div>
            <label style={lbl}>Name</label>
            <input style={inp} value={block.name || ""} onChange={(e) => { setDraft({ ...draft, name: e.target.value }); setDirty(true); }} />
            <label style={lbl}>Category</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {CATEGORIES.map((c) => (
                <button key={c} type="button" onClick={() => { setDraft({ ...draft, category: c }); setDirty(true); }} style={{
                  padding: "4px 8px", borderRadius: 4, border: `1px solid ${block.category === c ? COLORS.accent : COLORS.border}`,
                  background: block.category === c ? `${COLORS.accent}22` : COLORS.bgInput, color: COLORS.text, cursor: "pointer", fontSize: 11,
                }}>{c}</button>
              ))}
            </div>
            <label style={lbl}>Tier</label>
            <div style={{ display: "flex", gap: 6 }}>
              {[1, 2, 3, 4, 5].map((t) => (
                <button key={t} type="button" onClick={() => { setDraft({ ...draft, tier: t }); setDirty(true); }} style={{
                  width: 32, height: 28, borderRadius: 4, border: `1px solid ${block.tier === t ? COLORS.accent : COLORS.border}`,
                  background: block.tier === t ? `${COLORS.accent}22` : COLORS.bgInput, color: COLORS.text, cursor: "pointer",
                }}>{t}</button>
              ))}
            </div>
            <label style={lbl}>Body slot</label>
            <select style={inp} value={block.body_slot || "forearm"} onChange={(e) => { setDraft({ ...draft, body_slot: e.target.value }); setDirty(true); }}>
              {SLOTS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <label style={lbl}>Description</label>
            <textarea style={{ ...inp, minHeight: 60 }} value={block.description || ""} onChange={(e) => { setDraft({ ...draft, description: e.target.value }); setDirty(true); }} />
            <label style={lbl}>Inscription</label>
            <textarea style={{ ...inp, minHeight: 60 }} value={block.inscription || ""} onChange={(e) => { setDraft({ ...draft, inscription: e.target.value }); setDirty(true); }} />
            <label style={lbl}>Effect</label>
            <select style={inp} value={block.effect?.type || "damage"} onChange={(e) => { setDraft({ ...draft, effect: { ...(draft.effect || {}), type: e.target.value } }); setDirty(true); }}>
              {EFFECT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            {["magnitude", "duration", "cooldown"].map((k) => (
              <div key={k} style={{ marginTop: 6 }}>
                <span style={{ fontSize: 10, color: COLORS.textMuted }}>{k}</span>
                <input type="number" style={inp} value={block.effect?.[k] ?? 0} onChange={(e) => {
                  setDraft({ ...draft, effect: { ...(draft.effect || {}), [k]: Number(e.target.value) } });
                  setDirty(true);
                }} />
              </div>
            ))}
            <label style={lbl}>Energy cost</label>
            <input type="number" style={inp} value={block.cost?.energy ?? 0} onChange={(e) => {
              setDraft({ ...draft, cost: { ...(draft.cost || {}), energy: Number(e.target.value) } });
              setDirty(true);
            }} />
            <label style={lbl}>Prerequisites (comma-separated glyph ids)</label>
            <input style={inp} value={(block.prerequisites || []).join(", ")} onChange={(e) => {
              setDraft({ ...draft, prerequisites: e.target.value.split(/,\s*/).filter(Boolean) });
              setDirty(true);
            }} />
            <label style={lbl}>Tags (comma-separated)</label>
            <input style={inp} value={(block.tags || []).join(", ")} onChange={(e) => {
              setDraft({ ...draft, tags: e.target.value.split(/,\s*/).filter(Boolean) });
              setDirty(true);
            }} />
            <label style={lbl}>YAML</label>
            <textarea style={{ ...inp, minHeight: 160, fontFamily: "monospace", fontSize: 11 }} readOnly value={yaml.dump(draft, { lineWidth: 120, quotingType: '"' })} />
            <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button type="button" style={btn} onClick={save} disabled={!dirty}>Save</button>
              <button type="button" style={{ ...btn, color: COLORS.danger }} onClick={del}>Delete</button>
            </div>
          </>
        ) : (
          <div style={{ color: COLORS.textMuted }}>Select a glyph.</div>
        )}
      </div>
      <TextPromptModal
        open={newIdOpen}
        title="New glyph"
        hint="Letters, numbers, underscore, and hyphen only."
        initialValue=""
        confirmLabel="Create"
        validate={(v) => /^[a-zA-Z0-9_-]+$/.test(v)}
        invalidMessage="Use only letters, numbers, underscore (_), and hyphen (-)."
        onConfirm={(id) => {
          setNewIdOpen(false);
      const base = {
      id,
      name: id,
      category: "combat",
      tier: 1,
      body_slot: "forearm",
      description: "",
      inscription: "",
      effect: { type: "damage", magnitude: 0, duration: 0, cooldown: 0 },
      cost: { energy: 0 },
      prerequisites: [],
      tags: [],
      };
      saveGlyph(worldRoot, id, base).then(() => {
      dispatch({ type: "ADD_GLYPH_ID", id });
      onSelect(id);
      }).catch((e) => window.alert(`Create failed: ${e}`));

        }}
        onCancel={() => setNewIdOpen(false)}
      />
    </div>
  );
}
