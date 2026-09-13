import { useCallback, useEffect, useRef, useState } from "react";
import GalaxyView from "./GalaxyView.jsx";
import SystemView from "./SystemView.jsx";
import SurfaceView from "./SurfaceView.jsx";
import ZoneEditor from "./ZoneEditor.jsx";
import ShipEditor from "./ShipEditor.jsx";
import BuilderSearchPanel from "./BuilderSearchPanel.jsx";
import { useAdminTheme } from "../AdminThemeContext.jsx";

const SCALE_TABS = [
  { id: "galaxy", label: "Galaxy" },
  { id: "system", label: "System" },
  { id: "surface", label: "Surface" },
  { id: "zone", label: "Zone" },
  { id: "ship", label: "Ship" },
];

const SCALE_ICONS = {
  galaxy: "\u{1F30C}",
  system: "\u2B50",
  surface: "\u{1F30D}",
  zone: "\u25C8",
  ship: "\u{1F680}",
};

function readInitialNav() {
  try {
    const raw = sessionStorage.getItem("fs_builder_initial");
    if (!raw) return null;
    sessionStorage.removeItem("fs_builder_initial");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function contextHint(scale, crumb) {
  switch (scale) {
    case "galaxy":
      return "Galaxy map: open a system, filter stars, or add a new system.";
    case "system":
      return "Tabs: Overview, Connections, Bodies, Ships, YAML. Header saves the whole system file.";
    case "surface":
      return "Zone index: choose a zone to open the room graph.";
    case "zone":
      return crumb?.id
        ? `Room graph for zone “${crumb.label}”. Connect rooms, then save positions or room YAML from the side panel.`
        : "Pick a zone from Surface or search.";
    case "ship":
      return crumb?.id
        ? `Interior layout for ship template “${crumb.label}”. Exits use self:room links.`
        : "Open a ship from a system or search.";
    default:
      return "";
  }
}

export default function WorldBuilderPage() {
  const { colors: COLORS } = useAdminTheme();
  const hdrBtnStyle = (disabled) => ({
    padding: "6px 12px",
    fontSize: 12,
    fontWeight: 600,
    borderRadius: 6,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgCard,
    color: COLORS.text,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.5 : 1,
    fontFamily: "'DM Sans', sans-serif",
  });
  const [crumbs, setCrumbs] = useState(() => [{ scale: "galaxy", id: null, label: "Galaxy" }]);
  const [navigateRoomSlug, setNavigateRoomSlug] = useState(null);
  const zoneEditorRef = useRef(null);

  useEffect(() => {
    const nav = readInitialNav();
    if (!nav) return;
    if (nav.scale === "zone" && nav.id) {
      setCrumbs([
        { scale: "galaxy", id: null, label: "Galaxy" },
        { scale: "zone", id: nav.id, label: nav.label || nav.id },
      ]);
      return;
    }
    if (nav.scale === "ship" && nav.id) {
      setCrumbs([
        { scale: "galaxy", id: null, label: "Galaxy" },
        { scale: "ship", id: nav.id, label: nav.label || nav.id },
      ]);
      return;
    }
    if (nav.scale === "system" && nav.id) {
      setCrumbs([
        { scale: "galaxy", id: null, label: "Galaxy" },
        { scale: "system", id: nav.id, label: nav.label || nav.id },
      ]);
    }
  }, []);

  const current = crumbs[crumbs.length - 1];
  const activeScale = current.scale;

  // Unsaved-changes guard: the zone editor's property panel tracks a dirty flag;
  // every navigation path away from the zone must check it or edits vanish silently.
  const confirmLeave = useCallback(() => {
    if (zoneEditorRef.current?.hasUnsavedChanges?.()) {
      return window.confirm("You have unsaved room edits. Leave without saving?");
    }
    return true;
  }, []);

  const drill = useCallback(
    (newScale, id, label) => {
      if (!confirmLeave()) return;
      setNavigateRoomSlug(null);
      setCrumbs((p) => [...p, { scale: newScale, id, label: label || id }]);
    },
    [confirmLeave]
  );

  const goCrumb = useCallback(
    (index) => {
      if (index >= crumbs.length - 1) return; // already here — no-op, no prompt
      if (!confirmLeave()) return;
      setNavigateRoomSlug(null);
      setCrumbs((p) => p.slice(0, index + 1));
    },
    [crumbs.length, confirmLeave]
  );

  const jumpTab = useCallback((tabId) => {
    if (tabId === activeScale) return; // already on this view
    if (!confirmLeave()) return;
    setNavigateRoomSlug(null);
    if (tabId === "galaxy") {
      setCrumbs([{ scale: "galaxy", id: null, label: "Galaxy" }]);
      return;
    }
    if (tabId === "surface") {
      setCrumbs([
        { scale: "galaxy", id: null, label: "Galaxy" },
        { scale: "surface", id: null, label: "Surface" },
      ]);
      return;
    }
    if (tabId === "zone") {
      setCrumbs((p) => {
        const hit = [...p].reverse().find((c) => c.scale === "zone" && c.id != null);
        if (hit) {
          const idx = p.findIndex((c) => c.scale === hit.scale && c.id === hit.id);
          if (idx >= 0) return p.slice(0, idx + 1);
        }
        return [
          { scale: "galaxy", id: null, label: "Galaxy" },
          { scale: "surface", id: null, label: "Surface" },
        ];
      });
      return;
    }
    setCrumbs((p) => {
      const hit = [...p].reverse().find((c) => c.scale === tabId && c.id != null);
      if (hit) {
        const idx = p.findIndex((c) => c.scale === hit.scale && c.id === hit.id);
        if (idx >= 0) return p.slice(0, idx + 1);
      }
      return [{ scale: "galaxy", id: null, label: "Galaxy" }];
    });
  }, [activeScale, confirmLeave]);

  const tabBtnSeg = (active, isFirst, isLast) => ({
    padding: "7px 12px",
    fontSize: 12,
    fontWeight: 600,
    border: "none",
    borderRight: isLast ? "none" : `1px solid ${COLORS.border}`,
    borderRadius: 0,
    background: active ? COLORS.accentGlow : COLORS.bgCard,
    color: active ? COLORS.accent : COLORS.textMuted,
    cursor: "pointer",
    fontFamily: "'DM Sans', sans-serif",
    ...(isFirst ? { borderTopLeftRadius: 8, borderBottomLeftRadius: 8 } : {}),
    ...(isLast ? { borderTopRightRadius: 8, borderBottomRightRadius: 8 } : {}),
  });

  const systemId = activeScale === "system" ? current.id : null;
  const zoneId = activeScale === "zone" ? current.id : null;
  const shipId = activeScale === "ship" ? current.id : null;

  const canSaveLayout = activeScale === "zone" && Boolean(zoneId);

  const saveZoneLayout = () => {
    if (canSaveLayout && zoneEditorRef.current?.savePositions) {
      zoneEditorRef.current.savePositions();
      return;
    }
    window.alert("Open a zone (Surface or search), then use Save zone layout to store graph positions. Room fields use Save in the properties panel.");
  };

  const openForge = () => {
    window.dispatchEvent(new CustomEvent("fs-admin-nav", { detail: { page: "forge" } }));
  };

  const hint = contextHint(activeScale, current);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0, minHeight: "72vh", fontFamily: "'DM Sans', sans-serif" }}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
          padding: "12px 0 16px",
          marginBottom: 4,
          borderBottom: `1px solid ${COLORS.border}`,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 200 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 18, color: COLORS.accent }} aria-hidden>
              ◈
            </span>
            <span style={{ fontSize: 17, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>World Builder</span>
            <span
              style={{
                display: "inline-flex",
                padding: "2px 8px",
                borderRadius: 4,
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.06em",
                color: COLORS.accent,
                background: COLORS.accentGlow,
                border: `1px solid ${COLORS.borderActive}`,
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              BETA
            </span>
          </div>
          <div style={{ fontSize: 11, color: COLORS.textDim, maxWidth: 520, lineHeight: 1.5 }}>
            Content at multiple scales: galaxy → system → zones → rooms (and ship interiors). Search jumps anywhere; breadcrumbs move back.
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <button
            type="button"
            style={hdrBtnStyle(!canSaveLayout)}
            disabled={!canSaveLayout}
            onClick={saveZoneLayout}
            title={canSaveLayout ? "Writes .positions.json for this zone graph" : "Open a zone first"}
          >
            Save zone layout
          </button>
          <button
            type="button"
            style={{ ...hdrBtnStyle(false), background: `${COLORS.forge}22`, borderColor: COLORS.forge, color: COLORS.forge }}
            onClick={openForge}
          >
            AI Forge
          </button>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 8,
          padding: "10px 12px",
          marginBottom: 10,
          background: COLORS.bgCard,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 10,
        }}
      >
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: COLORS.textDim }}>Path</span>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, flex: 1, minWidth: 0 }}>
          {crumbs.map((c, i) => (
            <span key={`${c.scale}-${c.id ?? "root"}-${i}`} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              {i > 0 && <span style={{ color: COLORS.textDim, userSelect: "none" }} aria-hidden>/</span>}
              <button
                type="button"
                onClick={() => goCrumb(i)}
                aria-current={i === crumbs.length - 1 ? "page" : undefined}
                style={{
                  background: i === crumbs.length - 1 ? COLORS.accentGlow : "transparent",
                  border: `1px solid ${i === crumbs.length - 1 ? `${COLORS.accent}55` : "transparent"}`,
                  borderRadius: 6,
                  padding: "4px 10px",
                  cursor: "pointer",
                  fontSize: 12,
                  fontWeight: i === crumbs.length - 1 ? 600 : 400,
                  color: i === crumbs.length - 1 ? COLORS.accent : COLORS.textMuted,
                  fontFamily: "'DM Sans', sans-serif",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span style={{ fontSize: 13 }} aria-hidden>
                  {SCALE_ICONS[c.scale] || "·"}
                </span>
                {c.label}
              </button>
            </span>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 12, paddingLeft: 2, lineHeight: 1.45 }}>{hint}</div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "stretch",
          gap: 14,
          marginBottom: 16,
        }}
      >
        <div style={{ flex: "1 1 260px", minWidth: 220, maxWidth: 440 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: COLORS.textDim, marginBottom: 6 }}>Search</div>
          <BuilderSearchPanel
            onOpenZone={(id, label) => {
              if (!confirmLeave()) return;
              setNavigateRoomSlug(null);
              setCrumbs([
                { scale: "galaxy", id: null, label: "Galaxy" },
                { scale: "zone", id, label: label || id },
              ]);
            }}
            onOpenSystem={(id, label) => {
              if (!confirmLeave()) return;
              setNavigateRoomSlug(null);
              setCrumbs([
                { scale: "galaxy", id: null, label: "Galaxy" },
                { scale: "system", id, label: label || id },
              ]);
            }}
            onOpenShip={(id, label) => {
              if (!confirmLeave()) return;
              setNavigateRoomSlug(null);
              setCrumbs([
                { scale: "galaxy", id: null, label: "Galaxy" },
                { scale: "ship", id, label: label || id },
              ]);
            }}
            onOpenRoom={(zid, slug) => {
              if (!confirmLeave()) return;
              setNavigateRoomSlug(slug);
              setCrumbs([
                { scale: "galaxy", id: null, label: "Galaxy" },
                { scale: "zone", id: zid, label: zid },
              ]);
            }}
          />
        </div>
        <div style={{ width: 1, alignSelf: "stretch", background: COLORS.border, minHeight: 44 }} aria-hidden />
        <div style={{ flex: "1 1 280px", display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: COLORS.textDim }}>Jump to view</div>
          <div style={{ display: "inline-flex", flexWrap: "wrap", border: `1px solid ${COLORS.border}`, borderRadius: 8, overflow: "hidden", width: "fit-content", maxWidth: "100%" }}>
            {SCALE_TABS.map((t, i) => (
              <button
                key={t.id}
                type="button"
                style={tabBtnSeg(activeScale === t.id, i === 0, i === SCALE_TABS.length - 1)}
                onClick={() => jumpTab(t.id)}
                title={
                  t.id === "zone"
                    ? "Open last zone or Surface list"
                    : t.id === "system" || t.id === "ship"
                      ? "Open last context or Galaxy"
                      : undefined
                }
              >
                <span style={{ marginRight: 6, opacity: 0.85 }} aria-hidden>
                  {SCALE_ICONS[t.id]}
                </span>
                {t.label}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11, color: COLORS.textDim }}>Room YAML: Revert in the properties panel per room (no global undo yet).</div>
        </div>
      </div>

      <div style={{ borderTop: `1px solid ${COLORS.border}`, paddingTop: 14 }}>
        {activeScale === "galaxy" && <GalaxyView onSelectSystem={(id, name) => drill("system", id, name)} />}

        {activeScale === "system" && (
          <SystemView
            systemId={systemId}
            onSelectZone={(zid) => drill("zone", zid, zid)}
            onSelectShip={(sid, name) => drill("ship", sid, name || sid)}
          />
        )}

        {activeScale === "surface" && <SurfaceView onSelectZone={(zid, zname) => drill("zone", zid, zname || zid)} />}

        {activeScale === "zone" && (
          <ZoneEditor
            ref={zoneEditorRef}
            key={zoneId || "none"}
            zoneId={zoneId}
            navigateRoomSlug={navigateRoomSlug}
            onNavigateRoomDone={() => setNavigateRoomSlug(null)}
          />
        )}

        {activeScale === "ship" && <ShipEditor key={shipId} shipId={shipId} />}
      </div>
    </div>
  );
}
