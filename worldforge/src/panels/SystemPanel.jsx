import { useMemo, useState } from "react";
import { deepClone } from "../utils/clone.js";
import yaml from "js-yaml";
import { useTheme } from "../ThemeContext.jsx";

export default function SystemPanel({ rawDoc, onChangeDoc, onSave, onRevert, dirty }) {
  const { colors: COLORS } = useTheme();
  const lbl = useMemo(
    () => ({ display: "block", fontSize: 10, color: COLORS.textMuted, marginTop: 8, marginBottom: 4 }),
    [COLORS]
  );
  const inp = useMemo(
    () => ({
      width: "100%",
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
  const btn = useMemo(
    () => ({
      padding: "8px 12px",
      borderRadius: 6,
      border: `1px solid ${COLORS.border}`,
      background: COLORS.bgCard,
      color: COLORS.text,
      cursor: "pointer",
      marginTop: 8,
    }),
    [COLORS]
  );
  const block = rawDoc?.system || rawDoc || {};
  const [yamlText, setYamlText] = useState("");

  const setField = (path, val) => {
    const next = deepClone(rawDoc || { system: {} });
    const sys = next.system || (next.system = {});
    if (path === "name") sys.name = val;
    if (path === "faction") sys.faction = val;
    if (path === "security") sys.security = val;
    if (path === "star.type") {
      sys.star = { ...(sys.star || {}), type: val };
    }
    onChangeDoc(next);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: COLORS.bgPanel }}>
      <div style={{ flex: 1, overflow: "auto", padding: 12 }}>
        <label style={lbl}>Name</label>
        <input style={inp} value={block.name || ""} onChange={(e) => setField("name", e.target.value)} />
        <label style={lbl}>Faction</label>
        <input style={inp} value={block.faction || ""} onChange={(e) => setField("faction", e.target.value)} />
        <label style={lbl}>Security</label>
        <input style={inp} value={block.security || ""} onChange={(e) => setField("security", e.target.value)} />
        <label style={lbl}>Star type</label>
        <input style={inp} value={block.star?.type || ""} onChange={(e) => setField("star.type", e.target.value)} />
        <label style={lbl}>YAML</label>
        <textarea
          style={{ ...inp, minHeight: 200, fontFamily: "monospace", fontSize: 11 }}
          value={yamlText || yaml.dump(rawDoc || {}, { lineWidth: 120, quotingType: '"' })}
          onFocus={() => setYamlText(yaml.dump(rawDoc || {}, { lineWidth: 120, quotingType: '"' }))}
          onChange={(e) => setYamlText(e.target.value)}
        />
        <button type="button" style={btn} onClick={() => onChangeDoc(yaml.load(yamlText || yaml.dump(rawDoc || {})))}>
          Parse YAML
        </button>
      </div>
      <div style={{ padding: 10, borderTop: `1px solid ${COLORS.border}`, display: "flex", gap: 8 }}>
        {dirty ? <span style={{ color: COLORS.warning, fontSize: 11 }}>Unsaved</span> : null}
        <button type="button" style={btn} onClick={onSave}>
          Save
        </button>
        <button type="button" style={btn} onClick={onRevert}>
          Revert
        </button>
      </div>
    </div>
  );
}
