import { useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";

// What points at a room, item or creature (GET /content/references/{kind}/{id}): the content that
// names it, grouped by field, and the saved and live state that holds it. Every entry links to
// the record it names.

const mono = "'JetBrains Mono', monospace";
const roomHref = (roomId) => {
  const [zone, slug] = String(roomId).split(":");
  return slug ? `#/content/rooms/${zone}/${slug}` : null;
};

function Group({ title, children, empty }) {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, fontFamily: mono, textTransform: "uppercase", letterSpacing: "0.06em" }}>{title}</div>
      {children || <div style={{ fontSize: 12, color: COLORS.textDim }}>{empty}</div>}
    </div>
  );
}

function Links({ items }) {
  const { colors: COLORS } = useAdminTheme();
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
      {items.map((it) => (
        it.href
          ? <a key={it.key} href={it.href} style={{ color: COLORS.accent, fontSize: 13 }}>{it.label}{it.note && <span style={{ color: COLORS.textDim, fontFamily: mono, fontSize: 11 }}> {it.note}</span>}</a>
          : <span key={it.key} style={{ fontSize: 13, color: COLORS.textMuted }}>{it.label}{it.note && <span style={{ fontFamily: mono, fontSize: 11 }}> {it.note}</span>}</span>
      ))}
    </div>
  );
}

export default function ReferencesPanel({ kind, id }) {
  const { colors: COLORS } = useAdminTheme();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/content/references/${kind}/${encodeURIComponent(id)}`)
      .then(({ data: d }) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => alive && setError(e?.response?.data?.detail || e.message));
    return () => { alive = false; };
  }, [kind, id]);

  if (error) return <div style={{ fontSize: 12, color: COLORS.danger }}>References: {String(error)}</div>;
  if (!data) return <div style={{ fontSize: 12, color: COLORS.textMuted }}>Finding what uses this…</div>;

  const byField = {};
  for (const r of data.used_by) (byField[r.field] ||= []).push(r);
  const live = data.live || {};
  const count = (rows) => rows.reduce((n, r) => n + r.count, 0);

  return (
    <section aria-label="Used by" style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
      <Group title={`Named in content (${data.used_by_total})`} empty="Nothing in the world package names it.">
        {data.used_by.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {Object.entries(byField).map(([field, rows]) => (
              <div key={field}>
                <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: mono }}>{field}</div>
                <Links items={rows.map((r) => ({ key: `${r.kind}:${r.id}`, href: r.href, label: r.name, note: r.kind === "room" ? r.id : undefined }))} />
              </div>
            ))}
          </div>
        )}
      </Group>
      {live.carried_by && (
        <Group title={`Carried by (${live.carried_by.total})`} empty="No saved character carries one.">
          {live.carried_by.rows.length > 0 && <Links items={live.carried_by.rows.map((c) => ({ key: c.id, href: c.href, label: c.name }))} />}
        </Group>
      )}
      {live.on_floors && (
        <Group title={`On floors (${count(live.on_floors)})`} empty="None lying in any room.">
          {live.on_floors.length > 0 && <Links items={live.on_floors.map((r) => ({ key: r.room_id, href: roomHref(r.room_id), label: r.room_id, note: `×${r.count}` }))} />}
        </Group>
      )}
      {live.alive && (
        <Group title={`Alive now (${count(live.alive)})`} empty="None alive right now.">
          {live.alive.length > 0 && <Links items={live.alive.map((r) => ({ key: r.room_id, href: roomHref(r.room_id), label: r.room_id, note: `×${r.count}` }))} />}
        </Group>
      )}
      {live.saved_here && (
        <Group title={`Characters saved here (${live.saved_here.total})`} empty="No saved character is here.">
          {live.saved_here.rows.length > 0 && <Links items={live.saved_here.rows.map((c) => ({ key: c.id, href: c.href, label: c.name }))} />}
        </Group>
      )}
      {live.present && (
        <Group title={`In the room now (${live.present.length})`} empty="Nobody is in the room.">
          {live.present.length > 0 && <Links items={live.present.map((n) => ({ key: n, label: n }))} />}
        </Group>
      )}
      {(live.carried_by || live.alive) && (
        <div style={{ gridColumn: "1 / -1", fontSize: 11, color: COLORS.textDim }}>
          {live.carried_by && "Carried by reads saved characters, which the server updates about once a minute. "}
          Live copies are under <a href="#/live" style={{ color: COLORS.accent }}>Live › Live world</a>.
        </div>
      )}
    </section>
  );
}
