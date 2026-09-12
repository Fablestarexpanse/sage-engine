import { useEffect, useMemo, useState, useRef } from "react";
import { deepClone } from "../utils/clone.js";
import yaml from "js-yaml";
import { joinPaths } from "../utils/paths.js";
import { useTheme } from "../ThemeContext.jsx";
import * as fs from "../utils/fsBridge.js";
import TextPromptModal from "../components/TextPromptModal.jsx";
import { useContent } from "../hooks/useContentStore.js";

export default function EntityEditor({ worldRoot, selectedId, onSelect, itemIds }) {
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
  const { entities, entityIds, dispatch, saveEntity } = useContent();
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [newIdOpen, setNewIdOpen] = useState(false);

  // Reset the draft when selection changes; on live-watch store refreshes,
  // never clobber in-progress (dirty) edits.
  const lastSelectedRef = useRef(null);
  useEffect(() => {
    if (!selectedId || !entities[selectedId]) return;
    const switched = lastSelectedRef.current !== selectedId;
    lastSelectedRef.current = selectedId;
    if (!switched && dirty) return;
    setDraft(deepClone(entities[selectedId]));
    setDirty(false);
  }, [selectedId, entities, dirty]);

  const save = async () => {
    if (!selectedId || !draft) return;
    try {
      await saveEntity(worldRoot, selectedId, draft);
    } catch (e) {
      window.alert(`Save failed: ${e}`);
      return;
    }
    setDirty(false);
  };

  const del = async () => {
    if (!selectedId || !window.confirm("Delete entity?")) return;
    await fs.deleteFile(joinPaths(worldRoot, "entities", `${selectedId}.yaml`));
    dispatch({ type: "DELETE_ENTITY", id: selectedId });
    onSelect(null);
  };

  const block = draft || {};

  return (
    <div style={{ display: "flex", height: "100%", background: COLORS.bg }}>
      <div style={{ width: 220, borderRight: `1px solid ${COLORS.border}`, overflow: "auto", background: COLORS.bgPanel }}>
        <button type="button" style={btn} onClick={() => setNewIdOpen(true)}>+ New</button>
        {entityIds.map((id) => (
          <button key={id} type="button" onClick={() => onSelect(id)} style={{ ...listBtn, background: id === selectedId ? COLORS.bgHover : "transparent" }}>
            {id}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, padding: 16, overflow: "auto" }}>
        {draft ? (
          <>
            <div style={{ color: COLORS.textDim, fontSize: 11, marginBottom: 8 }}>ID: {block.id} (rename not supported)</div>
            <label style={lbl}>Name</label>
            <input style={inp} value={block.name || ""} onChange={(e) => { setDraft({ ...draft, name: e.target.value }); setDirty(true); }} />
            <label style={lbl}>Type</label>
            <select style={inp} value={block.type || "creature"} onChange={(e) => { setDraft({ ...draft, type: e.target.value }); setDirty(true); }}>
              {["creature", "npc", "vendor", "boss", "ambient"].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <label style={lbl}>Short description</label>
            <input style={inp} value={block.description?.short || ""} onChange={(e) => { setDraft({ ...draft, description: { ...(draft.description || {}), short: e.target.value } }); setDirty(true); }} />
            <label style={lbl}>Long description</label>
            <textarea style={{ ...inp, minHeight: 80 }} value={block.description?.long || ""} onChange={(e) => { setDraft({ ...draft, description: { ...(draft.description || {}), long: e.target.value } }); setDirty(true); }} />
            <label style={lbl}>Stats</label>
            {["hp", "max_hp", "attack", "defense"].map((k) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ width: 70, fontSize: 11, color: COLORS.textMuted }}>{k}</span>
                <input type="number" style={{ ...inp, flex: 1 }} value={block.stats?.[k] ?? 0} onChange={(e) => {
                  setDraft({ ...draft, stats: { ...(draft.stats || {}), [k]: Number(e.target.value) } });
                  setDirty(true);
                }} />
              </div>
            ))}
            <label style={lbl}>Loot (item ids, comma-separated)</label>
            <input style={inp} value={(block.loot || []).join(", ")} onChange={(e) => {
              setDraft({ ...draft, loot: e.target.value.split(/,\s*/).filter(Boolean) });
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
          <div style={{ color: COLORS.textMuted }}>Select an entity.</div>
        )}
      </div>
      <TextPromptModal
        open={newIdOpen}
        title="New entity"
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
            type: "creature",
            description: { short: "", long: "" },
            stats: { hp: 10, max_hp: 10, attack: 1, defense: 1 },
            tags: [],
            loot: [],
          };
          saveEntity(worldRoot, id, base)
            .then(() => {
              onSelect(id);
            })
            .catch((e) => window.alert(`Create failed: ${e}`));
        }}
        onCancel={() => setNewIdOpen(false)}
      />
    </div>
  );
}
