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


// ═══════════════════════════════════════════════════════════
// CONTENT LIBRARY — one browsing surface for zones, rooms, entities, items,
// and glyphs (replaces the former World & Zones / Locations / Entities /
// Items / Glyphs pages, which were overlapping read-only shells).
// ═══════════════════════════════════════════════════════════

const openBuilderAt = (zoneId, zoneLabel) => {
  window.dispatchEvent(
    new CustomEvent("fs-admin-nav", { detail: { page: "builder", zoneId, zoneLabel } })
  );
};

const openForgeStudio = () => {
  window.dispatchEvent(new CustomEvent("fs-admin-nav", { detail: { page: "forge" } }));
};

const ZonesLibTab = () => {
  const { colors: COLORS } = useAdminTheme();
  const [filter, setFilter] = useState("all");
  const { rows: zones, error: zonesError } = usePolledList(`${API_BASE}/content/zones`, 10000);
  const typeColors = { tutorial: COLORS.success, exploration: COLORS.info, dungeon: COLORS.accent, boss: COLORS.danger, safe: COLORS.warning };
  const filtered = zones.filter((z) => filter === "all" || z.status === filter);

  const createZone = async () => {
    const zid = window.prompt("New zone id (e.g. crystal_depths):", "");
    if (!zid || !/^[a-zA-Z0-9_-]+$/.test(zid)) return;
    const name = window.prompt("Display name:", zid) || zid;
    try {
      await axios.post(`${API_BASE}/content/zones`, { id: zid, name });
      openBuilderAt(zid, name);
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <TabBar tabs={[{ id: "all", label: "All" }, { id: "active", label: "Active" }, { id: "building", label: "Building" }]} active={filter} onChange={setFilter} />
        <ActionButton variant="primary" icon={<Icons.Plus />} onClick={createZone}>New Zone</ActionButton>
      </div>
      <FetchErrorBanner error={zonesError} label="zones" />
      {filtered.length === 0 && !zonesError && <div style={{ color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>No zones found under content/world/zones.</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
        {filtered.map((zone) => (
          <div key={zone.id} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12, cursor: "pointer" }}
            onClick={() => openBuilderAt(zone.id, zone.name)}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = COLORS.borderActive; }} onMouseLeave={(e) => { e.currentTarget.style.borderColor = COLORS.border; }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{zone.name}</div>
                <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 2 }}>{zone.id} · depth {zone.depth}</div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <Badge color={typeColors[zone.type] || COLORS.textMuted}>{zone.type}</Badge>
                <Badge color={zone.status === "active" ? COLORS.success : zone.status === "building" ? COLORS.warning : COLORS.danger}>{zone.status}</Badge>
              </div>
            </div>
            <div style={{ display: "flex", gap: 16 }}>
              {[{ label: "Rooms", value: zone.rooms }, { label: "Entities", value: zone.entities }, { label: "Players", value: zone.players }].map((st) => (
                <div key={st.label}><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{st.value}</div><div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{st.label}</div></div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
              <ActionButton small variant="primary" icon={<Icons.Map />} onClick={(e) => { e.stopPropagation(); openBuilderAt(zone.id, zone.name); }}>Open in Builder</ActionButton>
              <ActionButton small variant="forge" icon={<Icons.Sparkles />} onClick={(e) => { e.stopPropagation(); openForgeStudio(); }}>AI Forge</ActionButton>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const RoomsLibTab = () => {
  const { colors: COLORS } = useAdminTheme();
  const [selectedZone, setSelectedZone] = useState("");
  const { rows: zones, error: zonesError } = usePolledList(`${API_BASE}/content/zones`, 12000);
  const { rows: roomRows, error: roomsError } = usePolledList(
    selectedZone ? `${API_BASE}/content/zones/${selectedZone}/rooms` : null,
    10000,
    { enabled: !!selectedZone }
  );
  useEffect(() => {
    if (zones.length && !selectedZone) setSelectedZone(zones[0].id);
  }, [zones, selectedZone]);
  const zone = zones.find((z) => z.id === selectedZone);

  const addRoom = async () => {
    if (!selectedZone) return;
    const slug = window.prompt("New room slug (e.g. alcove_02):", "");
    if (!slug || !/^[a-zA-Z0-9_-]+$/.test(slug)) return;
    try {
      await axios.post(`${API_BASE}/content/zones/${selectedZone}/rooms`, { slug, room: {} });
      openBuilderAt(selectedZone, zone?.name);
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <select value={selectedZone} onChange={(e) => setSelectedZone(e.target.value)} style={{ padding: "8px 12px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 8, color: COLORS.text, fontSize: 13, fontFamily: "'DM Sans', sans-serif" }}>
          {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
        </select>
        <ActionButton variant="primary" icon={<Icons.Plus />} onClick={addRoom}>Add Room</ActionButton>
        <ActionButton variant="primary" icon={<Icons.Map />} onClick={() => openBuilderAt(selectedZone, zone?.name)}>Open in World Builder</ActionButton>
      </div>
      <FetchErrorBanner error={zonesError} label="zones" />
      <FetchErrorBanner error={roomsError} label="rooms" />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{zone?.name || "—"}</div>
          <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 2 }}>{zone?.id} · {zone?.rooms ?? roomRows.length} rooms · depth {zone?.depth ?? "—"}</div>
        </div>
        <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif" }}>
          Bulk AI descriptions live in World Builder → open a zone → “AI Describe All”.
        </div>
      </div>
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable columns={[
          { label: "Room", render: (row) => (<div><div style={{ fontWeight: 600, fontSize: 13 }}>{row.name}</div><div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{row.id}</div></div>) },
          { label: "Type", render: (row) => <Badge>{row.type}</Badge> },
          { label: "Exits", render: (row) => (<div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>{(row.exits || []).map((e) => (<span key={e} style={{ width: 22, height: 22, borderRadius: 4, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 600, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>{e}</span>))}</div>) },
          { label: "Entities", key: "entities", mono: true },
          { label: "Hazards", render: (row) => <span style={{ color: row.hazards > 0 ? COLORS.danger : COLORS.textDim }}>{row.hazards}</span> },
          { label: "", render: () => (<ActionButton small variant="ghost" icon={<Icons.Map />} onClick={() => openBuilderAt(selectedZone, zone?.name)}>Edit</ActionButton>) },
        ]} rows={roomRows} />
      </div>
    </div>
  );
};

const EntitiesLibTab = () => {
  const { colors: COLORS } = useAdminTheme();
  const [search, setSearch] = useState("");
  const { rows, error: rowsError } = usePolledList(`${API_BASE}/content/entities/spawns`, 12000);
  const { rows: liveEntities, error: liveError } = usePolledList(`${API_BASE}/world/entities`, 8000);
  const { rows: zones } = usePolledList(`${API_BASE}/content/zones`, 30000);
  const [spawnZone, setSpawnZone] = useState("");
  const { rows: spawnRooms } = usePolledList(
    spawnZone ? `${API_BASE}/content/zones/${spawnZone}/rooms` : null,
    30000,
    { enabled: !!spawnZone }
  );
  const [spawnRoom, setSpawnRoom] = useState("");
  const [spawnTemplate, setSpawnTemplate] = useState("");
  const [spawnMsg, setSpawnMsg] = useState("");
  const typeColors = { Hunter: COLORS.danger, Guide: COLORS.success, Watcher: COLORS.info, Boss: COLORS.warning, Vendor: COLORS.accent, spawn: COLORS.accent };
  const filtered = rows.filter((e) => String(e.name).toLowerCase().includes(search.toLowerCase()));

  const doSpawn = async () => {
    if (!spawnZone || !spawnRoom || !spawnTemplate) {
      setSpawnMsg("Pick a zone, room, and template first.");
      return;
    }
    setSpawnMsg("");
    try {
      const { data } = await axios.post(`${API_BASE}/world/rooms/${spawnZone}/${spawnRoom}/spawn`, { template: spawnTemplate });
      setSpawnMsg(`Spawned ${data.entity_id} ✓`);
    } catch (e) {
      setSpawnMsg(e.response?.data?.detail || e.message);
    }
  };

  const doDespawn = async (ent) => {
    if (!window.confirm(`Despawn ${ent.name || ent.id}?`)) return;
    try {
      await axios.delete(`${API_BASE}/world/entities/${ent.id}`);
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <SearchBar placeholder="Search spawn templates..." value={search} onChange={setSearch} />
        <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={openForgeStudio}>AI Generate</ActionButton>
      </div>
      <p style={{ margin: 0, fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>Rows aggregate <code style={{ color: COLORS.textDim }}>entity_spawns</code> entries from all room YAML files.</p>
      <FetchErrorBanner error={rowsError} label="entity spawns" />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable columns={[
          { label: "Template", render: (row) => <span style={{ fontWeight: 600 }}>{row.name}</span> },
          { label: "Kind", render: (row) => <Badge color={typeColors[row.type] || COLORS.textMuted}>{row.type}</Badge> },
          { label: "Zone ref", key: "zone" }, { label: "Level", key: "level", mono: true },
          { label: "Behavior", render: (row) => <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: COLORS.textMuted }}>{row.behavior}</span> },
          { label: "Spawn refs", key: "count", mono: true },
          { label: "Status", render: (row) => <Badge color={row.status === "active" ? COLORS.success : COLORS.textDim}>{row.status}</Badge> },
        ]} rows={filtered} />
      </div>

      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Live entities</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select value={spawnZone} onChange={(e) => { setSpawnZone(e.target.value); setSpawnRoom(""); }} style={{ padding: "6px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 12 }}>
              <option value="">zone…</option>
              {zones.map((z) => <option key={z.id} value={z.id}>{z.id}</option>)}
            </select>
            <select value={spawnRoom} onChange={(e) => setSpawnRoom(e.target.value)} style={{ padding: "6px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 12 }}>
              <option value="">room…</option>
              {spawnRooms.map((r) => <option key={r.id} value={r.name}>{r.name}</option>)}
            </select>
            <select value={spawnTemplate} onChange={(e) => setSpawnTemplate(e.target.value)} style={{ padding: "6px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 12 }}>
              <option value="">template…</option>
              {rows.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
            </select>
            <ActionButton small variant="primary" icon={<Icons.Plus />} onClick={doSpawn}>Spawn</ActionButton>
          </div>
        </div>
        {spawnMsg && <div style={{ fontSize: 11, color: spawnMsg.endsWith("✓") ? COLORS.success : COLORS.danger, fontFamily: "'JetBrains Mono', monospace" }}>{spawnMsg}</div>}
        <FetchErrorBanner error={liveError} label="live entities" />
        {!liveEntities.length && !liveError && <div style={{ fontSize: 12, color: COLORS.textMuted }}>No live entities in occupied rooms right now (spawns happen in rooms with players).</div>}
        {liveEntities.length > 0 && (
          <DataTable columns={[
            { label: "Entity", render: (row) => (<div><div style={{ fontWeight: 600, fontSize: 13 }}>{row.name}</div><div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{row.id}</div></div>) },
            { label: "Template", key: "template", mono: true },
            { label: "Room", key: "room_id", mono: true },
            { label: "HP", render: (row) => <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{row.hp}/{row.max_hp}</span> },
            { label: "", render: (row) => <ActionButton small variant="danger" onClick={() => doDespawn(row)}>Despawn</ActionButton> },
          ]} rows={liveEntities} />
        )}
      </div>
    </div>
  );
};

const ItemsLibTab = () => {
  const { colors: COLORS } = useAdminTheme();
  const rarityColors = { common: COLORS.textMuted, uncommon: COLORS.success, rare: COLORS.info, epic: COLORS.accent, legendary: COLORS.warning };
  const { rows: items, error: itemsError } = usePolledList(`${API_BASE}/content/items`, 15000);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={openForgeStudio}>AI Generate Item</ActionButton>
      </div>
      <FetchErrorBanner error={itemsError} label="items" />
      {!items.length && !itemsError && <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>No items found. Add YAML under <code style={{ color: COLORS.textDim }}>content/world/items/</code> or generate with AI Forge.</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 }}>
        {items.map((item) => (
          <div key={item.id} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 10, borderLeft: `3px solid ${rarityColors[item.rarity] || COLORS.border}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div><div style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{item.name}</div><div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 2 }}>{item.id}</div></div>
              {item.rarity && <Badge color={rarityColors[item.rarity]}>{item.rarity}</Badge>}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              {item.type && <Pill label="Type" value={item.type} />}
              {item.value > 0 && <Pill label="Value" value={`${item.value}g`} color={COLORS.warning} />}
            </div>
            {item.zones && <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>Zones: {Array.isArray(item.zones) ? item.zones.join(", ") : item.zones}</div>}
          </div>
        ))}
      </div>
    </div>
  );
};

const GlyphsLibTab = () => {
  const { colors: COLORS } = useAdminTheme();
  const catColors = { Combat: COLORS.danger, Defense: COLORS.info, Utility: COLORS.success };
  const { rows: glyphs, error: glyphsError } = usePolledList(`${API_BASE}/content/glyphs`, 15000);
  const rows = glyphs.map((g) => ({
    ...g,
    tier: g.tier ?? "—",
    energyCost: g.energyCost ?? "—",
    bodySlot: g.bodySlot ?? g.body_slot ?? "—",
    effect: g.effect ?? "",
    category: g.category || "Utility",
    name: g.name || g.id,
  }));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <PlannedAction icon={<Icons.Plus />} hint="A glyph editor is planned. Today: generate YAML with AI Forge → Glyph, then save it under content/world/glyphs/.">Design Glyph</PlannedAction>
        <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={openForgeStudio}>AI Forge Glyph</ActionButton>
      </div>
      <FetchErrorBanner error={glyphsError} label="glyphs" />
      {!glyphs.length && !glyphsError && <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>No glyphs found. Add YAML under <code style={{ color: COLORS.textDim }}>content/world/glyphs/</code> or use AI Forge.</div>}
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable columns={[
          { label: "Glyph", render: (row) => (<div style={{ display: "flex", alignItems: "center", gap: 10 }}><div style={{ width: 32, height: 32, borderRadius: 6, background: `${(catColors[row.category] || COLORS.accent)}15`, border: `1px solid ${(catColors[row.category] || COLORS.accent)}30`, display: "flex", alignItems: "center", justifyContent: "center", color: (catColors[row.category] || COLORS.accent), fontSize: 14 }}><Icons.Glyphs /></div><div><div style={{ fontWeight: 600, fontSize: 13 }}>{row.name}</div><div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>{row.id}</div></div></div>) },
          { label: "Category", render: (row) => <Badge color={catColors[row.category] || COLORS.textMuted}>{row.category}</Badge> },
          { label: "Tier", key: "tier", mono: true },
          { label: "Energy", render: (row) => <span style={{ color: COLORS.cyan, fontFamily: "'JetBrains Mono', monospace" }}>{row.energyCost}</span> },
          { label: "Body Slot", key: "bodySlot" },
          { label: "Effect", render: (row) => <span style={{ fontSize: 12, color: COLORS.textMuted }}>{row.effect}</span> },
        ]} rows={rows} />
      </div>
    </div>
  );
};

const CONTENT_LIB_TABS = [
  { id: "zones", label: "Zones" },
  { id: "rooms", label: "Rooms" },
  { id: "entities", label: "Entities" },
  { id: "items", label: "Items" },
  { id: "glyphs", label: "Glyphs" },
];

const ContentLibraryPage = () => {
  const { colors: COLORS } = useAdminTheme();
  const [tab, setTab] = useState("zones");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Content Library</h2>
        <TabBar tabs={CONTENT_LIB_TABS} active={tab} onChange={setTab} />
      </div>
      {tab === "zones" && <ZonesLibTab />}
      {tab === "rooms" && <RoomsLibTab />}
      {tab === "entities" && <EntitiesLibTab />}
      {tab === "items" && <ItemsLibTab />}
      {tab === "glyphs" && <GlyphsLibTab />}
    </div>
  );
};

export default ContentLibraryPage;
