import { useMemo, useState } from "react";
import { usePlayTheme } from "../PlayThemeContext.jsx";
import { ReputationThermometer } from "../ReputationThermometer.jsx";
import { PORTRAIT_ASPECT_RATIO_CSS } from "../portraitProfile.js";
import { Tooltip } from "./01-primitives.jsx";

const RESONANCE_CAP = 5000;

/** Frosted quick-read: account, Digi wallet, PVP, reputation, location, level (pixels in header). */
function ConduitGlassStrip({ locationLabel, level, accountName, digiBalance, gameCurrencyLabel, pvpEnabled, reputation }) {
  const { T } = usePlayTheme();
  const glass = {
    padding: "10px 10px 8px",
    borderBottom: `1px solid ${T.border.subtle}`,
    background: `linear-gradient(165deg, ${T.bg.panel}f0 0%, ${T.bg.deep}e6 100%)`,
    backdropFilter: "blur(14px)",
    WebkitBackdropFilter: "blur(14px)",
    boxShadow: `inset 0 1px 0 ${T.border.subtle}40`,
  };
  const micro = {
    fontSize: 8,
    fontFamily: T.font.body,
    color: T.text.muted,
    textTransform: "uppercase",
    letterSpacing: "0.11em",
    marginBottom: 3,
  };
  return (
    <div style={glass}>
      {accountName ? (
        <div style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted, marginBottom: 8, opacity: 0.85 }}>
          <span style={{ opacity: 0.65 }}>Account</span>{" "}
          <span style={{ color: T.text.secondary }}>{accountName}</span>
        </div>
      ) : null}
      {digiBalance != null && gameCurrencyLabel ? (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            gap: 8,
            marginBottom: 10,
            padding: "6px 8px",
            borderRadius: T.radius.md,
            background: T.currency.digi.bg,
            border: `1px solid ${T.currency.digi.border}`,
          }}
        >
          <div style={{ ...micro, marginBottom: 0, color: T.currency.digi.fg }}>{gameCurrencyLabel}</div>
          <div style={{ fontSize: 15, fontFamily: T.font.mono, fontWeight: 700, color: T.currency.digi.fg }}>{digiBalance}</div>
        </div>
      ) : null}
      {typeof pvpEnabled === "boolean" ? (
        <div
          style={{
            marginBottom: 10,
            padding: "6px 8px",
            borderRadius: T.radius.md,
            border: `1px solid ${pvpEnabled ? `${T.glyph.crimson}55` : `${T.text.success}40`}`,
            background: pvpEnabled ? T.glyph.crimsonDim : "rgba(52,211,153,0.08)",
          }}
        >
          <div style={{ ...micro, marginBottom: 2 }}>Player combat</div>
          <div
            style={{
              fontSize: 11,
              fontFamily: T.font.body,
              fontWeight: 700,
              color: pvpEnabled ? T.glyph.crimson : T.text.success,
            }}
          >
            {pvpEnabled ? "PVP enabled" : "No PVP"}
          </div>
          <div style={{ fontSize: 8, color: T.text.muted, marginTop: 3, lineHeight: 1.35 }}>
            {pvpEnabled ? "You can be engaged by other players where rules allow." : "Opt-in PVP is off; toggle later when supported in-game."}
          </div>
        </div>
      ) : null}
      {typeof reputation === "number" ? <ReputationThermometer reputation={reputation} /> : null}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "stretch", gap: 10, marginBottom: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={micro}>Location</div>
          <div
            title={locationLabel || ""}
            style={{
              fontSize: 11,
              fontFamily: T.font.body,
              color: T.text.secondary,
              lineHeight: 1.4,
              wordBreak: "break-word",
              maxHeight: 40,
              overflow: "hidden",
            }}
          >
            {locationLabel?.trim() ? locationLabel : "No room line yet — move or look"}
          </div>
        </div>
        <div style={{ flexShrink: 0, width: 52, textAlign: "center", padding: "4px 6px", borderRadius: T.radius.md, background: `${T.glyph.violet}14`, border: `1px solid ${T.glyph.violet}35` }}>
          <div style={{ ...micro, marginBottom: 2 }}>Prof. Σ</div>
          <div style={{ fontSize: 18, fontFamily: T.font.display, fontWeight: 700, color: T.glyph.violet, lineHeight: 1.1 }}>
            {level != null && level !== "" ? level : "—"}
          </div>
          <div style={{ fontSize: 7, color: T.text.muted, marginTop: 2, lineHeight: 1.2, opacity: 0.75 }}>/{RESONANCE_CAP}</div>
        </div>
      </div>
    </div>
  );
}

