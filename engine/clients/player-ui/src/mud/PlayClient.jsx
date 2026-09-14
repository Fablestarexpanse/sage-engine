import { useState, useCallback, useMemo, useEffect } from "react";
import { usePlayTheme } from "../PlayThemeContext.jsx";
import { ThemeToggleButton } from "../ThemeToggleButton.jsx";
import { GameCmdContext } from "./00-ctx.jsx";
import { ContextMenu, DraggablePanel } from "./01-primitives.jsx";
import { NarrativePanel, CommandInput, lastRoomTitleHint } from "./03-narrative.jsx";
import { AfflictionTracker } from "./04-panels-a.jsx";
import { MiniMap } from "./05-minimap.jsx";
import { CharacterPanel, InventoryPanel, SocialPanel, ScenePanel } from "./06-panels-b.jsx";
import { DeclaredPanel } from "./08-declared-panels.jsx";
import { PORTRAIT_ASPECT_RATIO_CSS } from "../portraitProfile.js";
import { GmBadge } from "../GmBadge.jsx";

/** Layout presets were authored for this logical size; we scale to the real viewport. */
const DESIGN_W = 1180;
const DESIGN_H = 560;
const HEADER_PX = 36;

function useWorkspaceScale() {
  const [dims, setDims] = useState(() => ({
    iw: typeof window !== "undefined" ? window.innerWidth : DESIGN_W,
    ih: typeof window !== "undefined" ? Math.max(320, window.innerHeight - HEADER_PX) : DESIGN_H,
  }));

  useEffect(() => {
    const onResize = () => {
      setDims({
        iw: window.innerWidth,
        ih: Math.max(320, window.innerHeight - HEADER_PX),
      });
    };
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const sx = dims.iw / DESIGN_W;
  const sy = dims.ih / DESIGN_H;
  const layoutKey = `${Math.floor(dims.iw / 40)}x${Math.floor(dims.ih / 40)}`;
  return { sx, sy, layoutKey, iw: dims.iw, ih: dims.ih };
}

/** Where a server-declared panel opens the first time it is shown (cascaded by index). */
function declaredPanelBox(index) {
  return { x: 300 + (index % 5) * 30, y: 60 + (index % 5) * 30, w: 280, h: 260 };
}

const PRESETS = {
  standard: { name: "Standard", desc: "Balanced layout",
    panels: { narrative:{x:260,y:0,w:580,h:560}, scene:{x:840,y:0,w:340,h:260}, character:{x:0,y:0,w:260,h:360}, map:{x:840,y:260,w:340,h:210}, inventory:{x:0,y:360,w:260,h:200}, social:{x:840,y:470,w:340,h:90}, afflictions:{x:100,y:100,w:240,h:280} },
    visible: ["narrative","scene","character","map","inventory","social"] },
  combat: { name: "Combat", desc: "Effects up front",
    panels: { narrative:{x:280,y:0,w:560,h:560}, scene:{x:0,y:360,w:280,h:200}, character:{x:0,y:0,w:280,h:360}, map:{x:840,y:360,w:340,h:200}, inventory:{x:840,y:200,w:340,h:160}, social:{x:840,y:480,w:340,h:80}, afflictions:{x:840,y:0,w:340,h:200} },
    visible: ["narrative","character","afflictions","inventory","map"] },
  classic: { name: "Classic MUD", desc: "Text-forward",
    panels: { narrative:{x:0,y:0,w:860,h:500}, scene:{x:100,y:100,w:380,h:300}, character:{x:860,y:0,w:320,h:260}, map:{x:860,y:260,w:320,h:200}, inventory:{x:860,y:460,w:320,h:100}, social:{x:0,y:500,w:860,h:60}, afflictions:{x:100,y:100,w:240,h:280} },
    visible: ["narrative","character","map","inventory","social"] },
};

export default function PlayClient({
  session,
  onSignOut,
  narrativeLines,
  onSendCommand,
  wsConnected,
  /** Why the server ended the session (quit / replaced / refused); null while reconnecting normally. */
  wsStopped = null,
  onReconnect,
  /** Absolute URL for current room scene art (from room YAML area_image_url + Nexus base). */
  sceneImageUrl,
  /** ComfyUI scene render in progress (spinner on Scene panel). */
  sceneGenerating = false,
  sceneRoomLabel,
  /** Safe filename stem for Scene panel download (no extension). */
  sceneDownloadBaseName = "scene",
  /** The world's display name (GET /play/world). */
  worldName = "",
  /** Optional: { credits, label } for ComfyUI / AI art credit display. */
  aiEconomy,
  /** The world's primary currency name from the server; empty when the world has no money. */
  gameCurrencyDisplayName = "",
  /** Optional: narrative toolbar → ComfyUI scene generation (credentials + callbacks). */
  sceneGen,
}) {
  const { T } = usePlayTheme();
  const [layout, setLayout] = useState("standard");
  const [collapsed, setCollapsed] = useState({});
  const [focusStack, setFocusStack] = useState([]);
  const [showLayoutPicker, setShowLayoutPicker] = useState(false);
  const [ctxMenu, setCtxMenu] = useState(null);
  const [notifications] = useState({ tells: 1, guild: 0 });
  const [narrativeBackdropSource, setNarrativeBackdropSource] = useState("portrait");
  const [openSceneGallerySignal, setOpenSceneGallerySignal] = useState(0);
  const { sx, sy, layoutKey } = useWorkspaceScale();

  const preset = PRESETS[layout];
  const narrativeLocationHint = useMemo(() => lastRoomTitleHint(narrativeLines || []), [narrativeLines]);
  // Server-pushed location wins; the narrative-scrape hint is the legacy fallback.
  const characterLocation =
    session?.liveLocation?.name || session?.liveLocation?.id || narrativeLocationHint;
  const toggleCollapse = (id) => setCollapsed(p => ({ ...p, [id]: !p[id] }));
  const bringToFront = (id) => setFocusStack(p => [...p.filter(x => x !== id), id]);
  const getZ = (id) => { const i = focusStack.indexOf(id); return i === -1 ? 1 : i + 2; };
  const isVis = (id) => preset.visible.includes(id);
  const togglePanel = (id) => {
    const p = { ...PRESETS[layout] };
    const showing = !isVis(id);
    p.visible = showing ? [...p.visible, id] : p.visible.filter(v => v !== id);
    PRESETS[layout] = p;
    if (showing) bringToFront(id);
    setLayout(l => l);
    setCollapsed(c => ({ ...c }));
  };

  const openCtx = useCallback((menu) => setCtxMenu(menu), []);

  const sendCommand = useCallback((cmd) => {
    onSendCommand?.(cmd);
  }, [onSendCommand]);

  const onArtCreditsInfo = useCallback(() => {
    const art = aiEconomy?.label || "credits";
    const game = gameCurrencyDisplayName || "in-world money";
    window.alert(
      `${art} is your account balance for AI portraits and scene art (ComfyUI). It is shared by every character and is not the same as in-world ${game}.\n\n` +
        "Your host can grant more, or future progression may award it. There is no in-client purchase yet."
    );
  }, [aiEconomy?.label, gameCurrencyDisplayName]);

  const onWalletInfo = useCallback(() => {
    const game = gameCurrencyDisplayName || "in-world money";
    const art = aiEconomy?.label || "credits";
    window.alert(
      `${game} is your in-world wallet for this character only — loot, quests, trades. It is separate from ${art} (AI portrait / scene balance on your account).\n\n` +
        "Each character has their own balance; pick another character to see a different amount here."
    );
  }, [gameCurrencyDisplayName, aiEconomy?.label]);

  const narrativeBackdropUrl =
    narrativeBackdropSource === "scene" && sceneImageUrl
      ? sceneImageUrl
      : (session?.portraitImageUrl || null);

  useEffect(() => {
    if (narrativeBackdropSource === "scene" && !sceneImageUrl) {
      setNarrativeBackdropSource("portrait");
    }
  }, [narrativeBackdropSource, sceneImageUrl]);

  const panels = useMemo(() => [
    { id: "narrative", title: "Narrative", icon: "📜", accent: T.text.narrative, minW: 340, minH: 260, content: (
      <div style={{display:"flex",flexDirection:"column",height:"100%"}}>
        <div style={{flex:1,overflow:"hidden"}}>
          <NarrativePanel
            lines={narrativeLines}
            onContextMenu={openCtx}
            sceneGen={sceneGen}
            portraitBackdropUrl={narrativeBackdropUrl}
            openSceneGallerySignal={openSceneGallerySignal}
          />
        </div>
        <CommandInput onSubmitCommand={sendCommand} />
      </div>
    ) },
    { id: "scene", title: "Scene", icon: "🎨", accent: T.hue.violet, minW: 240, minH: 180, content: (
      <ScenePanel
        imageUrl={sceneImageUrl}
        roomLabel={sceneRoomLabel}
        downloadBaseName={sceneDownloadBaseName}
        generating={sceneGenerating}
        usingSceneAsNarrativeBackdrop={narrativeBackdropSource === "scene"}
        onUseSceneAsNarrativeBackdrop={() => setNarrativeBackdropSource("scene")}
        onResetNarrativeBackdropToCharacter={() => setNarrativeBackdropSource("portrait")}
        onOpenSceneGallery={
          sceneGen
            ? () => setOpenSceneGallerySignal((n) => n + 1)
            : undefined
        }
      />
    ) },
    { id: "character", title: "Character", icon: "◉", accent: T.hue.violet, minW: 200, minH: 240, content: (
      <CharacterPanel
        displayName={session?.characterName}
        portraitImageUrl={session?.portraitImageUrl}
        showHeroPortrait={!session?.portraitImageUrl}
        accountName={session?.username}
        locationLabel={characterLocation}
        characterStats={session?.characterStats ?? null}
        levelsTotal={session?.levelsTotal ?? null}
        walletBalance={session?.walletBalance}
        gameCurrencyLabel={gameCurrencyDisplayName}
        pvpEnabled={session?.pvpEnabled}
        effects={session?.liveEffects ?? null}
      />
    ) },
    { id: "map", title: "Map", icon: "🗺", accent: T.hue.cyan, minW: 220, minH: 160, content: <MiniMap map={session?.liveMap ?? null}/> },
    { id: "inventory", title: "Inventory", icon: "◻", accent: T.hue.amber, minW: 200, minH: 180, content: <InventoryPanel onContextMenu={openCtx} items={session?.liveInventory ?? null}/> },
    { id: "social", title: "Comms", icon: "💬", accent: T.hue.cyan, minW: 220, minH: 140, content: <SocialPanel messages={session?.chatMessages ?? null}/> },
    { id: "afflictions", title: "Effects", icon: "⊘", accent: T.hue.crimson, minW: 200, minH: 180, content: <AfflictionTracker effects={session?.liveEffects ?? null}/> },
    ...(session?.declaredPanels || []).map((spec) => ({
      id: spec.id,
      title: spec.title,
      icon: spec.icon || "▣",
      accent: T.text.accent,
      minW: 200,
      minH: 140,
      content: <DeclaredPanel spec={spec} data={session?.liveSections?.[spec.section]} />,
    })),
  ], [session?.declaredPanels, session?.liveSections, narrativeLines, openCtx, sendCommand, notifications, session?.characterName, session?.username, session?.portraitImageUrl, session?.walletBalance, session?.pvpEnabled, session?.characterStats, session?.levelsTotal, session?.liveEffects, session?.liveInventory, session?.liveMap, session?.chatMessages, sceneImageUrl, sceneGenerating, sceneRoomLabel, sceneDownloadBaseName, sceneGen, characterLocation, gameCurrencyDisplayName, narrativeBackdropUrl, narrativeBackdropSource, openSceneGallerySignal]);

  return (
    <GameCmdContext.Provider value={{ sendCommand }}>
    {!wsConnected && (
      <div
        role="alert"
        style={{
          position: "fixed",
          // Below the 36px top bar (also fixed, z 9999), which otherwise covers
          // the banner and swallows clicks on its Reconnect button.
          top: 36,
          left: 0,
          right: 0,
          zIndex: 10001,
          padding: "6px 14px",
          textAlign: "center",
          background: T.hue.crimson,
          color: "#fff",
          fontFamily: T.font.body,
          fontSize: 12,
          letterSpacing: "0.06em",
        }}
      >
        {wsStopped ? (
          <>
            {wsStopped}{" "}
            <button
              type="button"
              onClick={onReconnect}
              style={{
                marginLeft: 8,
                padding: "2px 10px",
                borderRadius: 4,
                border: "1px solid #fff",
                background: "transparent",
                color: "#fff",
                cursor: "pointer",
                fontFamily: T.font.body,
                fontSize: 12,
              }}
            >
              Reconnect
            </button>
          </>
        ) : (
          "Connection lost — reconnecting…"
        )}
      </div>
    )}
    <div style={{
      flex: 1,
      width: "100%",
      minWidth: 0,
      minHeight: 0,
      height: "100%",
      background: T.bg.void,
      overflow: "hidden",
      fontFamily: T.font.body,
      position: "relative",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@300;400;500;600;700&family=Exo+2:wght@500;600;700&family=JetBrains+Mono:wght@300;400;500;600&family=Oxanium:wght@400;500;600;700&display=swap" rel="stylesheet"/>
      <style>{`
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes pulse{0%,100%{opacity:.2;transform:scale(1)}50%{opacity:.5;transform:scale(1.1)}}
        ::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}
        ::-webkit-scrollbar-thumb{background:${T.text.muted}25;border-radius:3px}
        ::-webkit-scrollbar-thumb:hover{background:${T.text.muted}40}
        *{box-sizing:border-box;margin:0;padding:0}
      `}</style>

      {ctxMenu && <ContextMenu x={ctxMenu.x} y={ctxMenu.y} items={ctxMenu.items} onClose={() => setCtxMenu(null)} />}

      <header role="banner" style={{
        position: "fixed", top: 0, left: 0, right: 0, height: 36, zIndex: 9999,
        background: `linear-gradient(180deg,${T.bg.deep},${T.bg.deep}f0)`,
        borderBottom: `1px solid ${T.border.dim}`,
        display: "flex", alignItems: "center", padding: "0 10px", gap: 8,
      }}>
        <span style={{ fontSize: 16, color: T.hue.violet }}>◈</span>
        <span style={{ fontFamily: T.font.display, fontSize: 12, fontWeight: 700, color: T.text.primary, letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{worldName}</span>

        {session && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 8, paddingLeft: 12, borderLeft: `1px solid ${T.border.dim}` }}>
            {session.portraitImageUrl ? (
              <div
                className="sage-portrait-stage"
                style={{
                  width: 26,
                  aspectRatio: PORTRAIT_ASPECT_RATIO_CSS,
                  borderRadius: T.radius.md,
                  border: `1px solid ${T.border.accent}`,
                  flexShrink: 0,
                  overflow: "hidden",
                }}
              >
                <div className="sage-portrait-aurora sage-portrait-aurora--thumb" aria-hidden />
                <img
                  src={session.portraitImageUrl}
                  alt=""
                  className="sage-portrait-cutout sage-portrait-cutout--thumb"
                  style={{
                    position: "relative",
                    width: "100%",
                    height: "100%",
                    objectFit: "contain",
                    objectPosition: "center",
                    display: "block",
                  }}
                />
              </div>
            ) : null}
            <span style={{ fontFamily: T.font.body, fontSize: 11, color: T.text.secondary }}>{session.username}</span>
            {session.isGm ? <GmBadge style={{ marginLeft: 4 }} /> : null}
            <span style={{ fontSize: 8, color: T.text.muted }}>·</span>
            <span style={{ fontFamily: T.font.display, fontSize: 11, color: T.text.accent }}>{session.characterName}</span>
            <div style={{ marginLeft: 8, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              {aiEconomy?.credits != null ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 10px 4px 12px",
                    borderRadius: T.radius.md,
                    border: `1px solid ${T.currency.art.border}`,
                    background: T.currency.art.bg,
                    maxWidth: 200,
                  }}
                  title="Shared by all your characters. Spent on AI portrait and scene generation (not in-world money)."
                >
                  <div style={{ minWidth: 0, lineHeight: 1.2 }}>
                    <div
                      style={{
                        fontSize: 8,
                        fontWeight: 600,
                        color: T.currency.art.label,
                        textTransform: "uppercase",
                        letterSpacing: "0.07em",
                        fontFamily: T.font.body,
                      }}
                    >
                      {aiEconomy.label} · account
                    </div>
                    <div
                      style={{
                        fontSize: 13,
                        fontFamily: T.font.mono,
                        fontWeight: 600,
                        color: aiEconomy.credits < (aiEconomy.warnBelow ?? 12) ? T.currency.art.warn : T.currency.art.fg,
                        marginTop: 1,
                      }}
                    >
                      {aiEconomy.label} {aiEconomy.credits}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={onArtCreditsInfo}
                    title="What this is and how to get more"
                    style={{
                      flexShrink: 0,
                      width: 22,
                      height: 22,
                      padding: 0,
                      borderRadius: T.radius.sm,
                      border: `1px solid ${T.currency.art.border}`,
                      background: T.bg.deep,
                      color: T.currency.art.fg,
                      fontSize: 12,
                      fontWeight: 700,
                      cursor: "pointer",
                      fontFamily: T.font.body,
                      lineHeight: 1,
                    }}
                  >
                    ?
                  </button>
                </div>
              ) : null}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "4px 10px 4px 12px",
                  borderRadius: T.radius.md,
                  border: `1px solid ${T.currency.world.border}`,
                  background: T.currency.world.bg,
                  maxWidth: 200,
                }}
                title={`In-world wallet for ${session.characterName} (this character only).`}
              >
                <div style={{ minWidth: 0, lineHeight: 1.2 }}>
                  <div
                    style={{
                      fontSize: 8,
                      fontWeight: 600,
                      color: T.currency.world.label,
                      textTransform: "uppercase",
                      letterSpacing: "0.07em",
                      fontFamily: T.font.body,
                    }}
                  >
                    {gameCurrencyDisplayName} · character
                  </div>
                  <div
                    style={{
                      fontSize: 13,
                      fontFamily: T.font.mono,
                      fontWeight: 600,
                      color: T.currency.world.fg,
                      marginTop: 1,
                    }}
                  >
                    {String(gameCurrencyDisplayName).toLowerCase()}{" "}
                    {typeof session.walletBalance === "number" ? session.walletBalance : 0}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onWalletInfo}
                  title="What this currency is (in-world money vs AI art balance)"
                  style={{
                    flexShrink: 0,
                    width: 22,
                    height: 22,
                    padding: 0,
                    borderRadius: T.radius.sm,
                    border: `1px solid ${T.currency.world.border}`,
                    background: T.bg.deep,
                    color: T.currency.world.fg,
                    fontSize: 12,
                    fontWeight: 700,
                    cursor: "pointer",
                    fontFamily: T.font.body,
                    lineHeight: 1,
                  }}
                >
                  ?
                </button>
              </div>
            </div>
            <span style={{ marginLeft: 6, display: "inline-block" }}>
              <ThemeToggleButton compact style={{ padding: "2px 8px", fontSize: 9, borderRadius: T.radius.sm }} />
            </span>
            <button type="button" onClick={onSignOut} style={{ marginLeft: 4, padding: "2px 8px", borderRadius: T.radius.sm, border: `1px solid ${T.border.medium}`, background: T.bg.surface, color: T.text.muted, fontSize: 9, cursor: "pointer", fontFamily: T.font.body }}>
              Sign out
            </button>
          </div>
        )}

        <div style={{ flex: 1 }} />

        <nav aria-label="Panel toggles" style={{ display: "flex", gap: 2, flexWrap: "wrap", maxWidth: "42vw", justifyContent: "flex-end" }}>
          {panels.map(p => {
            const vis = isVis(p.id);
            return (
              <button key={p.id} type="button" onClick={() => togglePanel(p.id)} title={`${vis?"Hide":"Show"} ${p.title}`}
                aria-label={`${vis?"Hide":"Show"} ${p.title}`} aria-pressed={vis}
                style={{
                  width: 26, height: 22, borderRadius: T.radius.sm,
                  border: `1px solid ${vis ? (p.accent||T.hue.violet)+"30" : T.border.subtle}`,
                  background: vis ? (p.accent||T.hue.violet)+"15" : "transparent",
                  color: vis ? (p.accent||T.hue.violet) : T.text.muted,
                  cursor: "pointer", fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center",
                  transition: "all 0.15s", position: "relative",
                }}>
                {p.icon}
                {(p.badge||0) > 0 && vis && <span style={{ position: "absolute", top: -3, right: -3, width: 7, height: 7, borderRadius: 4, background: T.hue.crimson }}/>}
              </button>
            );
          })}
        </nav>

        <div style={{ width: 1, height: 16, background: T.border.dim }} />

        <div style={{ position: "relative" }}>
          <button type="button" onClick={() => setShowLayoutPicker(!showLayoutPicker)} aria-haspopup="listbox" aria-expanded={showLayoutPicker}
            style={{ padding: "2px 8px", borderRadius: T.radius.sm, border: `1px solid ${T.border.medium}`, background: T.bg.surface, color: T.text.secondary, fontFamily: T.font.body, fontSize: 9, cursor: "pointer", display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ fontSize: 10 }}>⊞</span>{preset.name}<span style={{ fontSize: 7, opacity: 0.5 }}>▼</span>
          </button>
          {showLayoutPicker && (
            <div role="listbox" style={{ position: "absolute", top: "100%", right: 0, marginTop: 4, background: T.bg.elevated, border: `1px solid ${T.border.medium}`, borderRadius: T.radius.md, padding: 4, minWidth: 170, boxShadow: T.shadow.panel, zIndex: 10000 }}>
              {Object.entries(PRESETS).map(([k, lp]) => (
                <button key={k} type="button" role="option" aria-selected={layout===k} onClick={() => { setLayout(k); setShowLayoutPicker(false); }}
                  style={{ display: "block", width: "100%", padding: "5px 8px", background: layout===k?T.hue.violetDim:"transparent", border: "none", borderRadius: T.radius.sm, textAlign: "left", cursor: "pointer" }}>
                  <div style={{ fontSize: 10, fontFamily: T.font.body, color: layout===k?T.text.accent:T.text.primary }}>{lp.name}</div>
                  <div style={{ fontSize: 8, fontFamily: T.font.body, color: T.text.muted }}>{lp.desc}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
          <div style={{ width: 5, height: 5, borderRadius: "50%", background: wsConnected ? T.hue.emerald : T.hue.crimson, boxShadow: wsConnected ? `0 0 6px ${T.hue.emerald}60` : `0 0 6px ${T.hue.crimson}40` }} />
          <span style={{ fontFamily: T.font.mono, fontSize: 8, color: T.text.muted }}>{wsConnected ? "Linked" : "Offline"}</span>
        </div>
      </header>

      <main style={{ position: "absolute", top: HEADER_PX, left: 0, right: 0, bottom: 0, overflow: "hidden" }}>
        {panels.map(p => {
          if (!isVis(p.id)) return null;
          const declaredIndex = (session?.declaredPanels || []).findIndex((d) => d.id === p.id);
          const pp = preset.panels[p.id] || (declaredIndex >= 0 ? declaredPanelBox(declaredIndex) : null);
          if (!pp) return null;
          const dw = Math.max(120, Math.round(pp.w * sx));
          const dh = Math.max(80, Math.round(pp.h * sy));
          const minW = Math.min(dw, Math.max(140, Math.round(p.minW * sx)));
          const minH = Math.min(dh, Math.max(72, Math.round(p.minH * sy)));
          return (
            <DraggablePanel
              key={`${p.id}-${layout}-${layoutKey}`}
              id={p.id}
              title={p.title}
              icon={p.icon}
              defaultPos={{ x: Math.round(pp.x * sx), y: Math.round(pp.y * sy) }}
              defaultSize={{ w: dw, h: dh }}
              minW={minW}
              minH={minH}
              collapsed={!!collapsed[p.id]}
              onToggleCollapse={toggleCollapse}
              zIndex={getZ(p.id)}
              onFocus={bringToFront}
              accentColor={p.accent}
              badge={p.badge}
            >
              {p.content}
            </DraggablePanel>
          );
        })}
      </main>
    </div>
    </GameCmdContext.Provider>
  );
}
