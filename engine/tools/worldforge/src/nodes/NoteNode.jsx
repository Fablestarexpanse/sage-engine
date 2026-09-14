import { memo, useState } from "react";
import { useTheme } from "../ThemeContext.jsx";

const VARIANTS = {
  yellow: { fill: "rgba(251, 191, 36, 0.12)", border: "rgba(251, 191, 36, 0.45)" },
  red: { fill: "rgba(248, 113, 113, 0.12)", border: "rgba(248, 113, 113, 0.5)" },
  green: { fill: "rgba(52, 211, 153, 0.12)", border: "rgba(52, 211, 153, 0.45)" },
  blue: { fill: "rgba(96, 165, 250, 0.12)", border: "rgba(96, 165, 250, 0.45)" },
};

export default memo(function NoteNode({ id, data, selected }) {
  const { colors: COLORS } = useTheme();
  const [editing, setEditing] = useState(false);
  const v = VARIANTS[data.color] || VARIANTS.yellow;
  return (
    <div
      onDoubleClick={() => setEditing(true)}
      style={{
        minWidth: 120,
        maxWidth: 220,
        padding: "8px 10px",
        borderRadius: 8,
        background: v.fill,
        border: `1px solid ${selected ? COLORS.accent : v.border}`,
        color: COLORS.text,
        fontSize: 11,
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      {editing ? (
        <textarea
          autoFocus
          defaultValue={data.text || ""}
          onBlur={(e) => {
            data.onChangeText?.(id, e.target.value);
            setEditing(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") setEditing(false);
          }}
          style={{
            width: "100%",
            minHeight: 48,
            background: COLORS.bgInput,
            color: COLORS.text,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 4,
            fontSize: 11,
            resize: "vertical",
          }}
        />
      ) : (
        <div style={{ whiteSpace: "pre-wrap" }}>{data.text || "Note"}</div>
      )}
    </div>
  );
});