export function CharacterPanel({
  displayName = "Kael Voss",
  portraitImageUrl = null,
  accountName = null,
  locationLabel = "",
  level = null,
  /** Server-backed stats (includes legacy keys + `conduit` proficiency block). */
  characterStats = null,
  resonanceLevelsTotal = null,
  digiBalance = null,
  gameCurrencyLabel = "Digi",
  pvpEnabled = null,
  reputation = null,
  /** Server-pushed live effects: [{name, description, debuff, seconds_left}] or null. */
  effects = null,
  /** Large Conduit portrait; set false when the cutout is shown behind Narrative instead. */
  showHeroPortrait = true,
}) {
  const { T } = usePlayTheme();
  const [tab, setTab] = useState("vitals");
  const ca = characterStats?.conduit?.conduit_attributes;
  const rsv = typeof ca?.RSV === "number" ? ca.RSV : 10;
  const resTotal = typeof resonanceLevelsTotal === "number" ? resonanceLevelsTotal : 0;
  const hp = typeof characterStats?.hp === "number" ? characterStats.hp : 73;
  const hpMax = typeof characterStats?.max_hp === "number" ? characterStats.max_hp : 100;
  const s = {
    hp,
    hpMax,
    mp: typeof characterStats?.mp === "number" ? characterStats.mp : 45,
    mpMax: typeof characterStats?.mpMax === "number" ? characterStats.mpMax : 80,
    res: resTotal,
    resMax: RESONANCE_CAP,
    madness: Math.max(0, Math.min(100, 100 - rsv)),
    madnessMax: 100,
  };
  const Bar = ({ label, val, max, color, icon }) => {
    const p = (val/max)*100, low = p < 25;
    return (
      <div style={{ marginBottom: 5 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 1 }}>
          <span style={{ fontSize: 10, fontFamily: T.font.body, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em" }}>{icon} {label}</span>
          <span style={{ fontSize: 11, fontFamily: T.font.mono, color: low ? T.text.danger : T.text.secondary }}>{val}<span style={{ opacity: 0.4 }}>/{max}</span></span>
        </div>
        <div style={{ height: 5, borderRadius: 3, background: T.bg.void, overflow: "hidden", border: `1px solid ${T.border.subtle}` }}>
          <div style={{ height: "100%", borderRadius: 3, width: `${p}%`, background: `linear-gradient(90deg,${color},${color}cc)`, boxShadow: low ? `0 0 8px ${color}60` : "none", transition: "width 0.5s" }} />
        </div>
      </div>
    );
  };
  const headerH = portraitImageUrl ? null : 90;
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {!showHeroPortrait ? (
        <div
          style={{
            flexShrink: 0,
            padding: "10px 12px 9px",
            borderBottom: `1px solid ${T.border.subtle}`,
            background: `linear-gradient(165deg, ${T.glyph.violetDim} 0%, ${T.bg.deep} 100%)`,
            boxShadow: `inset 0 1px 0 ${T.border.subtle}40`,
          }}
        >
          <div
            style={{
              fontFamily: T.font.display,
              fontSize: 14,
              fontWeight: 700,
              color: T.text.accent,
              letterSpacing: "0.04em",
              lineHeight: 1.2,
            }}
          >
            {displayName}
          </div>
        </div>
      ) : (
        <div
          className={portraitImageUrl ? "fablestar-portrait-stage" : undefined}
          style={
            portraitImageUrl
              ? {
                  position: "relative",
                  width: "100%",
                  aspectRatio: PORTRAIT_ASPECT_RATIO_CSS,
                  maxHeight: 220,
                  overflow: "hidden",
                  borderBottom: `1px solid ${T.border.subtle}`,
                  borderRadius: `${T.radius.md}px ${T.radius.md}px 0 0`,
                }
              : {
                  height: headerH,
                  position: "relative",
                  overflow: "hidden",
                  background: `radial-gradient(ellipse at center,${T.glyph.violetDim},${T.bg.deep})`,
                  borderBottom: `1px solid ${T.border.subtle}`,
                }
          }
        >
          {portraitImageUrl ? <div className="fablestar-portrait-aurora" aria-hidden /> : null}
          {portraitImageUrl ? (
            <img
              src={portraitImageUrl}
              alt=""
              className="fablestar-portrait-cutout fablestar-portrait-cutout--hero"
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "contain",
                objectPosition: "center center",
              }}
            />
          ) : null}
          <div
            style={{
              position: "absolute",
              inset: 0,
              zIndex: portraitImageUrl ? 3 : undefined,
              background: portraitImageUrl
                ? `linear-gradient(180deg, transparent 0%, ${T.bg.void}35 55%, ${T.bg.deep} 100%)`
                : "transparent",
              pointerEvents: "none",
            }}
          />
          <svg
            style={{
              position: "absolute",
              inset: 0,
              zIndex: portraitImageUrl ? 1 : undefined,
              opacity: portraitImageUrl ? 0.06 : 0.08,
            }}
            viewBox={portraitImageUrl ? "0 0 200 200" : `0 0 200 ${headerH}`}
            preserveAspectRatio="none"
          >
            {[...Array(5)].map((_, i) => (
              <circle
                key={i}
                cx={100}
                cy={portraitImageUrl ? 100 : headerH / 2}
                r={10 + i * 10}
                fill="none"
                stroke={T.glyph.violet}
                strokeWidth={0.5}
                strokeDasharray="3 5"
              />
            ))}
          </svg>
          {!portraitImageUrl ? (
            <div
              style={{
                position: "absolute",
                bottom: 0,
                left: "50%",
                transform: "translateX(-50%)",
                width: 60,
                height: 80,
                background: `linear-gradient(180deg,transparent,${T.glyph.violet}20)`,
                borderRadius: "30px 30px 0 0",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 28,
                color: T.glyph.violet + "40",
              }}
            >
              ◈
            </div>
          ) : null}
          <div
            style={{
              position: "absolute",
              bottom: 4,
              left: 6,
              zIndex: portraitImageUrl ? 4 : undefined,
              fontFamily: T.font.display,
              fontSize: 13,
              color: T.text.primary,
              textShadow: "0 1px 4px rgba(0,0,0,0.95), 0 0 12px rgba(0,0,0,0.8)",
            }}
          >
            {displayName}
          </div>
        </div>
      )}
      <ConduitGlassStrip
        locationLabel={locationLabel}
        level={level}
        accountName={accountName}
        digiBalance={digiBalance}
        gameCurrencyLabel={gameCurrencyLabel}
        pvpEnabled={pvpEnabled}
        reputation={reputation}
      />
      <div style={{ display: "flex", borderBottom: `1px solid ${T.border.subtle}` }}>
        {["vitals","stats","effects"].map(t => <button key={t} type="button" onClick={()=>setTab(t)} style={{ flex: 1, padding: "5px 0", background: "none", border: "none", borderBottom: tab===t?`2px solid ${T.glyph.violet}`:"2px solid transparent", color: tab===t?T.text.accent:T.text.muted, fontFamily: T.font.body, fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", cursor: "pointer" }}>{t}</button>)}
      </div>
      <div style={{ flex: 1, padding: 8, overflow: "auto" }}>
        {tab === "vitals" && <>
          <Bar label="Health" val={s.hp} max={s.hpMax} color={T.glyph.crimson} icon="♥" />
          <Bar label="Mana" val={s.mp} max={s.mpMax} color={T.glyph.cyan} icon="◆" />
          <Bar label="Resonance" val={s.res} max={s.resMax} color={T.glyph.violet} icon="✦" />
          <div style={{ height: 1, margin: "6px 0", background: T.border.subtle }} />
          <Bar label="Madness" val={s.madness} max={s.madnessMax} color={T.glyph.amber} icon="⊘" />
        </>}
        {tab === "effects" && (
          <div>
            {!(effects && effects.length) ? (
              <div style={{ fontSize: 10, fontFamily: T.font.body, color: T.text.muted, padding: "6px 2px" }}>
                Nothing ails or aids you.
              </div>
            ) : (
              effects.map((e, i) => (
                <div key={i} style={{ marginBottom: 6, padding: "5px 7px", background: T.bg.surface, borderRadius: T.radius.sm, border: `1px solid ${e.debuff ? T.glyph.crimson + "40" : T.glyph.emerald + "40"}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 11, fontFamily: T.font.body, color: e.debuff ? T.glyph.crimson : T.glyph.emerald }}>{e.name}</span>
                    <span style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted }}>
                      {e.seconds_left == null ? "∞" : `${e.seconds_left}s`}
                    </span>
                  </div>
                  {e.description ? (
                    <div style={{ fontSize: 9, fontFamily: T.font.body, color: T.text.muted, marginTop: 2 }}>{e.description}</div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        )}
        {tab === "stats" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
            {(ca
              ? [
                  { l: "FRT", v: ca.FRT },
                  { l: "RFX", v: ca.RFX },
                  { l: "ACU", v: ca.ACU },
                  { l: "RSV", v: ca.RSV },
                  { l: "PRS", v: ca.PRS },
                ]
              : []
            ).concat(
              characterStats
                ? [
                    { l: "STR", v: characterStats.strength ?? "—" },
                    { l: "DEX", v: characterStats.dexterity ?? "—" },
                  ]
                : [{ l: "STR", v: "—" }, { l: "DEX", v: "—" }]
            ).map((st) => (
              <div key={st.l} style={{ background: T.bg.surface, borderRadius: T.radius.sm, padding: "5px 7px", border: `1px solid ${T.border.subtle}`, display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 10, fontFamily: T.font.mono, color: T.text.muted }}>{st.l}</span>
                <span style={{ fontSize: 11, fontFamily: T.font.mono, color: T.text.primary }}>{st.v}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function GlyphBar() {
  const { T } = usePlayTheme();
  const [hov, setHov] = useState(null);
  const glyphs = [
    { id:1,name:"Ward of Stillness",slot:"L.Forearm",tier:2,color:T.glyph.cyan,icon:"◇",cd:0,cost:15,key:"1" },
    { id:2,name:"Searing Inscription",slot:"R.Palm",tier:3,color:T.glyph.crimson,icon:"⬡",cd:2,cost:25,key:"2" },
    { id:3,name:"Echo Thread",slot:"Spine",tier:1,color:T.glyph.violet,icon:"◈",cd:0,cost:10,key:"3" },
    { id:null,name:"Empty",slot:"—",tier:0,color:T.text.muted,icon:"○",cd:0,cost:0,key:"4" },
  ];
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${glyphs.length},1fr)`, gap: 3, padding: 6, flex: 1 }}>
        {glyphs.map((g,i) => {
          const h = hov===i, onCd = g.cd>0;
          return (
            <Tooltip key={i} text={g.name} detail={g.id ? `T${g.tier} · ${g.slot} · ${g.cost} RES` : "Empty slot"}>
              <div onMouseEnter={()=>setHov(i)} onMouseLeave={()=>setHov(null)}
                role="button" aria-label={`Glyph ${g.key}: ${g.name}`}
                style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 2, padding: "6px 2px", background: h&&g.id?g.color+"15":T.bg.surface, border: `1px solid ${g.id?(h?g.color+"50":g.color+"25"):T.border.subtle}`, borderRadius: T.radius.md, cursor: g.id?"pointer":"default", opacity: onCd?0.5:1, transition: "all 0.15s" }}>
                <span style={{ fontSize: 18, color: g.color, lineHeight: 1 }}>{g.icon}</span>
                <span style={{ fontSize: 7, fontFamily: T.font.body, color: T.text.muted, textAlign: "center", lineHeight: 1.1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "100%" }}>{g.name}</span>
                <span style={{ position: "absolute", top: 2, right: 3, fontSize: 7, fontFamily: T.font.mono, color: T.text.muted+"60" }}>{g.key}</span>
                {onCd && <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: T.bg.overlay, borderRadius: T.radius.md, fontFamily: T.font.mono, fontSize: 14, color: T.text.muted, fontWeight: 700 }}>{g.cd}</div>}
              </div>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

export function InventoryPanel({ onContextMenu, items: liveItems = null }) {
  const { T } = usePlayTheme();
  const [filter, setFilter] = useState("all");
  // Server inventory entries ({id, template, name, value, ...}) grouped by name into qty rows.
  // Until the first server snapshot arrives (liveItems === null) the panel shows an empty state,
  // never invented demo items.
  const items = useMemo(() => {
    const grouped = new Map();
    for (const it of liveItems || []) {
      const name = it?.name || it?.template || "unknown item";
      const prev = grouped.get(name);
      if (prev) prev.qty += 1;
      else grouped.set(name, { name, type: "material", rarity: "common", icon: "◻", qty: 1 });
    }
    return [...grouped.values()];
  }, [liveItems]);
  const rc = { common: T.text.secondary, uncommon: T.glyph.emerald, rare: T.glyph.cyan, epic: T.glyph.violet, legendary: T.glyph.amber };
  const filtered = filter === "all" ? items : items.filter(i => i.type === filter);
  if (!items.length) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", padding: 10 }}>
        <span style={{ fontSize: 10, fontFamily: T.font.body, color: T.text.muted }}>
          {liveItems === null ? "Waiting for server…" : "You are carrying nothing."}
        </span>
      </div>
    );
  }
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", padding: "3px 4px", gap: 3, borderBottom: `1px solid ${T.border.subtle}` }}>
        {["all","equipment","consumable","material"].map(f => <button key={f} type="button" onClick={()=>setFilter(f)} style={{ padding: "2px 6px", borderRadius: T.radius.sm, border: "none", background: filter===f?T.glyph.violetDim:"transparent", color: filter===f?T.text.accent:T.text.muted, fontFamily: T.font.body, fontSize: 8, textTransform: "uppercase", cursor: "pointer" }}>{f}</button>)}
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 3 }}>
        {filtered.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 6px", borderRadius: T.radius.sm, cursor: "pointer" }}
            onContextMenu={(e) => { e.preventDefault(); onContextMenu?.({ x: e.clientX, y: e.clientY, items: [{ icon: "👁", label: "Examine", action:()=>{} }, { icon: "🔧", label: "Use", action:()=>{} }] }); }}
            onMouseEnter={e => e.currentTarget.style.background = T.bg.surface}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}
          >
            <span style={{ fontSize: 14, color: rc[item.rarity], width: 18, textAlign: "center" }}>{item.icon}</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, fontFamily: T.font.body, color: rc[item.rarity] }}>{item.name}</div>
            </div>
            {item.qty > 1 && <span style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted }}>×{item.qty}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SocialPanel({ unreadCounts }) {
  const { T } = usePlayTheme();
  const [ch, setCh] = useState("party");
  const channels = [
    { id: "party", label: "Party", color: T.glyph.cyan },
    { id: "local", label: "Local", color: T.text.secondary },
    { id: "tells", label: "Tells", color: T.glyph.violet },
  ];
  const msgs = {
    party: [{ from: "Lyra", text: "Sentinel suppressed — go now", time: "19:43" }, { from: "You", text: "Moving to Glyph Chamber", time: "19:43" }],
    local: [{ from: "Sentinel", text: "*optics flicker*", time: "19:43", emote: true }],
    tells: [{ from: "Syra Vane", text: "Spare filaments?", time: "19:35" }],
  };
  const party = [
    { name: "You", role: "Inscriptor", hp: 73, status: "active", you: true },
    { name: "Lyra Ashfen", role: "Wardkeeper", hp: 88, status: "active" },
  ];
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: 4, borderBottom: `1px solid ${T.border.subtle}` }}>
        {party.map((p,i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5, padding: "2px 4px", borderRadius: T.radius.sm, background: p.you?T.glyph.violetDim:"transparent" }}>
            <div style={{ width: 5, height: 5, borderRadius: "50%", background: p.status==="combat"?T.glyph.crimson:T.glyph.emerald }}/>
            <span style={{ flex: 1, fontSize: 10, fontFamily: T.font.body, color: p.you?T.text.accent:T.text.primary }}>{p.name}</span>
            <span style={{ fontSize: 8, fontFamily: T.font.mono, color: T.text.muted }}>{p.role}</span>
            <div style={{ width: 28, height: 3, borderRadius: 2, background: T.bg.void }}><div style={{ height: "100%", borderRadius: 2, width: `${p.hp}%`, background: p.hp<30?T.glyph.crimson:T.glyph.emerald }}/></div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", borderBottom: `1px solid ${T.border.subtle}` }}>
        {channels.map(c => {
          const unread = (unreadCounts||{})[c.id] || 0;
          return (
            <button key={c.id} type="button" onClick={()=>setCh(c.id)} aria-label={`${c.label} channel`}
              style={{ flex: 1, padding: "4px 0", background: "none", border: "none", borderBottom: ch===c.id?`2px solid ${c.color}`:"2px solid transparent", color: ch===c.id?c.color:T.text.muted, fontFamily: T.font.body, fontSize: 8, textTransform: "uppercase", letterSpacing: "0.06em", cursor: "pointer", position: "relative" }}>
              {c.label}
              {unread > 0 && <span style={{ position: "absolute", top: 1, right: 2, width: 8, height: 8, borderRadius: 4, background: T.glyph.crimson, fontSize: 0 }}/>}
            </button>
          );
        })}
      </div>
      <div role="log" aria-label={`${ch} messages`} style={{ flex: 1, overflow: "auto", padding: 4 }}>
        {(msgs[ch]||[]).map((m,i) => (
          <div key={i} style={{ marginBottom: 5 }}>
            <div style={{ display: "flex", gap: 4, alignItems: "baseline" }}>
              <span style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted, opacity: 0.4 }}>{m.time}</span>
              <span style={{ fontSize: 10, fontFamily: T.font.body, fontWeight: 600, color: m.from==="You"?T.text.accent:T.glyph.cyan }}>{m.from}</span>
            </div>
            <div style={{ fontSize: 11, fontFamily: m.emote?T.font.body:T.font.mono, fontStyle: m.emote?"italic":"normal", color: T.text.secondary, paddingLeft: 36, lineHeight: 1.4 }}>{m.text}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 4, padding: "3px 4px", borderTop: `1px solid ${T.border.subtle}` }}>
        <input placeholder={`${ch}...`} aria-label={`Send to ${ch}`}
          style={{ flex: 1, background: T.bg.surface, border: `1px solid ${T.border.subtle}`, borderRadius: T.radius.sm, padding: "3px 6px", outline: "none", color: T.text.primary, fontFamily: T.font.mono, fontSize: 10 }}/>
      </div>
    </div>
  );
}

export function ScenePanel({
  imageUrl,
  roomLabel,
  downloadBaseName = "fablestar-scene",
  generating = false,
  usingSceneAsNarrativeBackdrop = false,
  onUseSceneAsNarrativeBackdrop,
  onResetNarrativeBackdropToCharacter,
  onOpenSceneGallery,
}) {
  const { T } = usePlayTheme();
  const [opacity, setOpacity] = useState(85);
  const [downBusy, setDownBusy] = useState(false);
  const hasImage = Boolean(imageUrl && String(imageUrl).trim());

  const runDownload = async () => {
    if (!hasImage || !imageUrl) return;
    setDownBusy(true);
    try {
      const res = await fetch(imageUrl, { credentials: "omit" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${downloadBaseName || "fablestar-scene"}.png`;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      window.alert(e?.message || "Download failed — try opening the image in a new tab from your browser.");
    } finally {
      setDownBusy(false);
    }
  };

  const openInNewTab = () => {
    if (hasImage && imageUrl) window.open(imageUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", position: "relative" }}>
      <div style={{ flex: 1, position: "relative", overflow: "hidden", background: `radial-gradient(ellipse at 40% 30%,${T.glyph.violetDim},${T.bg.deep})` }}>
        {hasImage ? (
          <div style={{ position: "absolute", inset: 0, opacity: opacity / 100 }}>
            <img
              src={imageUrl}
              alt=""
              style={{ width: "100%", height: "100%", objectFit: "cover", display: "block", pointerEvents: "none" }}
            />
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: `linear-gradient(180deg, transparent 55%, ${T.bg.void}e6)`,
                pointerEvents: "none",
              }}
            />
          </div>
        ) : (
          <div style={{ position: "absolute", inset: 0, background: `radial-gradient(ellipse at 30% 20%,${T.glyph.violet}12,transparent 50%),linear-gradient(180deg,${T.bg.void},${T.bg.deep})`, opacity: opacity / 100 }}>
            <svg style={{ position: "absolute", inset: 0, opacity: 0.15 }} viewBox="0 0 400 300">
              <rect x="170" y="180" width="60" height="80" rx="3" fill={T.glyph.violet + "08"} stroke={T.glyph.violet + "30"} strokeWidth="0.5" />
            </svg>
            <div
              style={{
                position: "absolute",
                left: "50%",
                top: "42%",
                transform: "translate(-50%, -50%)",
                fontSize: 10,
                color: T.text.muted,
                textAlign: "center",
                maxWidth: "85%",
                lineHeight: 1.45,
                fontFamily: T.font.body,
              }}
            >
              Generate scene art from the narrative toolbar (🎨). Your last image is saved to this character and reloads here.
            </div>
          </div>
        )}
        <div style={{ position: "absolute", bottom: 6, right: 6, display: "flex", alignItems: "center", gap: 4, background: T.bg.overlay, padding: "2px 6px", borderRadius: T.radius.sm }}>
          <input type="range" min={0} max={100} value={opacity} onChange={(e) => setOpacity(+e.target.value)} aria-label="Image opacity" style={{ width: 50, accentColor: T.glyph.violet, height: 2 }} />
        </div>
        {generating ? (
          <div
            role="status"
            aria-live="polite"
            aria-label="Generating scene art"
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 12,
              background: "rgba(6,6,10,0.72)",
              backdropFilter: "blur(2px)",
            }}
          >
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: "50%",
                border: `3px solid ${T.border.dim}`,
                borderTopColor: T.glyph.violet,
                animation: "spin 0.9s linear infinite",
              }}
            />
            <span style={{ fontFamily: T.font.body, fontSize: 11, color: T.text.secondary, textAlign: "center", maxWidth: "88%", lineHeight: 1.45 }}>
              Generating scene art on the server…
            </span>
          </div>
        ) : null}
      </div>
      <div style={{ padding: "4px 8px", borderTop: `1px solid ${T.border.subtle}`, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
        <span style={{ fontFamily: T.font.display, fontSize: 11, color: T.text.accent }}>{roomLabel || "Scene"}</span>
        <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
          <button
            type="button"
            disabled={!hasImage}
            onClick={() => onUseSceneAsNarrativeBackdrop?.()}
            title="Use this scene image behind the Narrative panel"
            style={{
              padding: "3px 8px",
              borderRadius: T.radius.sm,
              border: `1px solid ${usingSceneAsNarrativeBackdrop ? T.border.glyph : T.border.subtle}`,
              background: usingSceneAsNarrativeBackdrop ? T.glyph.violetDim : T.bg.surface,
              color: usingSceneAsNarrativeBackdrop ? T.text.accent : T.text.muted,
              fontFamily: T.font.body,
              fontSize: 9,
              cursor: hasImage ? "pointer" : "not-allowed",
              opacity: hasImage ? 1 : 0.5,
            }}
          >
            Scene as BG
          </button>
          <button
            type="button"
            disabled={!onResetNarrativeBackdropToCharacter || !usingSceneAsNarrativeBackdrop}
            onClick={() => onResetNarrativeBackdropToCharacter?.()}
            title="Reset Narrative background back to your character portrait"
            style={{
              padding: "3px 8px",
              borderRadius: T.radius.sm,
              border: `1px solid ${T.border.subtle}`,
              background: T.bg.surface,
              color: T.text.muted,
              fontFamily: T.font.body,
              fontSize: 9,
              cursor: !onResetNarrativeBackdropToCharacter || !usingSceneAsNarrativeBackdrop ? "not-allowed" : "pointer",
              opacity: !onResetNarrativeBackdropToCharacter || !usingSceneAsNarrativeBackdrop ? 0.5 : 1,
            }}
          >
            Character BG
          </button>
          <button
            type="button"
            disabled={!onOpenSceneGallery}
            onClick={() => onOpenSceneGallery?.()}
            title="Open your generated scene image gallery"
            style={{
              padding: "3px 8px",
              borderRadius: T.radius.sm,
              border: `1px solid ${T.border.subtle}`,
              background: T.bg.surface,
              color: T.text.muted,
              fontFamily: T.font.body,
              fontSize: 9,
              cursor: onOpenSceneGallery ? "pointer" : "not-allowed",
              opacity: onOpenSceneGallery ? 1 : 0.5,
            }}
          >
            My Scenes
          </button>
          {hasImage ? (
            <>
              <button
                type="button"
                disabled={downBusy}
                onClick={runDownload}
                title="Save PNG to your device"
                style={{
                  padding: "3px 8px",
                  borderRadius: T.radius.sm,
                  border: `1px solid ${T.border.medium}`,
                  background: T.glyph.violetDim,
                  color: T.text.accent,
                  fontFamily: T.font.body,
                  fontSize: 9,
                  fontWeight: 600,
                  cursor: downBusy ? "wait" : "pointer",
                }}
              >
                {downBusy ? "…" : "Download"}
              </button>
              <button
                type="button"
                onClick={openInNewTab}
                title="Open full image in a new tab"
                style={{
                  padding: "3px 8px",
                  borderRadius: T.radius.sm,
                  border: `1px solid ${T.border.subtle}`,
                  background: T.bg.surface,
                  color: T.text.muted,
                  fontFamily: T.font.body,
                  fontSize: 9,
                  cursor: "pointer",
                }}
              >
                Open
              </button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
