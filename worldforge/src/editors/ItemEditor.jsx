import { useEffect, useMemo, useState, useRef } from "react";
import { deepClone } from "../utils/clone.js";
import yaml from "js-yaml";
import { joinPaths } from "../utils/paths.js";
import { useTheme } from "../ThemeContext.jsx";
import * as fs from "../hooks/useFileSystem.js";
import TextPromptModal from "../components/TextPromptModal.jsx";
import { useContent } from "../hooks/useContentStore.js";

export default function ItemEditor({ worldRoot, selectedId, onSelect }) {
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
  const { items, itemIds, dispatch } = useContent();
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [newIdOpen, setNewIdOpen] = useState(false);

  // Reset the draft when selection changes; on live-watch store refreshes,
  // never clobber in-progress (dirty) edits.
  const lastSelectedRef = useRef(null);
  useEffect(() => {
    if (!selectedId || !items[selectedId]) return;
    const switched = lastSelectedRef.current !== selectedId;
    lastSelectedRef.current = selectedId;
    if (!switched && dirty) return;
    setDraft(deepClone(items[selectedId]));
    setDirty(false);
  }, [selectedId, items, dirty]);

  const save = async () => {
    if (!selectedId || !draft) return;
    await fs.writeYaml(joinPaths(worldRoot, "items", `${selectedId}.yaml`), draft);
    dispatch({ type: "UPDATE_ITEM", id: selectedId, data: draft });
    setDirty(false);
  };

  const del = async () => {
    if (!selectedId || !window.confirm("Delete item?")) return;
    await fs.deleteFile(joinPaths(worldRoot, "items", `${selectedId}.yaml`));
    dispatch({ type: "DELETE_ITEM", id: selectedId });
    onSelect(null);
  };

  const block = draft || {};

  return (
    <div style={{ display: "flex", height: "100%", background: COLORS.bg }}>
      <div style={{ width: 220, borderRight: `1px solid ${COLORS.border}`, overflow: "auto", background: COLORS.bgPanel }}>
        <button type="button" style={btn} onClick={() => setNewIdOpen(true)}>+ New</button>
        {itemIds.map((id) => (
          <button key={id} type="button" onClick={() => onSelect(id)} style={{ ...listBtn, background: id === selectedId ? COLORS.bgHover : "transparent" }}>{id}</button>
        ))}
      </div>
      <div style={{ flex: 1, padding: 16, overflow: "auto" }}>
        {draft ? (
          <>
            <div style={{ color: COLORS.textDim, fontSize: 11 }}>ID: {block.id}</div>
            <label style={lbl}>Name</label>
            <input style={inp} value={block.name || ""} onChange={(e) => { setDraft({ ...draft, name: e.target.value }); setDirty(true); }} />
            <label style={lbl}>Type</label>
            <select style={inp} value={block.type || "misc"} onChange={(e) => { setDraft({ ...draft, type: e.target.value }); setDirty(true); }}>
              {["weapon", "armor", "consumable", "material", "key", "lore", "misc"].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <label style={lbl}>Description</label>
            <textarea style={{ ...inp, minHeight: 100 }} value={block.description || ""} onChange={(e) => { setDraft({ ...draft, description: e.target.value }); setDirty(true); }} />
            <label style={lbl}>Value</label>
            <input type="number" style={inp} value={block.value ?? 0} onChange={(e) => { setDraft({ ...draft, value: Number(e.target.value) }); setDirty(true); }} />
            <label style={lbl}>Weight</label>
            <input type="number" step={0.1} style={inp} value={block.weight ?? 0} onChange={(e) => { setDraft({ ...draft, weight: Number(e.target.value) }); setDirty(true); }} />
            <label style={lbl}>YAML</label>
            <textarea style={{ ...inp, minHeight: 140, fontFamily: "monospace", fontSize: 11 }} readOnly value={yaml.dump(draft, { lineWidth: 120, quotingType: '"' })} />
            <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button type="button" style={btn} onClick={save} disabled={!dirty}>Save</button>
              <button type="button" style={{ ...btn, color: COLORS.danger }} onClick={del}>Delete</button>
            </div>
          </>
        ) : (
          <div style={{ color: COLORS.textMuted }}>Select an item.</div>
        )}
      </div>
      <TextPromptModal
        open={newIdOpen}
        title="New item"
        hint="Letters, numbers, underscore, and hyphen only."
        initialValue=""
        confirmLabel="Create"
        validate={(v) => /^[a-zA-Z0-9_-]+$/.test(v)}
        invalidMessage="Use only letters, numbers, underscore (_), and hyphen (-)."
        onConfirm={(id) => {
          setNewIdOpen(false);
      const base = { id, name: id, type: "misc", description: "", value: 0, weight: 0, tags: [] };
      fs.writeYaml(joinPaths(worldRoot, "items", `${id}.yaml`), base).then(() => {
      dispatch({ type: "UPDATE_ITEM", id, data: base });
      dispatch({ type: "ADD_ITEM_ID", id });
      onSelect(id);
      });

        }}
        onCancel={() => setNewIdOpen(false)}
      />
    </div>
  );
}
