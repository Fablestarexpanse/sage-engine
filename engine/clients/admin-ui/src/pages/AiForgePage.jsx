import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE, WS_BASE } from "../apiConfig.js";
import {
  LS_ADMIN_TOKEN, ALL_ADMIN_TOOLS, adminWsBase, adminPresenceWsUrl, adminLogsWsUrl,
  sendWsAuthToken, parseLeadingInt, parseRoomType, extractYamlRoomId, Icons,
  Badge, StatusDot, Pill, ActionButton, PlannedAction, SearchBar, TabBar,
  DataTable, StatCard, usePolledList, FetchErrorBanner,
} from "../adminCommon.jsx";


// ═══════════════════════════════════════════════════════════════
// AI FORGE — LLM Content Generation Studio
// ═══════════════════════════════════════════════════════════════

const FORGE_CATEGORIES = [
  {
    id: "room", label: "Room / Location", icon: <Icons.Locations />, colorKey: "info",
    desc: "Generate room descriptions, exits, ambient messages, and environmental details",
    fields: [
      { key: "zone", label: "Target Zone", type: "select", options: ["Outer Labyrinth", "Archive Depths", "The Crucible", "Shattered Gallery", "Resonance Caverns", "Tutorial Spire", "Pumpkin Fields"] },
      { key: "room_type", label: "Room Type", type: "select", options: ["chamber", "corridor", "hub", "dead_end", "hazard", "boss_arena", "sanctuary", "puzzle"] },
      { key: "depth", label: "Depth Level", type: "select", options: ["0 (Surface)", "1 (Shallow)", "2 (Mid)", "3 (Deep)", "4 (Abyssal)", "5 (Core)"] },
      { key: "mood", label: "Atmosphere", type: "select", options: ["foreboding", "serene", "chaotic", "ancient", "corrupted", "luminous", "decaying", "mechanical"] },
      { key: "details", label: "Additional Context", type: "textarea", placeholder: "Any specific features, lore connections, adjacent room context..." },
    ],
    promptTemplates: [
      "Generate a detailed room with base description, 3 time-of-day variants, and 2 ambient messages",
      "Create a puzzle room with environmental clues and hidden interactions",
      "Design a boss arena with phase-transition descriptions",
      "Write 5 connected corridor rooms with a thematic progression",
    ],
  },
  {
    id: "entity", label: "Entity / NPC", icon: <Icons.Entities />, colorKey: "warning",
    desc: "Create NPCs with dialogue, behavior patterns, combat abilities, and memory templates",
    fields: [
      { key: "entity_type", label: "Entity Type", type: "select", options: ["Hunter", "Watcher", "Guide", "Archivist", "Boss", "Vendor", "Ambient", "Quest NPC"] },
      { key: "zone", label: "Home Zone", type: "select", options: ["Outer Labyrinth", "Archive Depths", "The Crucible", "Shattered Gallery", "Resonance Caverns"] },
      { key: "level_range", label: "Level Range", type: "select", options: ["1-10 (Novice)", "11-25 (Intermediate)", "26-45 (Advanced)", "46-60 (Expert)", "61+ (Legendary)"] },
      { key: "behavior", label: "Behavior Pattern", type: "select", options: ["patrol", "static", "ambient", "scripted", "adaptive", "territorial", "fleeing", "stalking"] },
      { key: "details", label: "Character Concept", type: "textarea", placeholder: "Personality, backstory hooks, unique traits, combat style..." },
    ],
    promptTemplates: [
      "Create a Hunter entity with adaptive combat AI and 3 combat phases",
      "Design a Guide NPC with branching dialogue tree and lore delivery",
      "Generate an Archivist with a knowledge quiz mechanic",
      "Build a Vendor with personality, inventory theming, and bartering dialogue",
    ],
  },
  {
    id: "item", label: "Item", icon: <Icons.Items />, colorKey: "success",
    desc: "Design equipment, consumables, lore objects, and key items with stats and flavor text",
    fields: [
      { key: "item_type", label: "Item Type", type: "select", options: ["Equipment", "Consumable", "Material", "Key", "Lore", "Currency", "Artifact"] },
      { key: "rarity", label: "Rarity", type: "select", options: ["common", "uncommon", "rare", "epic", "legendary"] },
      { key: "theme", label: "Thematic Origin", type: "select", options: ["Labyrinth-forged", "Ancient Conduit tech", "Void-touched", "Resonance crystal", "Organic/living", "Mechanical/construct"] },
      { key: "details", label: "Item Concept", type: "textarea", placeholder: "Function, visual appearance, lore significance..." },
    ],
    promptTemplates: [
      "Generate a set of 5 themed loot drops for a specific zone",
      "Design a legendary artifact with lore, stats, and discovery quest hook",
      "Create a consumable crafting chain with 3 tiers of ingredients",
      "Write flavor text for 10 common materials found in the labyrinth",
    ],
  },
  {
    id: "glyph", label: "Glyph / Ability", icon: <Icons.Glyphs />, colorKey: "accent",
    desc: "Design glyph tattoos with mechanics, visual descriptions, and balance parameters",
    fields: [
      { key: "category", label: "Category", type: "select", options: ["Combat", "Defense", "Utility", "Perception", "Movement", "Social"] },
      { key: "tier", label: "Tier", type: "select", options: ["1 (Initiate)", "2 (Adept)", "3 (Master)", "4 (Transcendent)", "5 (Mythic)"] },
      { key: "body_slot", label: "Body Slot", type: "select", options: ["forearm", "upper arm", "chest", "back", "calf", "thigh", "palm", "temple", "spine", "shoulder"] },
      { key: "details", label: "Ability Concept", type: "textarea", placeholder: "Mechanical effect, visual manifestation, lore origin..." },
    ],
    promptTemplates: [
      "Design a glyph chain: 3 related glyphs that combo together",
      "Create a defensive glyph with scaling based on adaptive level",
      "Generate a utility glyph tree with 5 progression tiers",
      "Design a mythic-tier glyph with dramatic inscription sequence narrative",
    ],
  },
  {
    id: "quest", label: "Quest / Objective", icon: <Icons.Content />, colorKey: "danger",
    desc: "Create quest chains with objectives, branching paths, dialogue, and reward structures",
    fields: [
      { key: "quest_type", label: "Quest Type", type: "select", options: ["Main story", "Side quest", "Discovery", "Repeatable", "Event", "Hidden", "Tutorial"] },
      { key: "difficulty", label: "Difficulty", type: "select", options: ["Trivial", "Easy", "Medium", "Hard", "Legendary"] },
      { key: "zone", label: "Zone", type: "select", options: ["Outer Labyrinth", "Archive Depths", "The Crucible", "Shattered Gallery", "Resonance Caverns", "Multi-zone"] },
      { key: "details", label: "Quest Concept", type: "textarea", placeholder: "Story hook, objectives, key NPCs, reward ideas..." },
    ],
    promptTemplates: [
      "Create a 3-part quest chain with branching outcomes",
      "Design a hidden discovery quest with environmental clue progression",
      "Generate a repeatable hunt quest with adaptive difficulty scaling",
      "Build a tutorial quest that teaches glyph combat mechanics naturally",
    ],
  },
  {
    id: "dialogue", label: "Dialogue Tree", icon: <Icons.Activity />, colorKey: "cyan",
    desc: "Write NPC conversation flows with conditions, personality, and memory integration",
    fields: [
      { key: "npc_type", label: "NPC Type", type: "select", options: ["Guide", "Archivist", "Vendor", "Quest giver", "Lore keeper", "Antagonist", "Fellow Conduit"] },
      { key: "tone", label: "Personality Tone", type: "select", options: ["cryptic", "friendly", "hostile", "melancholic", "manic", "scholarly", "fearful", "ancient"] },
      { key: "context", label: "Conversation Context", type: "select", options: ["First meeting", "Returning player", "Quest delivery", "Lore dump", "Trading", "Warning", "Betrayal"] },
      { key: "details", label: "Dialogue Concept", type: "textarea", placeholder: "Topic, emotional arc, information to convey, branching triggers..." },
    ],
    promptTemplates: [
      "Write a first-meeting dialogue with 3 personality-based response branches",
      "Create a lore-delivery conversation that reveals info through questions",
      "Design a vendor haggling dialogue with price negotiation mechanics",
      "Generate a cryptic warning dialogue with hidden clue integration",
    ],
  },
  {
    id: "zone", label: "Zone / Region", icon: <Icons.World />, colorKey: "forge",
    desc: "Design entire zones with room layouts, entity populations, lore, and progression flow",
    fields: [
      { key: "zone_type", label: "Zone Type", type: "select", options: ["exploration", "dungeon", "boss", "safe", "tutorial", "puzzle", "gauntlet"] },
      { key: "depth", label: "Depth Level", type: "select", options: ["0 (Surface)", "1 (Shallow)", "2 (Mid)", "3 (Deep)", "4 (Abyssal)", "5 (Core)"] },
      { key: "room_count", label: "Approximate Rooms", type: "select", options: ["10-20 (Small)", "20-50 (Medium)", "50-100 (Large)", "100+ (Massive)"] },
      { key: "details", label: "Zone Concept", type: "textarea", placeholder: "Theme, narrative purpose, key landmarks, unique mechanics..." },
    ],
    promptTemplates: [
      "Design a complete zone blueprint with room graph and entity placement",
      "Create a dungeon zone with 3 puzzle rooms leading to a boss encounter",
      "Generate a safe hub zone with vendors, lore NPCs, and social spaces",
      "Build an adaptive gauntlet zone that escalates based on player performance",
    ],
  },
];

