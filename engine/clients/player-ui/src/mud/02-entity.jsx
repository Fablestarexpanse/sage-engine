import { useState } from "react";
import { Tooltip } from "./01-primitives.jsx";
import { usePlayTheme } from "../PlayThemeContext.jsx";

export function EntitySpan({ type, name, id, children, onContextMenu: parentCtx }) {
  const { T } = usePlayTheme();
  const colors = { npc: T.glyph.amber, item: T.glyph.cyan, exit: T.glyph.emerald, player: T.glyph.violet, glyph: T.text.glyph };
  const col = colors[type] || T.text.accent;
  const [hov, setHov] = useState(false);

  const menuItems = {
    npc: [
      { icon: "👁", label: "Examine", hint: "examine", action: () => {} },
      { icon: "💬", label: "Talk to", hint: "talk", action: () => {} },
      { icon: "⚔", label: "Attack", hint: "attack", action: () => {}, danger: true },
      { separator: true },
      { icon: "📌", label: "Track on map", action: () => {} },
    ],
    item: [
      { icon: "👁", label: "Examine", action: () => {} },
      { icon: "✋", label: "Get", hint: "get", action: () => {} },
      { icon: "🔧", label: "Use", action: () => {} },
      { separator: true },
      { icon: "📋", label: "Wiki lookup", action: () => {} },
    ],
    exit: [
      { icon: "🚪", label: "Go", action: () => {} },
      { icon: "👁", label: "Peek", hint: "peek", action: () => {} },
      { icon: "📌", label: "Set waypoint", action: () => {} },
    ],
    player: [
      { icon: "👁", label: "Inspect", action: () => {} },
      { icon: "💬", label: "Tell", action: () => {} },
      { icon: "🤝", label: "Invite to party", action: () => {} },
      { icon: "📋", label: "View profile", action: () => {} },
    ],
    glyph: [
      { icon: "✦", label: "Inscribe", action: () => {} },
      { icon: "📖", label: "View details", action: () => {} },
    ],
  };

  const handleContext = (e) => {
    e.preventDefault();
    parentCtx?.({ x: e.clientX, y: e.clientY, items: menuItems[type] || [] });
  };

  return (
    <Tooltip text={name} detail={`${type.charAt(0).toUpperCase() + type.slice(1)} · Right-click for actions`}>
      <span role="button" tabIndex={0} aria-label={`${name} (${type})`}
        onClick={() => {}} onContextMenu={handleContext}
        onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
        style={{
          color: col, cursor: "pointer", borderBottom: `1px ${hov ? "solid" : "dotted"} ${col}${hov ? "" : "50"}`,
          padding: "0 1px", transition: "all 0.1s", textShadow: hov ? `0 0 8px ${col}40` : "none",
          background: hov ? `${col}10` : "transparent", borderRadius: 2,
        }}
      >{children}</span>
    </Tooltip>
  );
}
