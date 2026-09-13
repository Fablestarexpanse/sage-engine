import { useState, useContext } from "react";
import { Tooltip } from "./01-primitives.jsx";
import { GameCmdContext } from "./00-ctx.jsx";
import { usePlayTheme } from "../PlayThemeContext.jsx";

export function AfflictionTracker({ effects = null }) {
  const { T } = usePlayTheme();
  // Server-pushed live effects only ({name, description, debuff, seconds_left}) —
  // no invented demo entries.
  const live = effects || [];
  const fmtDur = (s) => (s == null ? "∞" : `${s}s`);
  const afflictions = live
    .filter((e) => e.debuff)
    .map((e) => ({ name: e.name, icon: "⊘", dur: fmtDur(e.seconds_left), desc: e.description || "", color: T.glyph.crimson }));
  const buffs = live
    .filter((e) => !e.debuff)
    .map((e) => ({ name: e.name, icon: "◈", dur: fmtDur(e.seconds_left), desc: e.description || "", color: T.glyph.emerald }));
  if (!live.length) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", padding: 10 }}>
        <span style={{ fontSize: 10, fontFamily: T.font.body, color: T.text.muted }}>
          {effects === null ? "Waiting for server…" : "Nothing ails or aids you."}
        </span>
      </div>
    );
  }
  return (
    <div style={{ height: "100%", overflow: "auto", padding: 6 }}>
      {afflictions.length > 0 && (
        <>
          <div style={{ fontSize: 9, fontFamily: T.font.body, color: T.text.danger, textTransform: "uppercase", letterSpacing: "0.1em", padding: "2px 6px", marginBottom: 3 }}>Afflictions ({afflictions.length})</div>
          {afflictions.map((a, i) => (
            <Tooltip key={i} text={a.name} detail={a.desc}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 6px", marginBottom: 2, background: T.glyph.crimsonDim, borderRadius: T.radius.sm, borderLeft: `3px solid ${a.color}`, cursor: "default" }}>
                <span style={{ fontSize: 13, width: 18, textAlign: "center" }}>{a.icon}</span>
                <span style={{ flex: 1, fontSize: 11, fontFamily: T.font.body, color: T.text.danger }}>{a.name}</span>
                <span style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted }}>{a.dur}</span>
              </div>
            </Tooltip>
          ))}
        </>
      )}
      <div style={{ fontSize: 9, fontFamily: T.font.body, color: T.text.success, textTransform: "uppercase", letterSpacing: "0.1em", padding: "2px 6px", margin: "6px 0 3px" }}>Buffs ({buffs.length})</div>
      {buffs.map((b, i) => (
        <Tooltip key={i} text={b.name} detail={b.desc}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 6px", marginBottom: 2, background: `${b.color}12`, borderRadius: T.radius.sm, borderLeft: `3px solid ${b.color}40`, cursor: "default" }}>
            <span style={{ fontSize: 13, width: 18, textAlign: "center" }}>{b.icon}</span>
            <span style={{ flex: 1, fontSize: 11, fontFamily: T.font.body, color: b.color }}>{b.name}</span>
            <span style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted }}>{b.dur}</span>
          </div>
        </Tooltip>
      ))}
    </div>
  );
}

