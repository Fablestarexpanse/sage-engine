import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import yaml from "js-yaml";
import { API_BASE, adminRoomTypeColors } from "./builderConstants.js";
import { useAdminTheme } from "../AdminThemeContext.jsx";

const FEATURE_INTERACTIONS = ["examine", "use", "take", "push", "pull", "read"];
const HAZARD_TYPE_SUGGESTIONS = ["environmental", "trap", "magical", "structural", "biological"];

const BLANK_FEATURE = { id: "", name: "", keywords: [], description: "", interaction: "examine" };
const BLANK_HAZARD = { id: "", type: "environmental", severity: 1, description: "" };

function roomPayloadForSave(room) {
  try {
    const out = JSON.parse(JSON.stringify(room));
    const d = out.description;
    if (d && typeof d === "object" && !Array.isArray(d)) {
      const next = { ...d };
      for (const k of ["dawn", "dusk", "night"]) {
        const v = next[k];
        if (v === "" || v == null || (typeof v === "string" && !String(v).trim())) delete next[k];
      }
      out.description = next;
    }
    return out;
  } catch {
    return room;
  }
}

const ROOM_TYPES = [
  "chamber",
  "corridor",
  "junction",
  "alcove",
  "descent",
  "danger",
  "safe",
  "boss",
  "hub",
  "command",
  "engineering",
  "airlock",
];

const EXIT_DIRS = ["north", "south", "east", "west", "up", "down"];

function normalizeTags(tags) {
  if (tags == null) return [];
  if (Array.isArray(tags)) return tags.map(String).filter(Boolean);
  if (typeof tags === "object") return Object.keys(tags);
  return [];
}

