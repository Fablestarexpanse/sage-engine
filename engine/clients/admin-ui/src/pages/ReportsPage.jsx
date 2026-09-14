import { useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { ActionButton, TabBar, FetchErrorBanner } from "../adminCommon.jsx";
import Pager from "../pager.jsx";

// Players › Reports: what players sent with the in-game `report` command (also `bug`, `typo`,
// `idea`), with the room they were in. Staff mark each one and leave a note.

const mono = "'JetBrains Mono', monospace";
const PAGE = 50;
const STATUSES = [
  { id: "open", label: "Open" },
  { id: "fixed", label: "Fixed" },
  { id: "wont_fix", label: "Won't fix" },
  { id: "duplicate", label: "Duplicate" },
  { id: "all", label: "All" },
];

function roomHref(roomId) {
  const [zone, slug] = String(roomId || "").split(":");
  return slug ? `#/content/rooms/${zone}/${slug}` : null;
}

function ReportRow({ report, onSaved }) {
  const { colors: COLORS } = useAdminTheme();
  const [note, setNote] = useState(report.staff_note || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async (status) => {
    setBusy(true);
    setError("");
    try {
      await axios.patch(`${API_BASE}/admin/reports/${report.id}`, { status, staff_note: note });
      onSaved();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };
  const href = roomHref(report.room_id);
  return (
    <div style={{ borderBottom: `1px solid ${COLORS.border}`, padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap", fontSize: 12, color: COLORS.textMuted }}>
        <span style={{ fontFamily: mono, color: COLORS.textDim }}>#{report.id}</span>
        <span style={{ fontFamily: mono }}>{new Date(report.at).toLocaleString()}</span>
        <span>from <b style={{ color: COLORS.text }}>{report.character}</b></span>
        {report.account_id != null && <a href={`#/accounts/${report.account_id}`} style={{ color: COLORS.accent }}>account</a>}
        {href ? <a href={href} style={{ color: COLORS.accent, fontFamily: mono }}>{report.room_id}</a> : <span style={{ fontFamily: mono }}>{report.room_id || "no room"}</span>}
        <span style={{ marginLeft: "auto" }}>{report.status.replace("_", " ")}{report.handled_by ? ` · ${report.handled_by}` : ""}</span>
      </div>
      <div style={{ fontSize: 14, color: COLORS.text, whiteSpace: "pre-wrap" }}>{report.text}</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input id={`report-${report.id}-note`} aria-label="Staff note" placeholder="Note for other staff" value={note} onChange={(e) => setNote(e.target.value)}
          style={{ flex: 1, minWidth: 200, padding: "6px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13 }} />
        {STATUSES.filter((s) => s.id !== "all" && s.id !== report.status).map((s) => (
          <ActionButton key={s.id} small variant={s.id === "fixed" ? "primary" : "ghost"} disabled={busy} onClick={() => save(s.id)}>
            {s.id === "open" ? "Reopen" : `Mark ${s.label.toLowerCase()}`}
          </ActionButton>
        ))}
        {note !== (report.staff_note || "") && <ActionButton small variant="ghost" disabled={busy} onClick={() => save(undefined)}>Save note</ActionButton>}
      </div>
      {error && <div role="alert" style={{ color: COLORS.danger, fontSize: 12 }}>{String(error)}</div>}
    </div>
  );
}

export default function ReportsPage() {
  const { colors: COLORS } = useAdminTheme();
  const [status, setStatus] = useState("open");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/admin/reports`, { params: { status, limit: PAGE, offset } })
      .then(({ data: d }) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => alive && setError(e?.response?.data?.detail || e.message));
    return () => { alive = false; };
  }, [status, offset, version]);

  const counts = data?.counts || {};
  const tabs = STATUSES.map((s) => ({ id: s.id, label: s.id === "all" ? s.label : `${s.label} (${counts[s.id] ?? 0})` }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Reports</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", maxWidth: 820 }}>
          Sent by players with <code>report</code> (or <code>bug</code>, <code>typo</code>, <code>idea</code>) in the game. Each one carries the room they were standing in.
        </p>
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <TabBar tabs={tabs} active={status} onChange={(id) => { setStatus(id); setOffset(0); }} />
        <span style={{ marginLeft: "auto" }}><Pager offset={offset} limit={PAGE} total={data?.total || 0} onOffset={setOffset} /></span>
      </div>
      <FetchErrorBanner error={error} label="reports" />
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        {data && data.rows.length === 0 && <div style={{ padding: 16, fontSize: 13, color: COLORS.textMuted }}>No {status === "all" ? "" : `${status.replace("_", " ")} `}reports.</div>}
        {(data?.rows || []).map((r) => <ReportRow key={`${r.id}-${r.status}-${r.staff_note}`} report={r} onSaved={() => setVersion((v) => v + 1)} />)}
      </div>
    </div>
  );
}
