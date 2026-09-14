import { useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";
import { Badge, SearchBar, FetchErrorBanner } from "./adminCommon.jsx";
import Pager from "./pager.jsx";
import { useDebounced } from "./listHooks.js";

// Entity or item templates as one server-paged table (GET /content/templates/{kind}). The columns
// come from the server: the template model plus the fields this world's plugins add, so a combat
// plugin's attack or a crafting plugin's recipe shows up here with no console change.

const mono = "'JetBrains Mono', monospace";
const PAGE = 50;

function Cell({ col, value }) {
  const { colors: COLORS } = useAdminTheme();
  if (value == null) return <span style={{ color: COLORS.textDim }}>—</span>;
  if (col.kind === "tags") return <span style={{ fontSize: 11, color: COLORS.textMuted }}>{value.join(", ")}</span>;
  if (col.kind === "bool") return <span>{value ? "yes" : "no"}</span>;
  if (col.kind === "count") return <span style={{ fontFamily: mono }} title={`${value} entr${value === 1 ? "y" : "ies"}`}>{value}</span>;
  if (col.key === "type") return <Badge>{value}</Badge>;
  return <span style={{ fontFamily: col.kind === "number" ? mono : undefined }}>{String(value)}</span>;
}

export default function TemplateTable({ kind, noun, selectedId, onSelect }) {
  const { colors: COLORS } = useAdminTheme();
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [type, setType] = useState("");
  const [sort, setSort] = useState({ key: "name", desc: false });
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () => axios.get(`${API_BASE}/content/templates/${kind}`, { params: { q, type, sort: sort.key, desc: sort.desc, limit: PAGE, offset } })
      .then(({ data: d }) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => alive && setError(e?.response?.data?.detail || e.message));
    load();
    // Cheap on the server (unchanged files are not parsed again), so a slow refresh picks up saves.
    const id = setInterval(load, 30000);
    return () => { alive = false; clearInterval(id); };
  }, [kind, q, type, sort, offset]);

  const toggleSort = (key) => {
    setOffset(0);
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: false }));
  };
  const columns = [{ key: "name", label: "Name", kind: "text" }, ...(data?.columns || [])];
  const th = { textAlign: "left", padding: "9px 12px", fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: `1px solid ${COLORS.border}`, fontFamily: mono, whiteSpace: "nowrap" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <SearchBar placeholder={`Search ${noun} by name, id or tag…`} value={search} onChange={(v) => { setSearch(v); setOffset(0); }} />
        <select id={`${kind}-type-filter`} aria-label="Type" value={type} onChange={(e) => { setType(e.target.value); setOffset(0); }}
          style={{ padding: "8px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 8, color: COLORS.text, fontSize: 13 }}>
          <option value="">every type</option>
          {(data?.types || []).map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span style={{ marginLeft: "auto" }}><Pager offset={offset} limit={PAGE} total={data?.total || 0} onOffset={setOffset} /></span>
      </div>
      <FetchErrorBanner error={error} label={noun} />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, color: COLORS.text }}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} style={th} aria-sort={sort.key === c.key ? (sort.desc ? "descending" : "ascending") : undefined}
                  title={c.owner ? `Added by the ${c.owner} plugin` : undefined}>
                  <button type="button" onClick={() => toggleSort(c.key)} style={{ all: "unset", cursor: "pointer" }}>
                    {c.label}{sort.key === c.key ? (sort.desc ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data?.rows || []).map((r) => (
              <tr key={r.id} onClick={() => onSelect(r.id)}
                style={{ cursor: "pointer", background: selectedId === r.id ? COLORS.bgHover : "transparent", borderBottom: `1px solid ${COLORS.border}22` }}>
                <td style={{ padding: "8px 12px", whiteSpace: "nowrap" }}>
                  <div style={{ fontWeight: 600 }}>{r.name}</div>
                  <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: mono }}>{r.id}</div>
                </td>
                {r.parse_error ? (
                  <td colSpan={columns.length - 1} style={{ padding: "8px 12px" }}><Badge color={COLORS.danger}>does not load</Badge> <span style={{ fontSize: 12, color: COLORS.textMuted }}>{r.parse_error}</span></td>
                ) : (data.columns.map((c) => (
                  <td key={c.key} style={{ padding: "8px 12px", whiteSpace: "nowrap" }}><Cell col={c} value={r.values[c.key]} /></td>
                )))}
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.rows.length === 0 && <div style={{ padding: 16, fontSize: 13, color: COLORS.textMuted }}>{data.total === 0 && !q && !type ? `No ${noun} yet.` : `No ${noun} match.`}</div>}
      </div>
    </div>
  );
}
