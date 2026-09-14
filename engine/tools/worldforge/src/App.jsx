import { useCallback, useEffect, useState } from "react";
import { ContentProvider, useContent } from "./hooks/useContentStore.js";
import { useLocalSettings, readSnapEnabled } from "./hooks/useLocalSettings.js";
import * as fs from "./utils/fsBridge.js";
import { createWorldScaffold } from "./utils/worldScaffold.js";
import { useTheme } from "./ThemeContext.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ExportDialog from "./components/ExportDialog.jsx";
import ZoneEditor from "./editors/ZoneEditor.jsx";
import GalaxyEditor from "./editors/GalaxyEditor.jsx";
import ShipEditor from "./editors/ShipEditor.jsx";
import EntityEditor from "./editors/EntityEditor.jsx";
import ItemEditor from "./editors/ItemEditor.jsx";
import GlyphEditor from "./editors/GlyphEditor.jsx";

const LS_ROOT = "worldforge_content_root";

function Welcome({ onOpen }) {
  const { colors: COLORS } = useTheme();
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: COLORS.bg,
        color: COLORS.text,
        padding: 32,
      }}
    >
      <h1 style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 28, marginBottom: 8 }}>SAGE WorldForge</h1>
      <p style={{ color: COLORS.textMuted, marginBottom: 24, textAlign: "center", maxWidth: 420 }}>
        Dedicated world builder for SAGE worlds. Opens your repository&apos;s <code style={{ color: COLORS.accent }}>content/world</code> directly.
      </p>
      <button
        type="button"
        onClick={onOpen}
        style={{
          padding: "12px 24px",
          borderRadius: 8,
          border: `1px solid ${COLORS.accent}`,
          background: `${COLORS.accent}22`,
          color: COLORS.accent,
          fontSize: 14,
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        Open world folder
      </button>
      <p style={{ marginTop: 20, fontSize: 12, color: COLORS.textDim, textAlign: "center" }}>
        Choose your project folder (the one that contains <code>content</code>).
      </p>
    </div>
  );
}

