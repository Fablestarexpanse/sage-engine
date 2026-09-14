import { useMemo, useState } from "react";
import { useTheme } from "../ThemeContext.jsx";

function ListItem({ item, canDelete, onDelete, COLORS }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      style={{ position: "relative", marginBottom: 2 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        onClick={item.onClick}
        style={{
          display: "block",
          width: "100%",
          textAlign: "left",
          padding: "6px 28px 6px 8px",
          borderRadius: 6,
          border: "none",
          background: item.active ? COLORS.bgHover : "transparent",
          color: COLORS.text,
          fontSize: 12,
          cursor: "pointer",
        }}
      >
        {item.label}
      </button>
      {canDelete && hovered && (
        <button
          type="button"
          title={`Delete ${item.id}`}
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          style={{
            position: "absolute",
            right: 4,
            top: "50%",
            transform: "translateY(-50%)",
            padding: "2px 5px",
            borderRadius: 4,
            border: "none",
            background: "transparent",
            color: COLORS.danger,
            cursor: "pointer",
            fontSize: 13,
            lineHeight: 1,
            opacity: 0.7,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
          onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.7")}
        >
          ✕
        </button>
      )}
    </div>
  );
}

const navBtn = {
  textAlign: "left",
  padding: "8px 10px",
  borderRadius: 6,
  fontSize: 12,
  cursor: "pointer",
};

const EDITORS = [
  { id: "zone", label: "Zone" },
  { id: "entities", label: "Entities" },
  { id: "items", label: "Items" },
];

export default function Sidebar({
  contentRoot,
  worldRoot,
  onChangeRoot,
  activeEditor,
  onEditor,
  zoneIds,
  selectedZoneId,
  onSelectZone,
  entityIds,
  selectedEntityId,
  onSelectEntity,
  itemIds,
  selectedItemId,
  onSelectItem,
  search,
  onSearch,
  nexusLive,
  onOpenSettings,
  onOpenExport,
  onRefresh,
  watching,
  onToggleWatch,
  onDeleteZone,
}) {
  const { colors: COLORS } = useTheme();
  const smallBtn = useMemo(
    () => ({
      padding: "6px 10px",
      fontSize: 11,
      borderRadius: 6,
      border: `1px solid ${COLORS.border}`,
      background: COLORS.bgCard,
      color: COLORS.text,
      cursor: "pointer",
    }),
    [COLORS]
  );
  const shortRoot = (p) => (!p ? "" : p.length > 36 ? "…" + p.slice(-34) : p);

  const treeItems = () => {
    if (activeEditor === "zone")
      return zoneIds.map((id) => ({ id, label: id, active: id === selectedZoneId, onClick: () => onSelectZone(id) }));
    if (activeEditor === "entities")
      return entityIds.map((id) => ({ id, label: id, active: id === selectedEntityId, onClick: () => onSelectEntity(id) }));
    if (activeEditor === "items")
      return itemIds.map((id) => ({ id, label: id, active: id === selectedItemId, onClick: () => onSelectItem(id) }));
    return [];
  };

  const filtered = treeItems().filter((t) => !search || t.label.toLowerCase().includes(search.toLowerCase()));

  return (
    <div
      style={{
        width: 240,
        minWidth: 240,
        background: COLORS.bgPanel,
        borderRight: `1px solid ${COLORS.border}`,
        display: "flex",
        flexDirection: "column",
        height: "100%",
      }}
    >
      <div style={{ padding: "14px 12px", borderBottom: `1px solid ${COLORS.border}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L22 8v8L12 22 2 16V8L12 2z" stroke={COLORS.accent} strokeWidth="1.5" fill={`${COLORS.accent}22`} />
          </svg>
          <span style={{ fontWeight: 700, fontSize: 15, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>SAGE WorldForge</span>
        </div>
        {worldRoot ? (
          <div style={{ marginBottom: 6 }}>
            <div style={{ fontSize: 9, color: COLORS.textDim, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>
              World root
            </div>
            <div
              title={worldRoot}
              style={{ fontSize: 10, color: COLORS.accent, wordBreak: "break-all", fontFamily: "monospace", lineHeight: 1.4 }}
            >
              {shortRoot(worldRoot)}
            </div>
          </div>
        ) : contentRoot ? (
          <div style={{ fontSize: 10, color: COLORS.textDim, wordBreak: "break-all", marginBottom: 6 }} title={contentRoot}>
            {shortRoot(contentRoot)}
          </div>
        ) : null}
        <button type="button" onClick={onChangeRoot} style={smallBtn}>
          Change folder
        </button>
      </div>

      <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 4 }}>
        {EDITORS.map((ed) => (
          <button
            key={ed.id}
            type="button"
            onClick={() => onEditor(ed.id)}
            style={{
              ...navBtn,
              background: activeEditor === ed.id ? `${COLORS.accent}28` : "transparent",
              color: activeEditor === ed.id ? COLORS.accent : COLORS.textMuted,
              border: activeEditor === ed.id ? `1px solid ${COLORS.accent}55` : "1px solid transparent",
            }}
          >
            {ed.label}
          </button>
        ))}
      </div>

      <div style={{ padding: "8px 10px", display: "flex", gap: 6, alignItems: "center" }}>
        <input
          placeholder="Search…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          style={{
            flex: 1,
            minWidth: 0,
            padding: "6px 8px",
            borderRadius: 6,
            border: `1px solid ${COLORS.border}`,
            background: COLORS.bgInput,
            color: COLORS.text,
            fontSize: 12,
          }}
        />
        {onRefresh && (
          <button
            type="button"
            title="Refresh content (picks up zones created externally)"
            onClick={onRefresh}
            style={{
              padding: "5px 7px",
              borderRadius: 6,
              border: `1px solid ${COLORS.border}`,
              background: COLORS.bgCard,
              color: COLORS.textMuted,
              cursor: "pointer",
              fontSize: 14,
              lineHeight: 1,
              flexShrink: 0,
            }}
          >
            ↺
          </button>
        )}
        {onToggleWatch && (
          <button
            type="button"
            title={watching ? "Stop live watching (currently polling every 2 s)" : "Live watch — auto-refresh as files change on disk"}
            onClick={onToggleWatch}
            style={{
              padding: "5px 7px",
              borderRadius: 6,
              border: `1px solid ${watching ? COLORS.accent : COLORS.border}`,
              background: watching ? `${COLORS.accent}22` : COLORS.bgCard,
              color: watching ? COLORS.accent : COLORS.textMuted,
              cursor: "pointer",
              fontSize: 13,
              lineHeight: 1,
              flexShrink: 0,
              transition: "all 0.15s",
            }}
          >
            {watching ? "⏹" : "👁"}
          </button>
        )}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "4px 8px 8px" }}>
        {filtered.map((t) => (
          <ListItem
            key={t.id}
            item={t}
            canDelete={activeEditor === "zone" && !!onDeleteZone}
            onDelete={() => {
              if (window.confirm(`Delete zone "${t.id}" and all its rooms? This cannot be undone.`)) {
                onDeleteZone(t.id);
              }
            }}
            COLORS={COLORS}
          />
        ))}
      </div>

      <div style={{ padding: 10, borderTop: `1px solid ${COLORS.border}` }}>
        <button type="button" style={{ ...smallBtn, width: "100%", marginBottom: 6 }} onClick={onOpenExport}>
          Export bundle…
        </button>
        <button type="button" style={{ ...smallBtn, width: "100%", marginBottom: 8 }} onClick={onOpenSettings}>
          Settings
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: COLORS.textMuted }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: nexusLive ? COLORS.success : COLORS.textDim,
            }}
          />
          {nexusLive ? "Nexus live" : "Nexus offline"}
        </div>
      </div>
    </div>
  );
}