export function QuestJournal({ gameCurrencyLabel = "Digi" }) {
  const { T } = usePlayTheme();
  const [filter, setFilter] = useState("active");
  const quests = [
    { id: 1, title: "The Sentinel's Memory", zone: "Sector 7", type: "main", status: "active",
      objectives: [{ text: "Locate the Corroded Sentinel", done: true }, { text: "Retrieve the glyph-shard", done: false }],
      progress: 50, reward: "Glyph: Sentinel's Echo", digiPayout: 250 },
    { id: 2, title: "Cartographer's Ambition", zone: "Sector 7", type: "exploration", status: "active",
      objectives: [{ text: "Discover 8 rooms", done: false, count: "5/8" }],
      progress: 62, reward: "Map Fragment", digiPayout: 120 },
  ];
  const typeIcon = { main: "⬡", side: "◇", exploration: "🗺", repeatable: "↻" };
  const typeColor = { main: T.glyph.violet, side: T.glyph.cyan, exploration: T.glyph.emerald, repeatable: T.glyph.amber };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", borderBottom: `1px solid ${T.border.subtle}`, padding: "0 4px" }}>
        {["active", "completed", "all"].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            flex: 1, padding: "5px 0", background: "none", border: "none",
            borderBottom: filter === f ? `2px solid ${T.glyph.violet}` : "2px solid transparent",
            color: filter === f ? T.text.accent : T.text.muted, fontFamily: T.font.body,
            fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", cursor: "pointer",
          }}>{f} {f === "active" && `(${quests.length})`}</button>
        ))}
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 4 }}>
        {quests.map(q => (
          <div key={q.id} style={{ padding: "8px 6px", borderBottom: `1px solid ${T.border.subtle}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <span style={{ fontSize: 14, color: typeColor[q.type] }}>{typeIcon[q.type]}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontFamily: T.font.body, fontWeight: 600, color: T.text.primary }}>{q.title}</div>
                <div style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.muted }}>{q.zone} · {q.type}</div>
              </div>
              <div style={{ width: 32, textAlign: "right", fontSize: 10, fontFamily: T.font.mono, color: typeColor[q.type] }}>{q.progress}%</div>
            </div>
            <div style={{ height: 3, borderRadius: 2, background: T.bg.void, overflow: "hidden", marginBottom: 6 }}>
              <div style={{ height: "100%", width: `${q.progress}%`, background: typeColor[q.type], borderRadius: 2, transition: "width 0.3s" }} />
            </div>
            {q.objectives.map((obj, j) => (
              <div key={j} style={{ display: "flex", alignItems: "flex-start", gap: 6, padding: "2px 0 2px 20px" }}>
                <span style={{ fontSize: 10, color: obj.done ? T.text.success : T.text.muted, marginTop: 2 }}>{obj.done ? "✓" : "○"}</span>
                <span style={{ fontSize: 11, fontFamily: T.font.body, color: obj.done ? T.text.muted : T.text.secondary, textDecoration: obj.done ? "line-through" : "none", flex: 1 }}>{obj.text}</span>
                {obj.count && <span style={{ fontSize: 9, fontFamily: T.font.mono, color: T.text.accent }}>{obj.count}</span>}
              </div>
            ))}
            <div style={{ fontSize: 9, fontFamily: T.font.mono, color: T.currency.digi.fg, padding: "4px 0 0 20px" }}>
              ★ {q.reward}
              {q.digiPayout != null ? ` · ${q.digiPayout} ${gameCurrencyLabel}` : ""}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TargetPanel() {
  const { T } = usePlayTheme();
  const target = { name: "Corroded Sentinel", type: "Construct", level: 16, hp: 68, hpMax: 100, status: "Suppressed", weaknesses: ["Resonance"], resistances: ["Physical"], afflictions: ["Ward of Stillness"] };
  const hpPct = (target.hp / target.hpMax) * 100;
  const hpColor = hpPct > 50 ? T.glyph.emerald : hpPct > 25 ? T.glyph.amber : T.glyph.crimson;
  return (
    <div style={{ height: "100%", padding: 8, overflow: "auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <div style={{ width: 36, height: 36, borderRadius: T.radius.md, background: T.glyph.amberDim, border: `1px solid ${T.glyph.amber}30`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>⬡</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontFamily: T.font.body, fontWeight: 600, color: T.glyph.amber }}>{target.name}</div>
          <div style={{ fontSize: 10, fontFamily: T.font.mono, color: T.text.muted }}>{target.type} · Lv {target.level} · {target.status}</div>
        </div>
      </div>
      <div style={{ marginBottom: 4 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
          <span style={{ fontSize: 10, fontFamily: T.font.body, color: T.text.muted }}>♥ Health</span>
          <span style={{ fontSize: 11, fontFamily: T.font.mono, color: hpColor }}>{target.hp}/{target.hpMax}</span>
        </div>
        <div style={{ height: 8, borderRadius: 4, background: T.bg.void, overflow: "hidden", border: `1px solid ${T.border.subtle}` }}>
          <div style={{ height: "100%", width: `${hpPct}%`, background: `linear-gradient(90deg,${hpColor},${hpColor}cc)`, borderRadius: 4, transition: "width 0.5s" }} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 8 }}>
        {target.weaknesses.map(w => <span key={w} style={{ fontSize: 9, fontFamily: T.font.mono, padding: "2px 6px", borderRadius: T.radius.sm, background: T.glyph.crimsonDim, color: T.text.danger, border: `1px solid ${T.border.danger}` }}>WEAK: {w}</span>)}
        {target.resistances.map(r => <span key={r} style={{ fontSize: 9, fontFamily: T.font.mono, padding: "2px 6px", borderRadius: T.radius.sm, background: T.bg.surface, color: T.text.muted, border: `1px solid ${T.border.subtle}` }}>RES: {r}</span>)}
      </div>
    </div>
  );
}

export function SessionStats() {
  const { T } = usePlayTheme();
  const stats = [
    { label: "Session Time", value: "1h 12m", icon: "⏱" },
    { label: "XP Gained", value: "4,280", icon: "★" },
    { label: "Rooms Explored", value: "14", icon: "🗺" },
    { label: "Glyphs Cast", value: "8", icon: "✦" },
  ];
  return (
    <div style={{ height: "100%", overflow: "auto", padding: 6 }}>
      {stats.map((s, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 6px", borderBottom: i < stats.length - 1 ? `1px solid ${T.border.subtle}` : "none" }}>
          <span style={{ fontSize: 13, width: 20, textAlign: "center" }}>{s.icon}</span>
          <span style={{ flex: 1, fontSize: 11, fontFamily: T.font.body, color: T.text.secondary }}>{s.label}</span>
          <span style={{ fontSize: 12, fontFamily: T.font.mono, color: T.text.primary, fontWeight: 600 }}>{s.value}</span>
        </div>
      ))}
    </div>
  );
}

export function KeybindManager() {
  const { T } = usePlayTheme();
  const binds = [
    { key: "1–6", action: "Glyph slots", cat: "combat" },
    { key: "Ctrl+F", action: "Search scrollback", cat: "nav" },
    { key: "Ctrl+Q", action: "Quest journal", cat: "ui" },
    { key: "Tab", action: "Autocomplete", cat: "input" },
  ];
  const catColor = { combat: T.glyph.crimson, nav: T.glyph.cyan, ui: T.glyph.violet, input: T.glyph.amber };
  const catLabel = { combat: "Combat", nav: "Navigation", ui: "Interface", input: "Input" };
  const grouped = {};
  binds.forEach(b => { (grouped[b.cat] = grouped[b.cat] || []).push(b); });

  return (
    <div style={{ height: "100%", overflow: "auto", padding: 6 }}>
      {Object.entries(grouped).map(([cat, items]) => (
        <div key={cat} style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 9, fontFamily: T.font.body, color: catColor[cat], textTransform: "uppercase", letterSpacing: "0.1em", padding: "2px 6px", marginBottom: 3 }}>{catLabel[cat]}</div>
          {items.map((b, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "3px 6px" }}>
              <span style={{
                fontFamily: T.font.mono, fontSize: 10, color: T.text.primary,
                background: T.bg.surface, padding: "2px 6px", borderRadius: T.radius.sm,
                border: `1px solid ${T.border.medium}`, minWidth: 48, textAlign: "center",
              }}>{b.key}</span>
              <span style={{ fontSize: 11, fontFamily: T.font.body, color: T.text.secondary }}>{b.action}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function TriggerBuilder() {
  const { T } = usePlayTheme();
  const triggers = [
    { name: "Auto-sip health", pattern: "health drops below 50%", action: "use tincture", enabled: true, type: "text" },
    { name: "Highlight tells", pattern: "^\\w+ tells you:", action: "Highlight cyan", enabled: true, type: "regex" },
  ];
  const typeColor = { text: T.glyph.emerald, regex: T.glyph.amber, wildcard: T.glyph.cyan };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ flex: 1, overflow: "auto", padding: 4 }}>
        {triggers.map((tr, i) => (
          <div key={i} style={{
            padding: "6px 8px", marginBottom: 4, borderRadius: T.radius.sm,
            background: tr.enabled ? T.bg.surface : T.bg.deep,
            border: `1px solid ${tr.enabled ? T.border.dim : T.border.subtle}`,
            opacity: tr.enabled ? 1 : 0.5,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
              <span style={{ flex: 1, fontSize: 11, fontFamily: T.font.body, color: T.text.primary, fontWeight: 600 }}>{tr.name}</span>
              <span style={{ fontSize: 8, fontFamily: T.font.mono, padding: "1px 5px", borderRadius: T.radius.sm, background: typeColor[tr.type] + "20", color: typeColor[tr.type], textTransform: "uppercase" }}>{tr.type}</span>
            </div>
            <div style={{ fontSize: 10, fontFamily: T.font.mono, color: T.text.muted, padding: "0 4px" }}>
              Match: <span style={{ color: T.glyph.amber }}>{tr.pattern}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function QuickActions() {
  const { T } = usePlayTheme();
  const { sendCommand, focusProficienciesPanel } = useContext(GameCmdContext);
  const actions = [
    { label: "Look", cmd: "look", icon: "👁", color: T.text.secondary },
    { label: "Get All", cmd: "get all", icon: "✋", color: T.glyph.cyan },
    { label: "Inventory", cmd: "inventory", icon: "◻", color: T.glyph.amber },
    { label: "Score", cmd: "score", icon: "★", color: T.glyph.violet },
    { label: "Skills", cmd: "", icon: "◇", color: T.glyph.violet, openSkills: true },
    { label: "Rest", cmd: "rest", icon: "💤", color: T.glyph.emerald },
    { label: "Map", cmd: "map", icon: "🗺", color: T.glyph.cyan },
  ];
  return (
    <div style={{ height: "100%", display: "flex", flexWrap: "wrap", gap: 3, padding: 6, alignContent: "flex-start" }}>
      {actions.map((a, i) => (
        <button key={i} type="button" title={a.openSkills ? "Open Skills panel" : a.cmd} aria-label={a.openSkills ? `${a.label} (panel)` : `${a.label} (${a.cmd})`}
          onClick={() => (a.openSkills ? focusProficienciesPanel?.() : sendCommand(a.cmd))}
          style={{
            display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
            gap: 2, width: 52, height: 44, borderRadius: T.radius.md,
            background: T.bg.surface, border: `1px solid ${T.border.subtle}`,
            cursor: "pointer", transition: "all 0.15s",
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = a.color + "50"; e.currentTarget.style.background = a.color + "12"; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = T.border.subtle; e.currentTarget.style.background = T.bg.surface; }}
        >
          <span style={{ fontSize: 14 }}>{a.icon}</span>
          <span style={{ fontSize: 7, fontFamily: T.font.body, color: T.text.muted, textTransform: "uppercase" }}>{a.label}</span>
        </button>
      ))}
    </div>
  );
}