// Resolve category colors from the ACTIVE theme so Forge follows light/dark mode
// (a static dark-palette lookup here previously pinned these to dark-mode colors).
function useForgeCategories() {
  const { colors } = useAdminTheme();
  return useMemo(
    () => FORGE_CATEGORIES.map((c) => ({ ...c, color: colors[c.colorKey] || colors.accent })),
    [colors]
  );
}

const ForgePromptTemplateButton = ({ tmpl, cat, onPick }) => {
  const { colors: COLORS } = useAdminTheme();
  const [h, setH] = useState(false);
  return (
    <button type="button" onClick={() => onPick(tmpl)}
      onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
      style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
        background: h ? `${cat.color}10` : "transparent",
        border: `1px solid ${h ? cat.color + "30" : COLORS.border}`,
        borderRadius: 6, cursor: "pointer", textAlign: "left",
        color: COLORS.text, fontSize: 12, fontFamily: "'DM Sans', sans-serif",
        transition: "all 0.12s ease",
      }}
    >
      <span style={{ color: cat.color, flexShrink: 0 }}><Icons.Sparkles /></span>
      {tmpl}
    </button>
  );
};

const ForgeChat = ({ category, onClose }) => {
  const { colors: COLORS } = useAdminTheme();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [yamlPreview, setYamlPreview] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [formValues, setFormValues] = useState({});
  const [showYaml, setShowYaml] = useState(false);
  const [lastInjectId, setLastInjectId] = useState(null);
  const [injectBusy, setInjectBusy] = useState(false);
  const chatRef = useRef(null);
  const forgeCategories = useForgeCategories();
  const cat = forgeCategories.find(c => c.id === category);

  const runGeneration = useCallback(async (prompt) => {
    setIsGenerating(true);
    const contextParts = [];
    Object.entries(formValues).forEach(([k, v]) => {
      if (v && k !== "details") contextParts.push(`${k}: ${v}`);
    });
    const contextStr = contextParts.length > 0 ? `\n\nContext: ${contextParts.join(", ")}` : "";
    const fullSeed = prompt + contextStr;

    setMessages((prev) => [...prev,
      { role: "user", content: fullSeed },
      { role: "assistant", content: null, loading: true },
    ]);

    try {
      let yaml = "";
      let parsedId = null;
      if (category === "room") {
        const { data } = await axios.post(`${API_BASE}/forge/generate`, {
          seed: fullSeed,
          room_type: parseRoomType(formValues.room_type),
          depth: parseLeadingInt(formValues.depth),
        });
        yaml = data.yaml;
        parsedId = data.id ?? null;
      } else {
        const { data } = await axios.post(`${API_BASE}/forge/generate-content`, {
          category,
          seed: fullSeed,
          context: formValues,
        });
        yaml = data.yaml;
        const root = data.data;
        if (root && typeof root === "object" && root.id) parsedId = root.id;
      }
      const responseText =
        `**${cat.label}** generated via Nexus. Review YAML on the right. **Rooms**: deploy writes \`content/world/zones/<zone>/rooms/\` (needs \`id: zone:slug\`). **Entities / items**: use **Deploy** to save under \`content/world/entities/\` or \`items/\`. **Other categories**: copy YAML into the repo manually — no inject route yet.`;
      setMessages((prev) => prev.map((m, i) =>
        (i === prev.length - 1 ? { role: "assistant", content: responseText, loading: false } : m)
      ));
      setYamlPreview(yaml);
      setLastInjectId(parsedId || extractYamlRoomId(yaml));
      setShowYaml(true);
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : (detail ? JSON.stringify(detail) : (e.message || "Request failed"));
      setMessages((prev) => prev.map((m, i) =>
        (i === prev.length - 1 ? { role: "assistant", content: `**Error:** ${msg}`, loading: false } : m)
      ));
      setYamlPreview(null);
      setLastInjectId(null);
    } finally {
      setIsGenerating(false);
    }
  }, [category, formValues, cat]);

  const handleSend = () => {
    if (!input.trim() || isGenerating) return;
    runGeneration(input.trim());
    setInput("");
  };

  const copyYaml = () => {
    if (yamlPreview) navigator.clipboard.writeText(yamlPreview);
  };

  const canDeployYaml = category === "room" || category === "entity" || category === "item";

  const deployContent = async () => {
    if (!yamlPreview || !canDeployYaml) return;
    setInjectBusy(true);
    try {
      if (category === "room") {
        const rid = lastInjectId || extractYamlRoomId(yamlPreview);
        if (!rid || !rid.includes(":")) {
          window.alert("Room YAML needs an id like zone_key:room_slug to deploy.");
          return;
        }
        await axios.post(`${API_BASE}/forge/inject`, { id: rid, yaml_content: yamlPreview });
        window.alert(`Saved room to content/world/zones (${rid}).`);
        return;
      }
      if (category === "entity") {
        let eid = lastInjectId || extractYamlRoomId(yamlPreview);
        if (!eid || !/^[a-zA-Z0-9_]+$/.test(String(eid).trim())) {
          const p = window.prompt("Entity ID (filename without .yaml):", eid ? String(eid).trim() : "");
          if (p === null) return;
          eid = String(p).trim();
        }
        if (!eid || !/^[a-zA-Z0-9_]+$/.test(eid)) {
          window.alert("Invalid entity id (use letters, numbers, underscores).");
          return;
        }
        await axios.put(`${API_BASE}/content/entities/${eid}/yaml`, {
          path: `entities/${eid}`,
          yaml_content: yamlPreview,
        });
        window.alert(`Saved entity to content/world/entities/${eid}.yaml`);
        try {
          await axios.post(`${API_BASE}/content/cache/reload`);
        } catch {
          /* cache reload is optional (may require server tool) */
        }
        return;
      }
      if (category === "item") {
        let iid = lastInjectId || extractYamlRoomId(yamlPreview);
        if (!iid || !/^[a-zA-Z0-9_]+$/.test(String(iid).trim())) {
          const p = window.prompt("Item ID (filename without .yaml):", iid ? String(iid).trim() : "");
          if (p === null) return;
          iid = String(p).trim();
        }
        if (!iid || !/^[a-zA-Z0-9_]+$/.test(iid)) {
          window.alert("Invalid item id (use letters, numbers, underscores).");
          return;
        }
        await axios.put(`${API_BASE}/content/items/${iid}/yaml`, {
          path: `items/${iid}`,
          yaml_content: yamlPreview,
        });
        window.alert(`Saved item to content/world/items/${iid}.yaml`);
        try {
          await axios.post(`${API_BASE}/content/cache/reload`);
        } catch {
          /* optional */
        }
      }
    } catch (e) {
      const detail = e.response?.data?.detail;
      window.alert(typeof detail === "string" ? detail : (e.message || "Deploy failed"));
    } finally {
      setInjectBusy(false);
    }
  };

  const handleTemplateClick = (template) => {
    setSelectedTemplate(template);
    setInput(template);
  };

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages]);

  if (!cat) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 0 }}>
      {/* Forge Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "16px 20px", borderBottom: `1px solid ${COLORS.border}`,
        background: `linear-gradient(135deg, ${COLORS.bgCard} 0%, ${cat.color}08 100%)`,
        borderRadius: "10px 10px 0 0",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: `${cat.color}15`, border: `1px solid ${cat.color}30`,
            display: "flex", alignItems: "center", justifyContent: "center", color: cat.color,
          }}>{cat.icon}</div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif", display: "flex", alignItems: "center", gap: 8 }}>
              AI Forge: {cat.label}
              <Badge color={COLORS.forge}>LLM-Assisted</Badge>
            </div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", marginTop: 2 }}>{cat.desc}</div>
          </div>
        </div>
        <ActionButton small variant="ghost" onClick={onClose}>Close</ActionButton>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left: Context Panel + Chat */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", borderRight: showYaml ? `1px solid ${COLORS.border}` : "none", minWidth: 0 }}>
          {/* Context Fields */}
          <div style={{
            padding: "14px 18px", borderBottom: `1px solid ${COLORS.border}`, background: COLORS.bgCard,
            display: "flex", flexDirection: "column", gap: 10, flexShrink: 0,
          }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>
              Generation Context
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
              {cat.fields.filter(f => f.type === "select").map(field => (
                <div key={field.key}>
                  <label style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", marginBottom: 3, display: "block" }}>{field.label}</label>
                  <select
                    value={formValues[field.key] || ""}
                    onChange={e => setFormValues(prev => ({ ...prev, [field.key]: e.target.value }))}
                    style={{
                      width: "100%", padding: "6px 10px", background: COLORS.bgInput,
                      border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text,
                      fontSize: 12, fontFamily: "'DM Sans', sans-serif",
                    }}
                  >
                    <option value="">Select...</option>
                    {field.options.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
              ))}
            </div>
            {cat.fields.filter(f => f.type === "textarea").map(field => (
              <div key={field.key}>
                <label style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", marginBottom: 3, display: "block" }}>{field.label}</label>
                <textarea
                  value={formValues[field.key] || ""}
                  onChange={e => setFormValues(prev => ({ ...prev, [field.key]: e.target.value }))}
                  placeholder={field.placeholder}
                  rows={2}
                  style={{
                    width: "100%", padding: "8px 10px", background: COLORS.bgInput,
                    border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text,
                    fontSize: 12, fontFamily: "'DM Sans', sans-serif", resize: "vertical",
                  }}
                />
              </div>
            ))}
          </div>

          {/* Quick Templates */}
          {messages.length === 0 && (
            <div style={{ padding: "14px 18px", borderBottom: `1px solid ${COLORS.border}`, flexShrink: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace", marginBottom: 10 }}>
                Prompt Templates
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {cat.promptTemplates.map((tmpl, i) => (
                  <ForgePromptTemplateButton key={i} tmpl={tmpl} cat={cat} onPick={handleTemplateClick} />
                ))}
              </div>
            </div>
          )}

          {/* Chat Messages */}
          <div ref={chatRef} style={{ flex: 1, overflow: "auto", padding: "14px 18px", display: "flex", flexDirection: "column", gap: 14 }}>
            {messages.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, gap: 12, opacity: 0.5 }}>
                <Icons.Forge />
                <span style={{ fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
                  Set your context above, then describe what you want to create
                </span>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} style={{
                display: "flex", flexDirection: "column", gap: 6,
                alignItems: msg.role === "user" ? "flex-end" : "flex-start",
              }}>
                <div style={{
                  maxWidth: "85%", padding: "10px 14px", borderRadius: 10,
                  background: msg.role === "user" ? `${COLORS.accent}20` : COLORS.bgCard,
                  border: `1px solid ${msg.role === "user" ? COLORS.accent + "30" : COLORS.border}`,
                }}>
                  {msg.loading ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, color: COLORS.forge }}>
                      <span style={{ animation: "pulse 1.5s ease-in-out infinite" }}><Icons.Sparkles /></span>
                      <span style={{ fontSize: 12, fontFamily: "'DM Sans', sans-serif" }}>Generating content...</span>
                    </div>
                  ) : (
                    <div style={{ fontSize: 13, color: COLORS.text, lineHeight: 1.6, fontFamily: "'DM Sans', sans-serif", whiteSpace: "pre-wrap" }}>
                      {msg.content?.split("**").map((part, pi) =>
                        pi % 2 === 1 ? <strong key={pi} style={{ color: cat.color }}>{part}</strong> : part
                      )}
                    </div>
                  )}
                </div>
                {msg.role === "assistant" && !msg.loading && (
                  <div style={{ display: "flex", gap: 4, paddingLeft: 4 }}>
                    <ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={() => {
                      const lastUserMsg = [...messages].reverse().find(m => m.role === "user");
                      if (lastUserMsg) runGeneration(lastUserMsg.content);
                    }}>Regenerate</ActionButton>
                    <ActionButton small variant="ghost" icon={<Icons.Copy />} onClick={copyYaml}>Copy</ActionButton>
                    {!showYaml && <ActionButton small variant="ghost" icon={<Icons.Code />} onClick={() => setShowYaml(true)}>Show YAML</ActionButton>}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Input Bar */}
          <div style={{
            padding: "12px 18px", borderTop: `1px solid ${COLORS.border}`, background: COLORS.bgCard,
            display: "flex", gap: 10, alignItems: "flex-end", flexShrink: 0,
          }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder={`Describe the ${cat.label.toLowerCase()} you want to create...`}
              rows={2}
              style={{
                flex: 1, padding: "10px 14px", background: COLORS.bgInput,
                border: `1px solid ${COLORS.border}`, borderRadius: 8, color: COLORS.text,
                fontSize: 13, fontFamily: "'DM Sans', sans-serif", resize: "none", outline: "none",
              }}
            />
            <ActionButton variant="forge" onClick={handleSend} disabled={!input.trim() || isGenerating}
              icon={isGenerating ? <span style={{ animation: "pulse 1s infinite" }}><Icons.Sparkles /></span> : <Icons.Send />}>
              {isGenerating ? "Forging..." : "Generate"}
            </ActionButton>
          </div>
        </div>

        {/* Right: YAML Preview Panel */}
        {showYaml && (
          <div style={{ width: "45%", minWidth: 340, display: "flex", flexDirection: "column", background: COLORS.bgPanel }}>
            <div style={{
              padding: "12px 16px", borderBottom: `1px solid ${COLORS.border}`,
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Icons.Code />
                <span style={{ fontSize: 13, fontWeight: 600, color: COLORS.text, fontFamily: "'DM Sans', sans-serif" }}>YAML Output</span>
                <Badge color={COLORS.success}>valid</Badge>
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                <ActionButton small variant="ghost" icon={<Icons.Copy />} onClick={copyYaml}>
                  {canDeployYaml ? "Copy" : "Copy YAML"}
                </ActionButton>
                {canDeployYaml && (
                  <ActionButton small variant="success" icon={<Icons.Save />} onClick={deployContent} disabled={injectBusy}>
                    {category === "room" ? "Accept" : category === "entity" ? "Deploy to entities/" : "Deploy to items/"}
                  </ActionButton>
                )}
                <ActionButton small variant="ghost" onClick={() => setShowYaml(false)}>Hide</ActionButton>
              </div>
            </div>
            {!canDeployYaml && yamlPreview && (
              <div style={{ padding: "8px 16px", fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", borderBottom: `1px solid ${COLORS.border}` }}>
                Save this YAML manually to the appropriate <code style={{ color: COLORS.textDim }}>content/</code> directory — no deploy path for this category yet.
              </div>
            )}
            <pre style={{
              flex: 1, overflow: "auto", padding: "14px 16px", margin: 0,
              fontSize: 11.5, lineHeight: 1.55, color: COLORS.text,
              fontFamily: "'JetBrains Mono', monospace",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {yamlPreview || "# YAML preview will appear here after generation..."}
            </pre>
            <div style={{
              padding: "10px 16px", borderTop: `1px solid ${COLORS.border}`,
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <div style={{ display: "flex", gap: 6 }}>
                {canDeployYaml ? (
                  <ActionButton small variant="success" icon={<Icons.Check />} onClick={deployContent} disabled={injectBusy || !yamlPreview}>
                    {injectBusy
                      ? "Deploying…"
                      : category === "room"
                        ? "Accept & Deploy"
                        : category === "entity"
                          ? "Deploy to entities/"
                          : "Deploy to items/"}
                  </ActionButton>
                ) : (
                  <ActionButton small variant="default" icon={<Icons.Copy />} onClick={copyYaml} disabled={!yamlPreview}>
                    Copy YAML
                  </ActionButton>
                )}
                <ActionButton small variant="default" icon={<Icons.Save />} onClick={copyYaml}>Save Draft</ActionButton>
              </div>
              <ActionButton small variant="danger" icon={<Icons.Trash />}>Discard</ActionButton>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const ForgeCategoryPickCard = ({ cat, onPick }) => {
  const { colors: COLORS } = useAdminTheme();
  const [h, setH] = useState(false);
  return (
    <button
      type="button"
      onClick={() => onPick(cat.id)}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "flex", gap: 14, alignItems: "flex-start", padding: 18,
        background: h ? `${cat.color}08` : COLORS.bgCard,
        border: `1px solid ${h ? cat.color + "40" : COLORS.border}`,
        borderRadius: 10, cursor: "pointer", textAlign: "left",
        transition: "all 0.15s ease",
      }}
    >
      <div style={{
        width: 44, height: 44, borderRadius: 10, flexShrink: 0,
        background: `${cat.color}12`, border: `1px solid ${cat.color}25`,
        display: "flex", alignItems: "center", justifyContent: "center", color: cat.color,
        transition: "all 0.15s ease",
        transform: h ? "scale(1.08)" : "scale(1)",
      }}>{cat.icon}</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif", marginBottom: 4 }}>{cat.label}</div>
        <div style={{ fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5, fontFamily: "'DM Sans', sans-serif" }}>{cat.desc}</div>
        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          {cat.promptTemplates.slice(0, 2).map((t, i) => (
            <span key={i} style={{
              fontSize: 10, color: COLORS.textDim, padding: "2px 6px",
              background: COLORS.bgInput, borderRadius: 3,
              fontFamily: "'JetBrains Mono', monospace", maxWidth: 180,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>{t}</span>
          ))}
        </div>
      </div>
      <span style={{ color: COLORS.textDim, opacity: h ? 1 : 0.4, transition: "opacity 0.15s" }}><Icons.ChevronRight /></span>
    </button>
  );
};

const AiForgePage = () => {
  const { colors: COLORS } = useAdminTheme();
  const forgeCategories = useForgeCategories();
  const [activeCategory, setActiveCategory] = useState(null);
  const [historyFilter, setHistoryFilter] = useState("all");
  const [forgeHistoryRows] = useState([]);
  const [llmSnap, setLlmSnap] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/llm/status`);
        setLlmSnap(data);
      } catch {
        setLlmSnap(null);
      }
    };
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);

  if (activeCategory) {
    return (
      <div style={{
        display: "flex", flexDirection: "column", height: "calc(100vh - 56px)",
        background: COLORS.bgCard, borderRadius: 10, border: `1px solid ${COLORS.border}`, overflow: "hidden",
      }}>
        <ForgeChat category={activeCategory} onClose={() => setActiveCategory(null)} />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif", display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ color: COLORS.forge }}><Icons.Forge /></span>
            AI Forge
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
            LLM-powered content generation for every system in the Fablestar
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <Pill label="Backend" value={llmSnap?.primary_backend || "—"} color={COLORS.info} />
          <Pill label="Chat model" value={llmSnap?.chat_model || "—"} color={COLORS.forge} />
          <Pill
            label="LM link"
            value={llmSnap?.connected ? `${llmSnap.latency_ms ?? "?"} ms` : "offline"}
            color={llmSnap?.connected ? COLORS.success : COLORS.danger}
          />
        </div>
      </div>
      <p style={{ margin: 0, fontSize: 12, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif" }}>
        Forge uses the same OpenAI-compatible client as in-game narration (<code style={{ color: COLORS.textMuted }}>look</code>). Configure it on Server & Performance → LM Studio / LLM.
      </p>

      {/* Category Grid */}
      <div>
        <h3 style={{ margin: "0 0 14px", fontSize: 13, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace" }}>
          Choose Content Type
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
          {forgeCategories.map((cat) => (
            <ForgeCategoryPickCard key={cat.id} cat={cat} onPick={setActiveCategory} />
          ))}
        </div>
      </div>

      {/* Generation History */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono', monospace", display: "flex", alignItems: "center", gap: 8 }}>
            <Icons.History /> Generation History
          </h3>
          <TabBar tabs={[
            { id: "all", label: "All" },
            { id: "accepted", label: "Accepted" },
            { id: "editing", label: "Editing" },
            { id: "rejected", label: "Rejected" },
          ]} active={historyFilter} onChange={setHistoryFilter} />
        </div>
        <div style={{
          background: COLORS.bgCard, border: `1px solid ${COLORS.border}`,
          borderRadius: 10, overflow: "hidden",
        }}>
          <DataTable
            columns={[
              { label: "Type", render: row => {
                const cat = forgeCategories.find(c => c.id === row.category);
                return <Badge color={cat?.color}>{row.category}</Badge>;
              }},
              { label: "Prompt", render: row => (
                <span style={{ maxWidth: 360, display: "inline-block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {row.prompt}
                </span>
              )},
              { label: "Time", key: "timestamp", mono: true },
              { label: "Status", render: row => (
                <Badge color={
                  row.status === "accepted" ? COLORS.success :
                  row.status === "editing" ? COLORS.warning : COLORS.danger
                }>{row.status}</Badge>
              )},
              { label: "", render: row => (
                <div style={{ display: "flex", gap: 4 }}>
                  <ActionButton small variant="ghost" icon={<Icons.Eye />}>View</ActionButton>
                  <ActionButton small variant="ghost" icon={<Icons.Edit />}>Edit</ActionButton>
                  <ActionButton small variant="ghost" icon={<Icons.Refresh />}>Redo</ActionButton>
                </div>
              )},
            ]}
            rows={forgeHistoryRows.filter((h) => historyFilter === "all" || h.status === historyFilter)}
          />
        </div>
        {forgeHistoryRows.length === 0 && (
          <p style={{ margin: "10px 0 0", fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>
            No saved generations yet. History will appear here once the Nexus stores Forge runs (or use session-only workflow for now).
          </p>
        )}
      </div>
    </div>
  );
};

export default AiForgePage;
