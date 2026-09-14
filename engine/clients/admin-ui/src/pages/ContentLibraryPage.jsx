import { useState, useEffect } from "react";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import {
  Icons, Badge, ActionButton, TabBar, DataTable, usePolledList, FetchErrorBanner,
} from "../adminCommon.jsx";
import { useHashParts } from "../listHooks.js";
import { RoomDetail, TemplateEditor } from "../contentDetail.jsx";
import TemplateTable from "../templateTable.jsx";


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

const RoomsLibTab = ({ zoneParam, slugParam, go }) => {
  const { colors: COLORS } = useAdminTheme();
  const selectedZone = zoneParam || "";
  const setSelectedZone = (zone) => go("rooms", zone);
  const openRoom = zoneParam && slugParam ? { zone: zoneParam, slug: slugParam } : null;
  const setOpenRoom = (room) => (room ? go("rooms", room.zone, room.slug) : go("rooms", selectedZone));
  const { rows: zones, error: zonesError } = usePolledList(`${API_BASE}/content/zones`, 12000);
  const { rows: roomRows, error: roomsError } = usePolledList(
    selectedZone ? `${API_BASE}/content/zones/${selectedZone}/rooms` : null,
    10000,
    { enabled: !!selectedZone }
  );
  useEffect(() => {
    if (zones.length && !zoneParam) go("rooms", zones[0].id);
  }, [zones, zoneParam, go]);
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

// Items and creatures: one searchable, sortable table each, with the YAML editor for the selected
// template above it. The selected template is in the URL (#/content/items/<id>).
const TemplatesLibTab = ({ kind, tab, noun, forgeLabel, selectedId, go }) => {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <p style={{ margin: 0, fontSize: 12, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", maxWidth: 760 }}>
          Every {noun.replace(/s$/, "")} template in the world package. Columns include the fields this world&apos;s plugins add; click a heading to sort. Select a row to edit its YAML.
          {kind === "entities" && <> Live creatures and manual spawns are under <a href="#/live" style={{ color: COLORS.accent }}>Live › Live world</a>.</>}
        </p>
        <ActionButton variant="forge" icon={<Icons.Sparkles />} onClick={openForgeStudio}>{forgeLabel}</ActionButton>
      </div>
      {selectedId && <TemplateEditor key={selectedId} kind={kind} templateId={selectedId} onClose={() => go(tab)} />}
      <TemplateTable kind={kind} noun={noun} selectedId={selectedId} onSelect={(id) => go(tab, id)} />
    </div>
  );
};

const CONTENT_LIB_TABS = [
  { id: "zones", label: "Zones" },
  { id: "rooms", label: "Rooms" },
  { id: "creatures", label: "Creatures" },
  { id: "items", label: "Items" },
];

const ContentLibraryPage = () => {
  const { colors: COLORS } = useAdminTheme();
  // #/content/<tab>/<record…>: zones, rooms/<zone>/<room>, creatures/<id>, items/<id>.
  const [parts, go] = useHashParts();
  const tab = CONTENT_LIB_TABS.some((t) => t.id === parts[0]) ? parts[0] : "zones";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Content Library</h2>
        <TabBar tabs={CONTENT_LIB_TABS} active={tab} onChange={(id) => go(id)} />
      </div>
      {tab === "zones" && <ZonesLibTab />}
      {tab === "rooms" && <RoomsLibTab zoneParam={parts[1]} slugParam={parts[2]} go={go} />}
      {tab === "creatures" && <TemplatesLibTab kind="entities" tab="creatures" noun="creatures" forgeLabel="Draft a creature with AI" selectedId={parts[1]} go={go} />}
      {tab === "items" && <TemplatesLibTab kind="items" tab="items" noun="items" forgeLabel="Draft an item with AI" selectedId={parts[1]} go={go} />}
    </div>
  );
};

export default ContentLibraryPage;
