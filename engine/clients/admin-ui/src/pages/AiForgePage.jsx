import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE, WS_BASE } from "../apiConfig.js";
import { useWorldSummary, slotEnabled } from "../useWorldSummary.js";
import {
  LS_ADMIN_TOKEN, ALL_ADMIN_TOOLS, adminWsBase, adminPresenceWsUrl, adminLogsWsUrl,
  sendWsAuthToken, parseLeadingInt, parseRoomType, extractYamlRoomId, Icons,
  Badge, StatusDot, Pill, ActionButton, PlannedAction, SearchBar, TabBar,
  DataTable, StatCard, usePolledList, FetchErrorBanner,
} from "../adminCommon.jsx";


// ═══════════════════════════════════════════════════════════════
// AI FORGE — LLM Content Generation Studio
// ═══════════════════════════════════════════════════════════════

// Marker for zone pickers: filled with the running world's zones (GET /content/zones).
const WORLD_ZONES = "world_zones";

// Only content Forge can deploy: a room, an entity template or an item template. Each needs the
// world to fill its AI slot (worlds/<id>/ai/prompts/<slot>.j2); GET /admin/world says which do.
const WORLD_ROOM_TYPES = "world_room_types";

const FORGE_CATEGORIES = [
  {
    id: "room", slot: "forge.room", label: "Room", icon: <Icons.Locations />, colorKey: "info",
    desc: "A room YAML for one of this world's zones: name, description, exits and features. Accept writes it to the zone.",
    fields: [
      { key: "zone", label: "Target zone", type: "select", options: WORLD_ZONES },
      { key: "room_type", label: "Room type", type: "select", options: WORLD_ROOM_TYPES },
      { key: "depth", label: "Depth", type: "select", options: ["1", "2", "3", "4", "5"] },
      { key: "mood", label: "Atmosphere", type: "select", options: ["calm", "busy", "tense", "eerie", "cheerful", "run-down", "grand", "cramped"] },
      { key: "details", label: "Additional context", type: "textarea", placeholder: "Features, neighbouring rooms, what a visitor should notice…" },
    ],
    promptTemplates: [
      "A room with a clear description, two examinable features and exit descriptions",
      "A quiet side room that rewards examining things",
      "A busy crossroads room that connects several parts of the zone",
    ],
  },
  {
    id: "entity", slot: "forge.content", label: "Entity template", icon: <Icons.Entities />, colorKey: "warning",
    desc: "A creature or character template (name, description, stats, loot) saved to the world's entities.",
    fields: [
      { key: "zone", label: "Home zone", type: "select", options: WORLD_ZONES },
      { key: "details", label: "Concept", type: "textarea", placeholder: "What it is, how it looks, how tough it should be, what it drops…" },
    ],
    promptTemplates: [
      "A weak creature suitable for new players, with one loot drop",
      "A tougher creature for deeper rooms, with two loot drops",
    ],
  },
  {
    id: "item", slot: "forge.content", label: "Item template", icon: <Icons.Items />, colorKey: "success",
    desc: "An item template (name, type, value, description) saved to the world's items.",
    fields: [
      { key: "item_type", label: "Item type", type: "select", options: ["equipment", "consumable", "material", "key", "junk"] },
      { key: "details", label: "Concept", type: "textarea", placeholder: "What it is, what it is for, how it looks…" },
    ],
    promptTemplates: [
      "A common material a creature could drop",
      "A simple consumable a shop could sell",
    ],
  },
];

// Resolve category colors from the ACTIVE theme so Forge follows light/dark mode
// (a static dark-palette lookup here previously pinned these to dark-mode colors).
function useForgeCategories() {
  const { colors } = useAdminTheme();
  const { rows: zones } = usePolledList(`${API_BASE}/content/zones`, 60000);
  const { summary } = useWorldSummary();
  return useMemo(() => {
    const zoneNames = zones.map((z) => z.name || z.id).filter(Boolean);
    const roomTypes = summary?.world?.room_types || [];
    return FORGE_CATEGORIES.map((c) => ({
      ...c,
      color: colors[c.colorKey] || colors.accent,
      enabled: summary ? slotEnabled(summary, c.slot) : true,
      fields: c.fields.map((f) =>
        f.options === WORLD_ZONES ? { ...f, options: zoneNames }
          : f.options === WORLD_ROOM_TYPES ? { ...f, options: roomTypes }
          : f),
    }));
  }, [colors, zones, summary]);
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
        `**${cat.label}** generated. Review the YAML on the right. **Rooms**: Accept checks it and writes it to the zone (needs \`id: zone:slug\`). **Entity and item templates**: Deploy saves them to the world's \`entities/\` or \`items/\`.`;
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
      disabled={!cat.enabled}
      title={cat.enabled ? undefined : `This world ships no ${cat.slot} template (ai/prompts/${cat.slot}.j2)`}
      onClick={() => cat.enabled && onPick(cat.id)}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "flex", gap: 14, alignItems: "flex-start", padding: 18,
        background: h ? `${cat.color}08` : COLORS.bgCard,
        border: `1px solid ${h ? cat.color + "40" : COLORS.border}`,
        borderRadius: 10, cursor: cat.enabled ? "pointer" : "not-allowed", textAlign: "left",
        transition: "all 0.15s ease", opacity: cat.enabled ? 1 : 0.5,
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
  const { summary } = useWorldSummary();
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
            Draft rooms, entity templates and item templates for {summary?.world?.name || "this world"} with the configured model
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
        Forge uses the same model as in-game narration. Configure it under <strong>Server &amp; AI models</strong>.
      </p>
      {summary && !forgeCategories.some((c) => c.enabled) && (
        <div style={{ padding: "12px 14px", borderRadius: 8, border: `1px solid ${COLORS.warning}`, background: COLORS.warningBg, color: COLORS.text, fontSize: 13, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
          {summary.world.name} ships no Forge templates, so nothing can be generated here. A world turns Forge on with
          {" "}<code>ai/prompts/forge.room.j2</code> and <code>ai/prompts/forge.content.j2</code> in its package.
        </div>
      )}

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

    </div>
  );
};

export default AiForgePage;
