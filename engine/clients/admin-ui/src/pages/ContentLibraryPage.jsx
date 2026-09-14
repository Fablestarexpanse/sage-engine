import { useState, useEffect, useMemo } from "react";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import {
  Icons, Badge, Pill, ActionButton, SearchBar, TabBar, DataTable, usePolledList, FetchErrorBanner,
} from "../adminCommon.jsx";
import { RoomDetail, TemplateEditor } from "../contentDetail.jsx";


// ═══════════════════════════════════════════════════════════
// CONTENT LIBRARY — one browsing surface for zones, rooms, entities, items,
// (replaces the former World & Zones / Locations / Entities / Items pages, which were
// overlapping read-only shells). Room layout and exits are edited in WorldForge.
// ═══════════════════════════════════════════════════════════

const openForgeStudio = () => {
  window.dispatchEvent(new CustomEvent("fs-admin-nav", { detail: { page: "forge" } }));
};

const ZonesLibTab = () => {
  const { colors: COLORS } = useAdminTheme();
  const [filter, setFilter] = useState("all");
  const { rows: zones, error: zonesError } = usePolledList(`${API_BASE}/content/zones`, 10000);
  const typeColors = { tutorial: COLORS.success, exploration: COLORS.info, dungeon: COLORS.accent, boss: COLORS.danger, safe: COLORS.warning };
  const filtered = zones.filter((z) => filter === "all" || z.status === filter);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <TabBar tabs={[{ id: "all", label: "All" }, { id: "active", label: "Active" }, { id: "building", label: "Building" }]} active={filter} onChange={setFilter} />
      </div>
      <FetchErrorBanner error={zonesError} label="zones" />
      {filtered.length === 0 && !zonesError && <div style={{ color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>No zones found under content/world/zones. Zones and rooms are made in WorldForge.</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
        {filtered.map((zone) => (
          <div key={zone.id} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}
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
  const [openRoom, setOpenRoom] = useState(null); // { zone, slug }
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <select value={selectedZone} onChange={(e) => setSelectedZone(e.target.value)} style={{ padding: "8px 12px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 8, color: COLORS.text, fontSize: 13, fontFamily: "'DM Sans', sans-serif" }}>
          {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
        </select>
      </div>
      <FetchErrorBanner error={zonesError} label="zones" />
      <FetchErrorBanner error={roomsError} label="rooms" />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{zone?.name || "—"}</div>
          <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 2 }}>{zone?.id} · {zone?.rooms ?? roomRows.length} rooms · depth {zone?.depth ?? "—"}</div>
        </div>
        <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "'DM Sans', sans-serif" }}>
          Select a room to see its description, exits, features and who is there. Rooms are created and edited in WorldForge.
        </div>
      </div>
      {openRoom && (
        <RoomDetail
          key={`${openRoom.zone}:${openRoom.slug}`}
          zoneId={openRoom.zone}
          slug={openRoom.slug}
          onClose={() => setOpenRoom(null)}
          onOpenRoom={(zone, slug) => { setSelectedZone(zone); setOpenRoom({ zone, slug }); }}
        />
      )}
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable columns={[
          { label: "Room", render: (row) => (<div><div style={{ fontWeight: 600, fontSize: 13 }}>{row.name}</div><div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{row.id}</div></div>) },
          { label: "Type", render: (row) => <Badge>{row.type}</Badge> },
          { label: "Exits", render: (row) => (<div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>{(row.exits || []).map((e) => (<span key={e} style={{ width: 22, height: 22, borderRadius: 4, background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 600, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>{e}</span>))}</div>) },
          { label: "Features", key: "features", mono: true },
          { label: "Spawns", key: "entities", mono: true },
          { label: "", render: (row) => (row.error ? <Badge color={COLORS.danger}>does not load</Badge> : null) },
        ]} rows={roomRows} onRowClick={(row) => setOpenRoom({ zone: selectedZone, slug: row.name })} />
      </div>
    </div>
  );
};

const EntitiesLibTab = () => {
  const { colors: COLORS } = useAdminTheme();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState(null);
  const { rows: templates, error: templatesError } = usePolledList(`${API_BASE}/content/entities`, 15000);
  const { rows: spawnRefs } = usePolledList(`${API_BASE}/content/entities/spawns`, 15000);
  const rows = useMemo(() => {
    const refs = Object.fromEntries(spawnRefs.map((r) => [r.name, r.count]));
    return templates.map((t) => ({ ...t, spawn_refs: refs[t.id] ?? 0 }));
  }, [templates, spawnRefs]);
  const filtered = rows.filter((e) => `${e.name} ${e.id}`.toLowerCase().includes(search.toLowerCase()));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <SearchBar placeholder="Search entity templates..." value={search} onChange={setSearch} />
        <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={openForgeStudio}>AI Generate</ActionButton>
      </div>
      <p style={{ margin: 0, fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>Every entity template in the world's <code style={{ color: COLORS.textDim }}>entities/</code>. Spawned in counts the room spawn entries that name it. Select a template to edit it. Live creatures and manual spawns are under <a href="#/live" style={{ color: COLORS.accent }}>Live › Live world</a>.</p>
      <FetchErrorBanner error={templatesError} label="entity templates" />
      {editing && <TemplateEditor key={editing} kind="entities" templateId={editing} onClose={() => setEditing(null)} />}
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <DataTable columns={[
          { label: "Template", render: (row) => <span style={{ fontWeight: 600 }}>{row.name}</span> },
          { label: "Id", key: "id", mono: true },
          { label: "Type", render: (row) => (row.type ? <Badge>{row.type}</Badge> : <span style={{ color: COLORS.textDim }}>—</span>) },
          { label: "Spawned in", render: (row) => <span style={{ fontFamily: "'JetBrains Mono', monospace", color: row.spawn_refs ? COLORS.text : COLORS.textDim }}>{row.spawn_refs}</span> },
          { label: "", render: (row) => (row.parse_error ? <Badge color={COLORS.danger}>does not load</Badge> : null) },
        ]} rows={filtered} onRowClick={(row) => setEditing(row.id)} />
      </div>

    </div>
  );
};

const ItemsLibTab = () => {
  const { colors: COLORS } = useAdminTheme();
  const rarityColors = { common: COLORS.textMuted, uncommon: COLORS.success, rare: COLORS.info, epic: COLORS.accent, legendary: COLORS.warning };
  const { rows: items, error: itemsError } = usePolledList(`${API_BASE}/content/items`, 15000);
  const [editing, setEditing] = useState(null);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={openForgeStudio}>AI Generate Item</ActionButton>
      </div>
      <FetchErrorBanner error={itemsError} label="items" />
      {editing && <TemplateEditor key={editing} kind="items" templateId={editing} onClose={() => setEditing(null)} />}
      {!items.length && !itemsError && <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif" }}>No item templates yet. Add YAML under the world's <code style={{ color: COLORS.textDim }}>content/world/items/</code> or draft one with AI Forge.</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 }}>
        {items.map((item) => (
          <button type="button" key={item.id} onClick={() => setEditing(item.id)} title="Edit this item template" style={{ textAlign: "left", cursor: "pointer", font: "inherit", background: editing === item.id ? COLORS.bgHover : COLORS.bgCard, border: `1px solid ${editing === item.id ? COLORS.borderActive : COLORS.border}`, borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 10, borderLeft: `3px solid ${rarityColors[item.rarity] || COLORS.border}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div><div style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>{item.name}</div><div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 2 }}>{item.id}</div></div>
              {item.rarity && <Badge color={rarityColors[item.rarity]}>{item.rarity}</Badge>}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              {item.type && <Pill label="Type" value={item.type} />}
              {item.parse_error && <Badge color={COLORS.danger}>does not load</Badge>}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
};

const CONTENT_LIB_TABS = [
  { id: "zones", label: "Zones" },
  { id: "rooms", label: "Rooms" },
  { id: "entities", label: "Entities" },
  { id: "items", label: "Items" },
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
    </div>
  );
};

export default ContentLibraryPage;