export default function RoomPropertyPanel({
  zoneId,
  mode = "zone",
  shipId,
  node,
  neighborSlugs = [],
  onSaved,
  onDeleted,
  onRevertRequest,
  onDirtyChange,
}) {
  const { colors: COLORS } = useAdminTheme();
  const ROOM_TYPE_COLORS = adminRoomTypeColors(COLORS);
  const inp = {
    width: "100%",
    padding: "8px 10px",
    background: COLORS.bgInput,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 6,
    color: COLORS.text,
    fontSize: 12,
    fontFamily: "'DM Sans', sans-serif",
    boxSizing: "border-box",
  };
  const [raw, setRaw] = useState({});
  const [rawYaml, setRawYaml] = useState("");
  const [activeTab, setActiveTab] = useState("general");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [spawnTemplates, setSpawnTemplates] = useState([]);
  const [newTag, setNewTag] = useState("");
  const [exitDraft, setExitDraft] = useState({ direction: "north", destination: "", description: "" });
  const [dirty, setDirty] = useState(false);
  const [timeVariantsOpen, setTimeVariantsOpen] = useState(false);
  const [exitPickerDir, setExitPickerDir] = useState(null);
  const [pickerZones, setPickerZones] = useState([]);
  const [pickerZoneId, setPickerZoneId] = useState("");
  const [pickerRooms, setPickerRooms] = useState([]);
  const [featureKwDraft, setFeatureKwDraft] = useState({});
  const [featureCardOpen, setFeatureCardOpen] = useState({});

  const slug = node?.data?.slug;
  const roomLocalId = node?.data?.slug;

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  const neighbors = (neighborSlugs || []).filter((s) => s && s !== slug);

  useEffect(() => {
    axios
      .get(`${API_BASE}/content/entities/spawns`)
      .then((r) => setSpawnTemplates(Array.isArray(r.data) ? r.data : []))
      .catch(() => setSpawnTemplates([]));
  }, []);

  useEffect(() => {
    setDirty(false);
    setExitPickerDir(null);
    setPickerZoneId("");
    setPickerRooms([]);
    setFeatureKwDraft({});
    setFeatureCardOpen({});
    if (!node?.data?.raw) {
      setRaw({});
      setRawYaml("");
      return;
    }
    setRaw({ ...node.data.raw });
    try {
      setRawYaml(yaml.dump(node.data.raw, { lineWidth: 120 }));
    } catch {
      setRawYaml("");
    }
    setMsg("");
  }, [node]);

  useEffect(() => {
    if (!exitPickerDir) return;
    axios
      .get(`${API_BASE}/content/zones`)
      .then((r) => setPickerZones(Array.isArray(r.data) ? r.data : []))
      .catch(() => setPickerZones([]));
  }, [exitPickerDir]);

  useEffect(() => {
    if (!exitPickerDir || !pickerZoneId) {
      setPickerRooms([]);
      return;
    }
    axios
      .get(`${API_BASE}/content/zones/${pickerZoneId}/rooms`)
      .then((r) => setPickerRooms(Array.isArray(r.data) ? r.data : []))
      .catch(() => setPickerRooms([]));
  }, [exitPickerDir, pickerZoneId]);

  const changeTab = useCallback(
    (t) => {
      if (t === "yaml" && activeTab !== "yaml") {
        try {
          setRawYaml(yaml.dump(raw, { lineWidth: 120 }));
        } catch {
          /* ignore */
        }
      }
      setActiveTab(t);
    },
    [activeTab, raw]
  );

  if (!node) {
    return (
      <div style={{ color: COLORS.textMuted, fontSize: 13, padding: 12, fontFamily: "'DM Sans', sans-serif" }}>
        Select a room node to edit.
      </div>
    );
  }

  const setField = (path, value) => {
    setDirty(true);
    setRaw((prev) => {
      const next = { ...prev };
      if (path === "description.base") {
        next.description = { ...(typeof next.description === "object" && next.description ? next.description : {}), base: value };
      } else if (path.startsWith("description.")) {
        const key = path.slice("description.".length);
        next.description = { ...(typeof next.description === "object" && next.description ? next.description : {}), [key]: value };
      } else {
        next[path] = value;
      }
      return next;
    });
  };

  const setTags = (tagsArr) => {
    setDirty(true);
    setRaw((prev) => ({ ...prev, tags: tagsArr }));
  };

  // Sent as expected_mtime so a room edited elsewhere (WorldForge, an IDE) since this
  // graph load rejects with 409 instead of being silently clobbered.
  const loadedMtime = node?.data?.mtime;
  const CONFLICT_MSG =
    "Room changed on disk since it was loaded (edited in WorldForge or another tab?). Reload the zone, then reapply your edit.";

  const saveErrMsg = (e, fallback) => {
    if (e.response?.status === 409) return CONFLICT_MSG;
    return e.response?.data?.detail || e.message || fallback;
  };

  const saveJson = async () => {
    setBusy(true);
    setMsg("");
    const payload = roomPayloadForSave(raw);
    try {
      if (mode === "ship" && shipId) {
        await axios.put(`${API_BASE}/content/ships/${shipId}/rooms/${roomLocalId}`, { room: payload });
      } else {
        await axios.put(`${API_BASE}/content/zones/${zoneId}/rooms/${slug}`, {
          room: payload,
          expected_mtime: loadedMtime ?? null,
        });
      }
      setRaw(payload);
      setDirty(false);
      setMsg("Saved ✓");
      onSaved?.();
    } catch (e) {
      setMsg(saveErrMsg(e, "Save failed"));
    } finally {
      setBusy(false);
    }
  };

  const saveYaml = async () => {
    setBusy(true);
    setMsg("");
    try {
      const parsed = yaml.load(rawYaml);
      if (typeof parsed !== "object" || !parsed) throw new Error("Invalid YAML");
      const payload = roomPayloadForSave(parsed);
      if (mode === "ship" && shipId) {
        await axios.put(`${API_BASE}/content/ships/${shipId}/rooms/${roomLocalId}`, { room: payload });
      } else {
        await axios.put(`${API_BASE}/content/zones/${zoneId}/rooms/${slug}`, {
          room: payload,
          expected_mtime: loadedMtime ?? null,
        });
      }
      setRaw(payload);
      try {
        setRawYaml(yaml.dump(payload, { lineWidth: 120 }));
      } catch {
        /* ignore */
      }
      setDirty(false);
      setMsg("Saved ✓");
      onSaved?.();
    } catch (e) {
      setMsg(saveErrMsg(e, "YAML save failed"));
    } finally {
      setBusy(false);
    }
  };

  const del = async () => {
    if (!window.confirm(`Delete room ${slug}?`)) return;
    setBusy(true);
    try {
      await axios.delete(`${API_BASE}/content/zones/${zoneId}/rooms/${slug}`);
      onDeleted?.();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const revert = async () => {
    setBusy(true);
    setMsg("");
    try {
      if (mode === "zone" && zoneId && slug) {
        const { data } = await axios.get(`${API_BASE}/content/room/${zoneId}/${slug}/yaml`);
        const text = data.yaml || "";
        const parsed = yaml.load(text);
        if (typeof parsed === "object" && parsed) {
          setRaw(parsed);
          setRawYaml(text);
          setDirty(false);
        }
        setMsg("Reverted from disk.");
      } else {
        setMsg("Reloaded from graph.");
      }
      onRevertRequest?.();
    } catch (e) {
      setMsg(e.response?.data?.detail || e.message || "Revert failed");
      onRevertRequest?.();
    } finally {
      setBusy(false);
    }
  };

  const aiDescribe = async () => {
    setBusy(true);
    setMsg("");
    try {
      const seed = `${raw.description?.base || ""} ${raw.type || "chamber"} ${slug}`.trim();
      const { data } = await axios.post(`${API_BASE}/forge/generate`, {
        seed,
        room_type: raw.type || "chamber",
        depth: Number(raw.depth) || 1,
      });
      const y = data.yaml || "";
      let parsed = null;
      try {
        parsed = yaml.load(y);
      } catch {
        parsed = data.data && typeof data.data === "object" ? data.data : null;
      }
      if (parsed && typeof parsed === "object") {
        const base = parsed.description?.base || parsed.description;
        if (typeof base === "string") {
          setDirty(true);
          setRaw((prev) => ({
            ...prev,
            description: { ...(typeof prev.description === "object" && prev.description ? prev.description : {}), base },
          }));
          setMsg("AI text merged — review and Save.");
        } else {
          setMsg("AI returned YAML; check structure.");
        }
      }
    } catch (e) {
      setMsg(e.response?.data?.detail || e.message || "Forge failed");
    } finally {
      setBusy(false);
    }
  };

  const importYaml = () => {
    try {
      const parsed = yaml.load(rawYaml);
      if (typeof parsed === "object" && parsed) {
        setDirty(true);
        setRaw(parsed);
        setMsg("Imported into form — click Save.");
      }
    } catch (e) {
      setMsg(e.message || "Parse error");
    }
  };

  const exitsObj = raw.exits && typeof raw.exits === "object" ? raw.exits : {};
  const tags = normalizeTags(raw.tags);
  const freeDirs = EXIT_DIRS.filter((d) => !exitsObj[d]);
  const featuresList = Array.isArray(raw.features) ? raw.features : [];
  const hazardsList = Array.isArray(raw.hazards) ? raw.hazards : [];

  const addFeature = () => {
    setDirty(true);
    setRaw((prev) => ({
      ...prev,
      features: [...(Array.isArray(prev.features) ? prev.features : []), { ...BLANK_FEATURE }],
    }));
  };
  const removeFeature = (index) => {
    setDirty(true);
    setRaw((prev) => {
      const list = [...(Array.isArray(prev.features) ? prev.features : [])];
      list.splice(index, 1);
      return { ...prev, features: list };
    });
  };
  const patchFeature = (index, patch) => {
    setDirty(true);
    setRaw((prev) => {
      const list = [...(Array.isArray(prev.features) ? prev.features : [])];
      const cur = list[index];
      if (!cur || typeof cur !== "object") return prev;
      list[index] = { ...cur, ...patch };
      return { ...prev, features: list };
    });
  };
  const setFeatureKeywords = (index, keywords) => {
    setDirty(true);
    setRaw((prev) => {
      const list = [...(Array.isArray(prev.features) ? prev.features : [])];
      const cur = list[index];
      if (!cur || typeof cur !== "object") return prev;
      list[index] = { ...cur, keywords: Array.isArray(keywords) ? keywords : [] };
      return { ...prev, features: list };
    });
  };

  const addHazard = () => {
    setDirty(true);
    setRaw((prev) => ({
      ...prev,
      hazards: [...(Array.isArray(prev.hazards) ? prev.hazards : []), { ...BLANK_HAZARD }],
    }));
  };
  const removeHazard = (index) => {
    setDirty(true);
    setRaw((prev) => {
      const list = [...(Array.isArray(prev.hazards) ? prev.hazards : [])];
      list.splice(index, 1);
      return { ...prev, hazards: list };
    });
  };
  const patchHazard = (index, patch) => {
    setDirty(true);
    setRaw((prev) => {
      const list = [...(Array.isArray(prev.hazards) ? prev.hazards : [])];
      const cur = list[index];
      if (!cur || typeof cur !== "object") return prev;
      list[index] = { ...cur, ...patch };
      return { ...prev, hazards: list };
    });
  };

  const formatZoneDestination = (targetSlug) => {
    if (!targetSlug) return "";
    if (mode === "ship") {
      if (targetSlug.startsWith("self:") || targetSlug.startsWith("@")) return targetSlug;
      return `self:${targetSlug}`;
    }
    if (targetSlug.includes(":")) return targetSlug;
    return `${zoneId}:${targetSlug}`;
  };

  const addExit = () => {
    const dir = freeDirs.includes(exitDraft.direction) ? exitDraft.direction : freeDirs[0];
    if (!dir || exitsObj[dir]) {
      setMsg("Pick a free direction.");
      return;
    }
    const dest = formatZoneDestination(exitDraft.destination.trim());
    if (!dest) {
      setMsg("Destination required.");
      return;
    }
    setDirty(true);
    setRaw((prev) => ({
      ...prev,
      exits: {
        ...(prev.exits && typeof prev.exits === "object" ? prev.exits : {}),
        [dir]: { destination: dest, description: exitDraft.description || "" },
      },
    }));
    setExitDraft((d) => ({ ...d, destination: "", description: "" }));
    setMsg("Exit added locally — Save to persist.");
  };

  const removeExit = (dir) => {
    setDirty(true);
    setRaw((prev) => {
      const next = { ...prev };
      const ex = { ...(next.exits || {}) };
      delete ex[dir];
      next.exits = ex;
      return next;
    });
  };

  const updateExitDescription = (dir, description) => {
    setDirty(true);
    setRaw((prev) => {
      const ex = { ...(prev.exits || {}) };
      if (ex[dir]) ex[dir] = { ...ex[dir], description };
      return { ...prev, exits: ex };
    });
  };

  const updateExitDestination = (dir, destination) => {
    setDirty(true);
    setRaw((prev) => {
      const ex = { ...(prev.exits || {}) };
      if (ex[dir]) ex[dir] = { ...ex[dir], destination };
      return { ...prev, exits: ex };
    });
  };

  const addSpawn = () => {
    setDirty(true);
    setRaw((prev) => ({
      ...prev,
      entity_spawns: [...(Array.isArray(prev.entity_spawns) ? prev.entity_spawns : []), { template: "", chance: 1, max_count: 1 }],
    }));
    setMsg("Spawn added — pick template and Save.");
  };

  const removeSpawn = (index) => {
    setDirty(true);
    setRaw((prev) => {
      const list = [...(Array.isArray(prev.entity_spawns) ? prev.entity_spawns : [])];
      list.splice(index, 1);
      return { ...prev, entity_spawns: list };
    });
  };

  const updateSpawn = (index, patch) => {
    setDirty(true);
    setRaw((prev) => {
      const list = [...(Array.isArray(prev.entity_spawns) ? prev.entity_spawns : [])];
      const cur = list[index];
      if (!cur || typeof cur !== "object") return prev;
      list[index] = { ...cur, ...patch };
      return { ...prev, entity_spawns: list };
    });
  };

  const addTag = () => {
    const t = newTag.trim();
    if (!t || tags.includes(t)) return;
    setTags([...tags, t]);
    setNewTag("");
  };

  const removeTag = (t) => {
    setTags(tags.filter((x) => x !== t));
  };

  const descBase = raw.description?.base ?? "";
  const descDawn = typeof raw.description === "object" && raw.description ? raw.description.dawn ?? "" : "";
  const descDusk = typeof raw.description === "object" && raw.description ? raw.description.dusk ?? "" : "";
  const descNight = typeof raw.description === "object" && raw.description ? raw.description.night ?? "" : "";
  const roomName = raw.name ?? "";

  const tabBtn = (id, label) => (
    <button
      key={id}
      type="button"
      onClick={() => changeTab(id)}
      style={{
        flex: 1,
        padding: "8px 4px",
        background: "none",
        border: "none",
        borderBottom: activeTab === id ? `2px solid ${COLORS.accent}` : "2px solid transparent",
        color: activeTab === id ? COLORS.text : COLORS.textMuted,
        fontSize: 10,
        fontFamily: "'DM Sans', sans-serif",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        cursor: "pointer",
        fontWeight: activeTab === id ? 600 : 400,
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", maxHeight: "72vh", overflow: "hidden", fontFamily: "'DM Sans', sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, paddingBottom: 8, borderBottom: `1px solid ${COLORS.border}` }}>
        <div style={{ width: 3, height: 24, borderRadius: 2, background: ROOM_TYPE_COLORS[raw.type] || COLORS.accent }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, color: COLORS.text, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {node.data?.label || slug}
            </div>
            {dirty && (
              <span
                style={{
                  fontSize: 9,
                  fontWeight: 600,
                  color: COLORS.warning,
                  background: `${COLORS.warning}22`,
                  border: `1px solid ${COLORS.warning}55`,
                  padding: "2px 6px",
                  borderRadius: 4,
                  fontFamily: "'JetBrains Mono', monospace",
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                }}
              >
                Unsaved changes
              </span>
            )}
          </div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: COLORS.textMuted }}>
            {mode === "ship" ? `${shipId}:${slug}` : `${zoneId}:${slug}`}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", borderBottom: `1px solid ${COLORS.border}` }}>
        {tabBtn("general", "General")}
        {tabBtn("exits", "Exits")}
        {tabBtn("entities", "Entities")}
        {tabBtn("features", "Features")}
        {tabBtn("hazards", "Hazards")}
        {tabBtn("yaml", "YAML")}
      </div>

      {msg && (
        <div style={{ fontSize: 10, color: msg.includes("✓") ? COLORS.success : COLORS.warning, fontFamily: "'JetBrains Mono', monospace", padding: "6px 0" }}>{msg}</div>
      )}

      <div style={{ flex: 1, overflow: "auto", paddingTop: 10 }}>
        {activeTab === "general" && (
          <>
            <label style={{ fontSize: 10, color: COLORS.textMuted }}>Display name</label>
            <input type="text" value={roomName} onChange={(e) => setField("name", e.target.value)} style={{ ...inp, marginBottom: 10 }} placeholder="Room title" />

            <label style={{ fontSize: 10, color: COLORS.textMuted }}>Type</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 10 }}>
              {ROOM_TYPES.map((t) => {
                const c = ROOM_TYPE_COLORS[t] || COLORS.textMuted;
                const on = (raw.type || "chamber") === t;
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setField("type", t)}
                    style={{
                      padding: "4px 8px",
                      borderRadius: 4,
                      fontSize: 10,
                      fontFamily: "'JetBrains Mono', monospace",
                      border: `1px solid ${on ? c : COLORS.border}`,
                      background: on ? `${c}22` : "transparent",
                      color: on ? c : COLORS.textMuted,
                      cursor: "pointer",
                    }}
                  >
                    {t}
                  </button>
                );
              })}
            </div>

            <label style={{ fontSize: 10, color: COLORS.textMuted }}>Depth</label>
            <input type="number" value={raw.depth ?? 1} onChange={(e) => setField("depth", Number(e.target.value))} style={{ ...inp, marginBottom: 10 }} />

            <label style={{ fontSize: 10, color: COLORS.textMuted }}>Description</label>
            <textarea
              value={descBase}
              onChange={(e) => setField("description.base", e.target.value)}
              rows={5}
              style={{ ...inp, resize: "vertical", marginBottom: 6 }}
            />
            <button
              type="button"
              disabled={busy}
              onClick={aiDescribe}
              style={{
                padding: "6px 10px",
                background: COLORS.forge,
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontWeight: 600,
                cursor: "pointer",
                fontSize: 11,
                marginBottom: 10,
              }}
            >
              AI Generate description
            </button>

            <button
              type="button"
              onClick={() => setTimeVariantsOpen((o) => !o)}
              style={{
                width: "100%",
                textAlign: "left",
                padding: "8px 10px",
                marginBottom: timeVariantsOpen ? 8 : 10,
                background: COLORS.bgPanel,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 6,
                color: COLORS.textMuted,
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: "'DM Sans', sans-serif",
              }}
            >
              Time-of-day variants (optional) {timeVariantsOpen ? "▾" : "▸"}
            </button>
            {timeVariantsOpen && (
              <>
                <label style={{ fontSize: 10, color: COLORS.textMuted }}>Dawn</label>
                <textarea
                  value={descDawn}
                  onChange={(e) => setField("description.dawn", e.target.value)}
                  rows={4}
                  style={{ ...inp, resize: "vertical", marginBottom: 8 }}
                />
                <label style={{ fontSize: 10, color: COLORS.textMuted }}>Dusk</label>
                <textarea
                  value={descDusk}
                  onChange={(e) => setField("description.dusk", e.target.value)}
                  rows={4}
                  style={{ ...inp, resize: "vertical", marginBottom: 8 }}
                />
                <label style={{ fontSize: 10, color: COLORS.textMuted }}>Night</label>
                <textarea
                  value={descNight}
                  onChange={(e) => setField("description.night", e.target.value)}
                  rows={4}
                  style={{ ...inp, resize: "vertical", marginBottom: 10 }}
                />
              </>
            )}

            <label style={{ fontSize: 10, color: COLORS.textMuted }}>Tags</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginBottom: 10 }}>
              {tags.map((t) => (
                <span
                  key={t}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                    padding: "2px 8px",
                    borderRadius: 4,
                    fontSize: 10,
                    fontWeight: 600,
                    color: COLORS.success,
                    background: `${COLORS.success}18`,
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  {t}
                  <button type="button" onClick={() => removeTag(t)} style={{ background: "none", border: "none", color: COLORS.textMuted, cursor: "pointer", padding: 0, fontSize: 12 }}>
                    ×
                  </button>
                </span>
              ))}
              <input
                type="text"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTag())}
                placeholder="tag"
                style={{ ...inp, maxWidth: 100, padding: "4px 8px", fontSize: 11 }}
              />
              <button type="button" onClick={addTag} style={{ padding: "4px 8px", background: COLORS.bgHover, border: `1px dashed ${COLORS.border}`, borderRadius: 4, color: COLORS.textDim, cursor: "pointer", fontSize: 11 }}>
                + tag
              </button>
            </div>
          </>
        )}

        {activeTab === "exits" && (
          <>
            {Object.entries(exitsObj).map(([dir, ex]) => {
              const dest = typeof ex === "object" && ex ? ex.destination || "" : "";
              const dsc = typeof ex === "object" && ex ? ex.description || "" : "";
              return (
                <div key={dir} style={{ padding: 8, background: COLORS.bgPanel, border: `1px solid ${COLORS.border}`, borderRadius: 8, marginBottom: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: COLORS.accent, fontFamily: "'JetBrains Mono', monospace" }}>{dir}</span>
                    <button type="button" onClick={() => removeExit(dir)} style={{ background: "none", border: "none", color: COLORS.danger, cursor: "pointer", fontSize: 11 }}>
                      Remove
                    </button>
                  </div>
                  <label style={{ fontSize: 9, color: COLORS.textDim }}>Destination</label>
                  <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
                    <input type="text" value={dest} onChange={(e) => updateExitDestination(dir, e.target.value)} style={{ ...inp, flex: 1, marginBottom: 0 }} />
                    <button
                      type="button"
                      onClick={() => {
                        setExitPickerDir(exitPickerDir === dir ? null : dir);
                        setPickerZoneId(zoneId);
                      }}
                      style={{
                        flexShrink: 0,
                        padding: "6px 8px",
                        fontSize: 10,
                        background: COLORS.bgHover,
                        border: `1px solid ${COLORS.border}`,
                        borderRadius: 6,
                        color: COLORS.accent,
                        cursor: "pointer",
                        fontWeight: 600,
                      }}
                    >
                      Pick room…
                    </button>
                  </div>
                  {exitPickerDir === dir && (
                    <div
                      style={{
                        padding: 8,
                        marginBottom: 8,
                        background: COLORS.bgInput,
                        border: `1px dashed ${COLORS.borderActive}`,
                        borderRadius: 6,
                      }}
                    >
                      <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 6 }}>Cross-zone destination</div>
                      <select
                        value={pickerZoneId}
                        onChange={(e) => setPickerZoneId(e.target.value)}
                        style={{ ...inp, marginBottom: 6 }}
                      >
                        <option value="">Select zone…</option>
                        {pickerZones.map((z) => (
                          <option key={z.id} value={z.id}>
                            {z.name || z.id}
                          </option>
                        ))}
                      </select>
                      {pickerZoneId && (
                        <div style={{ maxHeight: 140, overflow: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
                          {pickerRooms.map((r) => {
                            const rs = r.name || (r.id && String(r.id).includes(":") ? String(r.id).split(":").pop() : r.id) || "?";
                            return (
                              <button
                                key={r.id || rs}
                                type="button"
                                onClick={() => {
                                  const slugPart = r.name || (String(r.id || "").includes(":") ? String(r.id).split(":").pop() : rs);
                                  updateExitDestination(dir, `${pickerZoneId}:${slugPart}`);
                                  setExitPickerDir(null);
                                }}
                                style={{
                                  textAlign: "left",
                                  padding: "6px 8px",
                                  fontSize: 11,
                                  background: COLORS.bgPanel,
                                  border: `1px solid ${COLORS.border}`,
                                  borderRadius: 4,
                                  color: COLORS.text,
                                  cursor: "pointer",
                                }}
                              >
                                {rs}
                              </button>
                            );
                          })}
                          {pickerRooms.length === 0 && <div style={{ fontSize: 10, color: COLORS.textDim }}>No rooms in this zone.</div>}
                        </div>
                      )}
                    </div>
                  )}
                  <label style={{ fontSize: 9, color: COLORS.textDim }}>Description</label>
                  <input type="text" value={dsc} onChange={(e) => updateExitDescription(dir, e.target.value)} style={inp} />
                </div>
              );
            })}

            <div style={{ padding: 8, border: `1px dashed ${COLORS.border}`, borderRadius: 8, marginTop: 4 }}>
              <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 6 }}>+ Add exit</div>
              {freeDirs.length === 0 ? (
                <div style={{ fontSize: 11, color: COLORS.textDim }}>All directions in use — remove one to add.</div>
              ) : (
              <select value={freeDirs.includes(exitDraft.direction) ? exitDraft.direction : freeDirs[0]} onChange={(e) => setExitDraft((d) => ({ ...d, direction: e.target.value }))} style={{ ...inp, marginBottom: 6 }}>
                {freeDirs.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              )}
              {freeDirs.length > 0 && neighbors.length > 0 && (
                <select
                  value=""
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v) setExitDraft((d) => ({ ...d, destination: v }));
                    e.target.value = "";
                  }}
                  style={{ ...inp, marginBottom: 6 }}
                >
                  <option value="">Link to room…</option>
                  {neighbors.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              )}
              <input
                type="text"
                placeholder={mode === "ship" ? "Destination (self:room or @special)" : "Destination (slug or zone:slug)"}
                value={exitDraft.destination}
                onChange={(e) => setExitDraft((d) => ({ ...d, destination: e.target.value }))}
                style={{ ...inp, marginBottom: 6 }}
              />
              <input type="text" placeholder="Exit description" value={exitDraft.description} onChange={(e) => setExitDraft((d) => ({ ...d, description: e.target.value }))} style={{ ...inp, marginBottom: 6 }} />
              {freeDirs.length > 0 && (
              <button type="button" onClick={addExit} style={{ width: "100%", padding: 8, background: COLORS.accentGlow, border: `1px solid ${COLORS.borderActive}`, borderRadius: 6, color: COLORS.accent, cursor: "pointer", fontSize: 11, fontWeight: 600 }}>
                Add exit
              </button>
              )}
            </div>
          </>
        )}

        {activeTab === "features" && (
          <>
            {featuresList.map((feat, fi) => {
              const o = typeof feat === "object" && feat ? feat : { ...BLANK_FEATURE };
              const kws = Array.isArray(o.keywords) ? o.keywords.map(String).filter(Boolean) : [];
              const open = featureCardOpen[fi] !== false;
              return (
                <div key={fi} style={{ marginBottom: 8, border: `1px solid ${COLORS.border}`, borderRadius: 8, overflow: "hidden" }}>
                  <button
                    type="button"
                    onClick={() => setFeatureCardOpen((p) => ({ ...p, [fi]: !(p[fi] ?? true) }))}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "8px 10px",
                      background: COLORS.bgPanel,
                      border: "none",
                      color: COLORS.textMuted,
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: "pointer",
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    {open ? "▾" : "▸"} Feature {fi + 1}{o.id ? ` · ${o.id}` : ""}
                  </button>
                  {open && (
                    <div style={{ padding: 10, background: COLORS.bgCard }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                        <span style={{ fontSize: 10, color: COLORS.textDim }}>id (slug)</span>
                        <button type="button" onClick={() => removeFeature(fi)} style={{ background: "none", border: "none", color: COLORS.danger, cursor: "pointer", fontSize: 11 }}>
                          Remove
                        </button>
                      </div>
                      <input
                        type="text"
                        value={o.id || ""}
                        onChange={(e) => patchFeature(fi, { id: e.target.value })}
                        placeholder="feature_slug"
                        style={{ ...inp, marginBottom: 8 }}
                      />
                      <label style={{ fontSize: 9, color: COLORS.textDim }}>Name</label>
                      <input type="text" value={o.name || ""} onChange={(e) => patchFeature(fi, { name: e.target.value })} style={{ ...inp, marginBottom: 8 }} />
                      <label style={{ fontSize: 9, color: COLORS.textDim }}>Keywords</label>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginBottom: 8 }}>
                        {kws.map((kw) => (
                          <span
                            key={kw}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                              padding: "2px 8px",
                              borderRadius: 4,
                              fontSize: 10,
                              color: COLORS.info,
                              background: `${COLORS.info}18`,
                              fontFamily: "'JetBrains Mono', monospace",
                            }}
                          >
                            {kw}
                            <button
                              type="button"
                              onClick={() => patchFeature(fi, { keywords: kws.filter((x) => x !== kw) })}
                              style={{ background: "none", border: "none", color: COLORS.textMuted, cursor: "pointer", padding: 0, fontSize: 12 }}
                            >
                              ×
                            </button>
                          </span>
                        ))}
                        <input
                          type="text"
                          value={featureKwDraft[fi] || ""}
                          onChange={(e) => setFeatureKwDraft((d) => ({ ...d, [fi]: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key !== "Enter") return;
                            e.preventDefault();
                            const t = (featureKwDraft[fi] || "").trim();
                            if (!t || kws.includes(t)) return;
                            patchFeature(fi, { keywords: [...kws, t] });
                            setFeatureKwDraft((d) => ({ ...d, [fi]: "" }));
                          }}
                          placeholder="keyword + Enter"
                          style={{ ...inp, maxWidth: 120, padding: "4px 8px", fontSize: 11 }}
                        />
                      </div>
                      <label style={{ fontSize: 9, color: COLORS.textDim }}>Description</label>
                      <textarea
                        value={o.description || ""}
                        onChange={(e) => patchFeature(fi, { description: e.target.value })}
                        rows={4}
                        style={{ ...inp, resize: "vertical", marginBottom: 8 }}
                      />
                      <label style={{ fontSize: 9, color: COLORS.textDim }}>Interaction</label>
                      <select
                        value={o.interaction || "examine"}
                        onChange={(e) => patchFeature(fi, { interaction: e.target.value })}
                        style={{ ...inp, marginBottom: 0 }}
                      >
                        {FEATURE_INTERACTIONS.map((x) => (
                          <option key={x} value={x}>
                            {x}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              );
            })}
            <button
              type="button"
              onClick={addFeature}
              style={{
                width: "100%",
                padding: 10,
                background: "transparent",
                border: `1px dashed ${COLORS.border}`,
                borderRadius: 8,
                color: COLORS.textMuted,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              + Add feature
            </button>
          </>
        )}

        {activeTab === "hazards" && (
          <>
            <datalist id="hazard-type-dl">
              {HAZARD_TYPE_SUGGESTIONS.map((x) => (
                <option key={x} value={x} />
              ))}
            </datalist>
            {hazardsList.map((hz, hi) => {
              const o = typeof hz === "object" && hz ? hz : { ...BLANK_HAZARD };
              return (
                <div key={hi} style={{ padding: 10, background: COLORS.bgPanel, border: `1px solid ${COLORS.border}`, borderRadius: 8, marginBottom: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                    <span style={{ fontSize: 10, color: COLORS.textMuted }}>Hazard {hi + 1}</span>
                    <button type="button" onClick={() => removeHazard(hi)} style={{ background: "none", border: "none", color: COLORS.danger, cursor: "pointer", fontSize: 11 }}>
                      Remove
                    </button>
                  </div>
                  <label style={{ fontSize: 9, color: COLORS.textDim }}>ID</label>
                  <input type="text" value={o.id || ""} onChange={(e) => patchHazard(hi, { id: e.target.value })} style={{ ...inp, marginBottom: 8 }} />
                  <label style={{ fontSize: 9, color: COLORS.textDim }}>Type</label>
                  <input
                    type="text"
                    list="hazard-type-dl"
                    value={o.type || ""}
                    onChange={(e) => patchHazard(hi, { type: e.target.value })}
                    style={{ ...inp, marginBottom: 8 }}
                  />
                  <label style={{ fontSize: 9, color: COLORS.textDim }}>Severity (1–5)</label>
                  <input
                    type="number"
                    min={1}
                    max={5}
                    value={o.severity ?? 1}
                    onChange={(e) => patchHazard(hi, { severity: Math.min(5, Math.max(1, parseInt(e.target.value, 10) || 1)) })}
                    style={{ ...inp, marginBottom: 8 }}
                  />
                  <label style={{ fontSize: 9, color: COLORS.textDim }}>Description</label>
                  <textarea
                    value={o.description || ""}
                    onChange={(e) => patchHazard(hi, { description: e.target.value })}
                    rows={3}
                    style={{ ...inp, resize: "vertical", marginBottom: 0 }}
                  />
                </div>
              );
            })}
            <button
              type="button"
              onClick={addHazard}
              style={{
                width: "100%",
                padding: 10,
                background: "transparent",
                border: `1px dashed ${COLORS.border}`,
                borderRadius: 8,
                color: COLORS.textMuted,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              + Add hazard
            </button>
          </>
        )}

        {activeTab === "entities" && (
          <>
            {(Array.isArray(raw.entity_spawns) ? raw.entity_spawns : []).map((sp, index) => {
              const o = typeof sp === "object" && sp ? sp : { template: String(sp), chance: 1, max_count: 1 };
              return (
                <div key={index} style={{ padding: 8, background: COLORS.bgPanel, border: `1px solid ${COLORS.border}`, borderRadius: 8, marginBottom: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ fontSize: 10, color: COLORS.textMuted }}>Spawn {index + 1}</span>
                    <button type="button" onClick={() => removeSpawn(index)} style={{ background: "none", border: "none", color: COLORS.danger, cursor: "pointer", fontSize: 11 }}>
                      Remove
                    </button>
                  </div>
                  <label style={{ fontSize: 9, color: COLORS.textDim }}>Template</label>
                  <input
                    type="text"
                    list={`spawn-tpl-${index}`}
                    value={o.template || ""}
                    onChange={(e) => updateSpawn(index, { template: e.target.value })}
                    placeholder="Template id"
                    style={{ ...inp, marginBottom: 6 }}
                  />
                  <datalist id={`spawn-tpl-${index}`}>
                    {spawnTemplates.map((row) => (
                      <option key={row.id || row.name} value={row.name} />
                    ))}
                  </datalist>
                  <label style={{ fontSize: 9, color: COLORS.textDim }}>Chance (0–1)</label>
                  <input
                    type="number"
                    step="0.05"
                    min={0}
                    max={1}
                    value={o.chance ?? 1}
                    onChange={(e) => updateSpawn(index, { chance: Math.min(1, Math.max(0, Number(e.target.value))) })}
                    style={{ ...inp, marginBottom: 6 }}
                  />
                  <label style={{ fontSize: 9, color: COLORS.textDim }}>Max count</label>
                  <input
                    type="number"
                    min={1}
                    value={o.max_count ?? 1}
                    onChange={(e) => updateSpawn(index, { max_count: Math.max(1, parseInt(e.target.value, 10) || 1) })}
                    style={inp}
                  />
                </div>
              );
            })}
            <button
              type="button"
              onClick={addSpawn}
              style={{
                width: "100%",
                padding: 10,
                background: "transparent",
                border: `1px dashed ${COLORS.border}`,
                borderRadius: 8,
                color: COLORS.textMuted,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              + Add entity spawn
            </button>
          </>
        )}

        {activeTab === "yaml" && (
          <>
            <textarea
              value={rawYaml}
              onChange={(e) => {
                setDirty(true);
                setRawYaml(e.target.value);
              }}
              rows={14}
              style={{ ...inp, fontFamily: "'JetBrains Mono', monospace", fontSize: 10 }}
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              <button type="button" onClick={importYaml} style={{ padding: "6px 10px", background: COLORS.bgHover, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, cursor: "pointer", fontSize: 11 }}>
                Parse into form
              </button>
              <button type="button" disabled={busy} onClick={saveYaml} style={{ padding: "6px 10px", background: COLORS.accent, border: "none", borderRadius: 6, color: "#fff", cursor: "pointer", fontSize: 11 }}>
                Save YAML
              </button>
            </div>
          </>
        )}
      </div>

      {/* Undo/redo for the whole builder is deferred; single-room edit history could stack here later. */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingTop: 10, borderTop: `1px solid ${COLORS.border}`, marginTop: 8 }}>
        <button type="button" disabled={busy} onClick={saveJson} style={{ padding: "8px 12px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer", fontSize: 12 }}>
          {dirty ? "Save *" : "Save"}
        </button>
        <button type="button" disabled={busy} onClick={revert} style={{ padding: "8px 12px", background: COLORS.bgHover, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, cursor: "pointer", fontSize: 12 }}>
          Revert
        </button>
        {mode === "zone" && (
          <button type="button" disabled={busy} onClick={del} style={{ padding: "8px 12px", background: COLORS.danger, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer", fontSize: 12 }}>
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