function SettingsPanel({ onClose, settings }) {
  const { colors: COLORS, colorScheme, setColorScheme } = useTheme();
  const sl = { display: "block", fontSize: 11, color: COLORS.textMuted, marginTop: 12, marginBottom: 4 };
  const si = {
    width: "100%",
    boxSizing: "border-box",
    padding: 8,
    borderRadius: 6,
    border: `1px solid ${COLORS.border}`,
    background: COLORS.bgInput,
    color: COLORS.text,
    fontSize: 12,
  };
  const segBtn = (active) => ({
    flex: 1,
    padding: "8px 12px",
    borderRadius: 6,
    border: `1px solid ${active ? COLORS.accent : COLORS.border}`,
    background: active ? `${COLORS.accent}22` : COLORS.bgCard,
    color: COLORS.text,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: active ? 600 : 400,
  });
  return (
    <div style={{ position: "absolute", inset: 0, background: `${COLORS.bg}dd`, zIndex: 90, display: "flex", alignItems: "center", justifyContent: "center" }} onMouseDown={onClose}>
      <div style={{ width: 420, maxWidth: "94vw", background: COLORS.bgPanel, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 20 }} onMouseDown={(e) => e.stopPropagation()}>
        <h3 style={{ marginTop: 0, color: COLORS.text }}>Settings</h3>
        <label style={{ ...sl, marginTop: 0 }}>Appearance</label>
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <button type="button" style={segBtn(colorScheme === "dark")} onClick={() => setColorScheme("dark")}>
            Dark
          </button>
          <button type="button" style={segBtn(colorScheme === "light")} onClick={() => setColorScheme("light")}>
            Light
          </button>
        </div>
        <label style={sl}>Nexus API URL</label>
        <input style={si} value={settings.nexusUrl} onChange={(e) => settings.setNexusUrl(e.target.value)} />
        <label style={sl}>Nexus bearer token (optional)</label>
        <input style={si} value={settings.nexusToken} onChange={(e) => settings.setNexusToken(e.target.value)} />
        <p style={{ fontSize: 11, color: COLORS.textDim, marginTop: 10, lineHeight: 1.45 }}>
          <strong style={{ color: COLORS.textMuted }}>LM Studio / LLM:</strong> Forge text (room descriptions, scene prompt suggestions) uses the game server&apos;s OpenAI-compatible endpoint — configure it in the{" "}
          <strong>Admin UI → Server &amp; Performance → LM Studio / LLM</strong> (same as in-game narration). The token above must allow the <strong>forge</strong> tool if admin auth is required.
        </p>
        <label style={sl}>LLM model hint</label>
        <input style={si} value={settings.llmModel} onChange={(e) => settings.setLlmModel(e.target.value)} />
        <label style={{ ...sl, display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={settings.autoSaveNavigate} onChange={(e) => settings.setAutoSaveNavigate(e.target.checked)} />
          Auto-save on navigate
        </label>
        <label style={{ ...sl, display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={settings.showYamlIds} onChange={(e) => settings.setShowYamlIds(e.target.checked)} />
          Show room IDs on nodes
        </label>
        <label style={{ ...sl, display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={settings.connectionDebugLog} onChange={(e) => settings.setConnectionDebugLog(e.target.checked)} />
          Log map connections (debug — console + zone panel)
        </label>
        <label style={{ ...sl, display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={settings.showDevTools} onChange={(e) => settings.setShowDevTools(e.target.checked)} />
          Show developer tools (destructive zone-clear button)
        </label>
        <label style={sl}>Default room type</label>
        <input style={si} value={settings.defaultRoomType} onChange={(e) => settings.setDefaultRoomType(e.target.value)} />
        <label style={sl}>Snap grid W × H</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input type="number" style={si} value={settings.snapGridW} onChange={(e) => settings.setSnapGridW(Number(e.target.value))} />
          <input type="number" style={si} value={settings.snapGridH} onChange={(e) => settings.setSnapGridH(Number(e.target.value))} />
        </div>
        <button type="button" style={{ marginTop: 16, padding: "8px 16px", borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bgCard, color: COLORS.text, cursor: "pointer" }} onClick={onClose}>
          Done
        </button>
      </div>
    </div>
  );
}

function ScaffoldPrompt({ pending, onCreate, onPickOther, onCancel, busy }) {
  const { colors: COLORS } = useTheme();
  const missing = pending.reason === "missing";
  const title = missing ? "No content/world folder" : "World folder is empty";
  const body = missing
    ? "This project does not have a content/world directory yet. Create a starter layout (galaxy index, starter zone with one room, and empty entity/item folders)?"
    : "content/world exists but has no zones, galaxy.yaml, or other YAML yet. Create the same starter layout? Existing files are left unchanged.";

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: `${COLORS.bg}cc`,
        zIndex: 50,
        padding: 24,
      }}
    >
      <div
        style={{
          maxWidth: 440,
          background: COLORS.bgPanel,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 12,
          padding: 24,
          color: COLORS.text,
          boxShadow: `0 16px 48px ${COLORS.bg}`,
        }}
      >
        <h2 style={{ marginTop: 0, fontSize: 18, fontFamily: "'Space Grotesk', sans-serif" }}>{title}</h2>
        <p style={{ fontSize: 13, color: COLORS.textMuted, lineHeight: 1.5 }}>{body}</p>
        <p style={{ fontSize: 11, color: COLORS.textDim, wordBreak: "break-all" }}>{pending.contentRoot}</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 20 }}>
          <button
            type="button"
            disabled={busy}
            onClick={onCreate}
            style={{
              padding: "10px 16px",
              borderRadius: 8,
              border: `1px solid ${COLORS.accent}`,
              background: `${COLORS.accent}33`,
              color: COLORS.accent,
              fontWeight: 600,
              cursor: busy ? "wait" : "pointer",
              fontSize: 13,
            }}
          >
            Create starter world
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onPickOther}
            style={{
              padding: "10px 16px",
              borderRadius: 8,
              border: `1px solid ${COLORS.border}`,
              background: COLORS.bgCard,
              color: COLORS.text,
              cursor: busy ? "wait" : "pointer",
              fontSize: 13,
            }}
          >
            Choose another folder
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onCancel}
            style={{
              padding: "10px 16px",
              borderRadius: 8,
              border: "none",
              background: "transparent",
              color: COLORS.textMuted,
              cursor: busy ? "wait" : "pointer",
              fontSize: 13,
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function Shell() {
  const { colors: COLORS } = useTheme();
  const {
    contentRoot,
    worldRoot,
    loading,
    loadError,
    pendingScaffold,
    zoneIds,
    systemIds,
    shipIds,
    entityIds,
    itemIds,
    glyphIds,
    setContentRoot,
    loadAll,
    softRefresh,
    deleteZone,
    dismissPendingScaffold,
  } = useContent();
  const settings = useLocalSettings();
  const [activeEditor, setActiveEditor] = useState("zone");
  const [selectedZone, setSelectedZone] = useState(null);
  const [selectedSystem, setSelectedSystem] = useState(null);
  const [selectedShip, setSelectedShip] = useState(null);
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [selectedItem, setSelectedItem] = useState(null);
  const [selectedGlyph, setSelectedGlyph] = useState(null);
  const [search, setSearch] = useState("");
  const [nexusLive, setNexusLive] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [snapEnabled, setSnapEnabled] = useState(readSnapEnabled);
  const [scaffoldBusy, setScaffoldBusy] = useState(false);
  const [watching, setWatching] = useState(false);

  // Live-watch: poll disk every 2 s and silently merge any changes
  useEffect(() => {
    if (!watching || !contentRoot) return;
    const id = setInterval(() => softRefresh(contentRoot), 2000);
    return () => clearInterval(id);
  }, [watching, contentRoot, softRefresh]);

  useEffect(() => {
    if (contentRoot && worldRoot && !pendingScaffold) {
      localStorage.setItem(LS_ROOT, contentRoot);
    }
  }, [contentRoot, worldRoot, pendingScaffold]);

  useEffect(() => {
    if (contentRoot && zoneIds.length && !selectedZone) setSelectedZone(zoneIds[0]);
  }, [contentRoot, zoneIds, selectedZone]);
  useEffect(() => {
    if (contentRoot && systemIds.length && !selectedSystem) setSelectedSystem(systemIds[0]);
  }, [contentRoot, systemIds, selectedSystem]);
  useEffect(() => {
    if (contentRoot && shipIds.length && !selectedShip) setSelectedShip(shipIds[0]);
  }, [contentRoot, shipIds, selectedShip]);

  useEffect(() => {
    const url = settings.nexusUrl?.replace(/\/$/, "");
    if (!url) {
      setNexusLive(false);
      return;
    }
    let cancelled = false;
    const tick = () => {
      fetch(`${url}/play/health`)
        .then((r) => {
          if (!cancelled) setNexusLive(r.ok);
        })
        .catch(() => {
          if (!cancelled) setNexusLive(false);
        });
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [settings.nexusUrl]);

  const openFolder = useCallback(async () => {
    const picked = await fs.pickFolder();
    if (!picked) return;
    if (!(await fs.pathExists(picked))) return;
    await setContentRoot(picked);
  }, [setContentRoot]);

  useEffect(() => {
    async function boot() {
      // 1. Honour saved path from last session
      const saved = localStorage.getItem(LS_ROOT);
      if (saved && (await fs.pathExists(saved))) {
        await setContentRoot(saved);
        return;
      }

      // 2. Honour WORLDFORGE_ROOT env var (same one the MCP server uses)
      const envRoot = await fs.getEnvVar("WORLDFORGE_ROOT");
      if (envRoot && (await fs.pathExists(envRoot))) {
        // env var points to content/world directly — use its parent as contentRoot
        // setContentRoot calls loadAll which calls resolveWorldRoot, so any level works
        await setContentRoot(envRoot);
        return;
      }

      // 3. Walk up from the exe to auto-detect the project root
      //    Dev layout:  engine/tools/worldforge/src-tauri/target/debug/worldforge.exe
      //                 → repository root is 7 levels up
      //    Prod layout: resources/worldforge.exe                → go up 1 level
      try {
        const exePath = await fs.getExePath();
        const sep = exePath.includes("\\") ? "\\" : "/";
        const parts = exePath.split(sep).filter(Boolean);
        // Try going up 1–8 levels from the exe
        for (let up = 1; up <= 8; up++) {
          if (parts.length - up < 1) break;
          const candidate = (exePath.startsWith("\\\\") ? "\\\\" : (sep === "\\" ? "" : "/"))
            + parts.slice(0, parts.length - up).join(sep);
          // Check for zones/ or content/world/zones/ inside this candidate
          const direct = candidate + sep + "zones";
          const nested = candidate + sep + "content" + sep + "world" + sep + "zones";
          const worldNested = candidate + sep + "world" + sep + "zones";
          if (
            (await fs.pathExists(direct)) ||
            (await fs.pathExists(nested)) ||
            (await fs.pathExists(worldNested))
          ) {
            await setContentRoot(candidate);
            return;
          }
        }
      } catch {
        // exe path unavailable — fall through to folder picker
      }

      // 4. Nothing found — show the folder picker (original behaviour)
    }
    boot();
  }, [setContentRoot]);

  if (!contentRoot && !loading && pendingScaffold) {
    return (
      <div style={{ display: "flex", flexDirection: "column", height: "100vh", position: "relative" }}>
        <Welcome onOpen={openFolder} />
        <ScaffoldPrompt
          pending={pendingScaffold}
          busy={scaffoldBusy}
          onCreate={async () => {
            setScaffoldBusy(true);
            try {
              await createWorldScaffold(pendingScaffold.contentRoot);
              await loadAll(pendingScaffold.contentRoot);
            } finally {
              setScaffoldBusy(false);
            }
          }}
          onPickOther={async () => {
            dismissPendingScaffold();
            localStorage.removeItem(LS_ROOT);
            await openFolder();
          }}
          onCancel={() => {
            dismissPendingScaffold();
            localStorage.removeItem(LS_ROOT);
          }}
        />
      </div>
    );
  }

  if (!contentRoot && !loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
        {loadError ? <div style={{ padding: 12, background: `${COLORS.danger}33`, color: COLORS.danger, fontSize: 12 }}>{loadError}</div> : null}
        <Welcome onOpen={openFolder} />
      </div>
    );
  }

  if (loading || !worldRoot) {
    return (
      <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: COLORS.bg, color: COLORS.textMuted }}>
        Loading content…
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100vh", background: COLORS.bg, color: COLORS.text, overflow: "hidden" }}>
      <Sidebar
        contentRoot={contentRoot}
        worldRoot={worldRoot}
        onChangeRoot={openFolder}
        activeEditor={activeEditor}
        onEditor={setActiveEditor}
        zoneIds={zoneIds}
        selectedZoneId={selectedZone}
        onSelectZone={setSelectedZone}
        systemIds={systemIds}
        selectedSystemId={selectedSystem}
        onSelectSystem={setSelectedSystem}
        shipIds={shipIds}
        selectedShipId={selectedShip}
        onSelectShip={setSelectedShip}
        entityIds={entityIds}
        selectedEntityId={selectedEntity}
        onSelectEntity={setSelectedEntity}
        itemIds={itemIds}
        selectedItemId={selectedItem}
        onSelectItem={setSelectedItem}
        glyphIds={glyphIds}
        selectedGlyphId={selectedGlyph}
        onSelectGlyph={setSelectedGlyph}
        search={search}
        onSearch={setSearch}
        nexusLive={nexusLive}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenExport={() => setExportOpen(true)}
        onRefresh={() => loadAll(contentRoot)}
        watching={watching}
        onToggleWatch={() => setWatching((w) => !w)}
        onDeleteZone={async (id) => {
          await deleteZone(id, worldRoot);
          if (selectedZone === id) setSelectedZone(zoneIds.filter((z) => z !== id)[0] ?? null);
        }}
      />
      <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
        {activeEditor === "zone" ? (
          <ZoneEditor
            zoneId={selectedZone}
            onZoneId={setSelectedZone}
            worldRoot={worldRoot}
            snapEnabled={snapEnabled}
            setSnapEnabled={setSnapEnabled}
            snapGrid={[settings.snapGridW, settings.snapGridH]}
            showYamlIds={settings.showYamlIds}
            connectionDebugLog={settings.connectionDebugLog}
            setConnectionDebugLog={settings.setConnectionDebugLog}
            nexusUrl={settings.nexusUrl}
            nexusToken={settings.nexusToken}
            defaultRoomType={settings.defaultRoomType}
            autoSaveNavigate={settings.autoSaveNavigate}
            showDevTools={settings.showDevTools}
          />
        ) : null}
        {activeEditor === "galaxy" ? <GalaxyEditor worldRoot={worldRoot} /> : null}
        {activeEditor === "ship" ? <ShipEditor shipId={selectedShip} worldRoot={worldRoot} onShipId={setSelectedShip} /> : null}
        {activeEditor === "entities" ? <EntityEditor worldRoot={worldRoot} selectedId={selectedEntity} onSelect={setSelectedEntity} /> : null}
        {activeEditor === "items" ? <ItemEditor worldRoot={worldRoot} selectedId={selectedItem} onSelect={setSelectedItem} /> : null}
        {activeEditor === "glyphs" ? <GlyphEditor worldRoot={worldRoot} selectedId={selectedGlyph} onSelect={setSelectedGlyph} /> : null}
      </div>
      {exportOpen ? (
        <ExportDialog
          worldRoot={worldRoot}
          contentRoot={contentRoot}
          zoneIds={zoneIds}
          systemIds={systemIds}
          entityIds={entityIds}
          itemIds={itemIds}
          glyphIds={glyphIds}
          onClose={() => setExportOpen(false)}
        />
      ) : null}
      {settingsOpen ? <SettingsPanel onClose={() => setSettingsOpen(false)} settings={settings} /> : null}
    </div>
  );
}

export default function App() {
  return (
    <ContentProvider>
      <Shell />
    </ContentProvider>
  );
}
