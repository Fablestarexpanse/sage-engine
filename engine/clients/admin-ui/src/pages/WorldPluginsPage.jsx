import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { Icons, Badge, ActionButton, DataTable, StatCard, FetchErrorBanner } from "../adminCommon.jsx";
import { useWorldSummary } from "../useWorldSummary.js";

// World & plugins: which world package is running, what it loaded, whether its content validates
// and its database is migrated. GET /admin/world and GET /admin/world/check.

const mono = "'JetBrains Mono', monospace";
const sans = "'DM Sans', sans-serif";

function Card({ title, icon, right, children }) {
  const { colors: COLORS } = useAdminTheme();
  return (
    <section style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: sans, display: "flex", alignItems: "center", gap: 8 }}>{icon}{title}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

function FindingList({ lines, color, empty }) {
  const { colors: COLORS } = useAdminTheme();
  if (!lines.length) return <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: sans }}>{empty}</div>;
  return (
    <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 4, maxHeight: 260, overflowY: "auto" }}>
      {lines.map((line, i) => (
        <li key={i} style={{ fontFamily: mono, fontSize: 12, color: COLORS.text, padding: "5px 8px", borderLeft: `3px solid ${color}`, background: COLORS.bgInput, borderRadius: 4, overflowWrap: "anywhere" }}>{line}</li>
      ))}
    </ul>
  );
}

const REGISTRATION_LABELS = [
  ["commands", "command", "commands"],
  ["events_subscribe", "event listener", "event listeners"],
  ["events_publish", "event published", "events published"],
  ["resolvers", "resolver", "resolvers"],
  ["tick_jobs", "tick job", "tick jobs"],
  ["state_blocks", "state block", "state blocks"],
  ["content_extensions", "content field", "content fields"],
  ["panels", "panel", "panels"],
  ["routes", "route group", "route groups"],
  ["tables", "table", "tables"],
];

function registrationSummary(registered) {
  return REGISTRATION_LABELS
    .filter(([k]) => registered?.[k]?.length)
    .map(([k, one, many]) => `${registered[k].length} ${registered[k].length === 1 ? one : many}`)
    .join(" · ");
}

export default function WorldPluginsPage() {
  const { colors: COLORS } = useAdminTheme();
  const { summary, error: summaryError } = useWorldSummary(30000);
  const [check, setCheck] = useState(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState(null);
  const [showInfo, setShowInfo] = useState(false);
  const [openPlugin, setOpenPlugin] = useState(null);

  const runCheck = useCallback(async () => {
    setChecking(true);
    setCheckError(null);
    try {
      const { data } = await axios.get(`${API_BASE}/admin/world/check`);
      setCheck({ ...data, at: new Date() });
    } catch (e) {
      setCheckError(e?.response?.data?.detail || e.message || "Check failed");
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => { runCheck(); }, [runCheck]);

  const lint = check?.lint;
  const migrations = check?.migrations;
  const world = summary?.world;
  const plugins = summary?.plugins || [];
  const slots = useMemo(() => Object.entries(summary?.ai_slots || {}).map(([slot, v]) => ({ slot, ...v })), [summary]);
  const selected = plugins.find((p) => p.id === openPlugin);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>World &amp; plugins</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: sans, maxWidth: 820, lineHeight: 1.5 }}>
          The world package this server runs, the plugins it loaded, and whether its content and database are in a good state.
        </p>
      </div>
      <FetchErrorBanner error={summaryError} label="World summary" />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 14 }}>
        <StatCard label="World" value={world ? world.name : "—"} color={COLORS.accent} icon={<Icons.World />} title={world ? `${world.id} ${world.version}` : undefined} />
        <StatCard label="Plugins loaded" value={summary ? String(plugins.length) : "—"} color={COLORS.info} icon={<Icons.Content />} />
        <StatCard label="Content errors" value={lint ? String(lint.counts.err) : "—"} color={lint?.counts.err ? COLORS.danger : COLORS.success} icon={<Icons.Alert />} />
        <StatCard label="Migrations" value={migrations ? (migrations.ok ? "up to date" : migrations.error ? "unknown" : `${migrations.pending.length} pending`) : "—"} color={migrations?.ok ? COLORS.success : COLORS.warning} icon={<Icons.History />} />
      </div>

      <Card title="World package" icon={<Icons.World />}>
        {!world ? <div style={{ fontSize: 12, color: COLORS.textMuted }}>Loading…</div> : (
          <div style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "6px 18px", fontSize: 13, fontFamily: sans, color: COLORS.text }}>
            <span style={{ color: COLORS.textMuted }}>Name</span><span>{world.name}</span>
            <span style={{ color: COLORS.textMuted }}>Id and version</span><span style={{ fontFamily: mono }}>{world.id} {world.version}</span>
            <span style={{ color: COLORS.textMuted }}>Package</span><span style={{ fontFamily: mono }}>{world.path}</span>
            <span style={{ color: COLORS.textMuted }}>Engine</span><span style={{ fontFamily: mono }}>SAGE {summary.engine.version}</span>
            <span style={{ color: COLORS.textMuted }}>Room types</span>
            <span style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{(world.room_types || []).map((t) => <Badge key={t} color={COLORS.textMuted}>{t}</Badge>)}</span>
          </div>
        )}
      </Card>

      <Card
        title="Content check"
        icon={<Icons.Check />}
        right={
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {check?.at && <span style={{ fontSize: 11, color: COLORS.textDim, fontFamily: mono }}>checked {check.at.toLocaleTimeString()}</span>}
            <ActionButton small variant="primary" icon={<Icons.Refresh />} onClick={runCheck} disabled={checking}>{checking ? "Checking…" : "Run check"}</ActionButton>
          </div>
        }
      >
        <FetchErrorBanner error={checkError} label="Content check" />
        {lint && (
          <>
            <div style={{ fontSize: 13, color: COLORS.text, fontFamily: sans }}>
              {lint.rooms} rooms in {lint.zones} zones: <strong style={{ color: lint.counts.err ? COLORS.danger : COLORS.success }}>{lint.counts.err} error{lint.counts.err === 1 ? "" : "s"}</strong>,{" "}
              <strong style={{ color: lint.counts.warn ? COLORS.warning : COLORS.success }}>{lint.counts.warn} warning{lint.counts.warn === 1 ? "" : "s"}</strong>.
              <span style={{ color: COLORS.textMuted }}> The same check as <code>python -m sage validate</code>. Errors break play: a room whose file does not load shows players "You are in the void.", and an exit to a missing room goes nowhere. Fix rooms and exits in WorldForge.</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 14 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: COLORS.danger, fontFamily: mono, textTransform: "uppercase", letterSpacing: "0.06em" }}>Errors</span>
                <FindingList lines={lint.errors} color={COLORS.danger} empty="No errors." />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: COLORS.warning, fontFamily: mono, textTransform: "uppercase", letterSpacing: "0.06em" }}>Warnings</span>
                <FindingList lines={lint.warnings} color={COLORS.warning} empty="No warnings." />
              </div>
            </div>
            {lint.info.length > 0 && (
              <div>
                <button type="button" onClick={() => setShowInfo((v) => !v)} style={{ background: "none", border: "none", padding: 0, color: COLORS.accent, cursor: "pointer", fontSize: 12, fontFamily: sans }}>
                  {showInfo ? "Hide" : "Show"} {lint.info.length} notes (one-way exits, links between zones, dead ends)
                </button>
                {showInfo && <div style={{ marginTop: 8 }}><FindingList lines={lint.info} color={COLORS.info} empty="" /></div>}
              </div>
            )}
          </>
        )}
        {migrations && (
          <div style={{ fontSize: 13, fontFamily: sans, color: COLORS.text, borderTop: `1px solid ${COLORS.border}`, paddingTop: 10 }}>
            <strong>Database migrations:</strong>{" "}
            {migrations.ok && <span style={{ color: COLORS.success }}>core and every enabled plugin are up to date.</span>}
            {!migrations.ok && migrations.error && <span style={{ color: COLORS.warning }}>could not be checked ({migrations.error}).</span>}
            {!migrations.ok && !migrations.error && (
              <span style={{ color: COLORS.warning }}>
                unapplied heads <code>{migrations.pending.join(", ")}</code>. Run <code>python -m sage db upgrade</code> and restart.
              </span>
            )}
          </div>
        )}
      </Card>

      <Card title={`Plugins (${plugins.length})`} icon={<Icons.Content />}>
        {summary && plugins.length === 0 && (
          <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: sans }}>This world enables no plugins. List them under <code>[plugins]</code> in its <code>world.toml</code>, then run <code>python -m sage db upgrade</code> and restart.</div>
        )}
        {plugins.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <DataTable
              onRowClick={(row) => setOpenPlugin((cur) => (cur === row.id ? null : row.id))}
              columns={[
                { label: "Plugin", render: (p) => <span style={{ fontWeight: 600 }}>{p.name}{p.name.toLowerCase() !== p.id && <span style={{ color: COLORS.textDim, fontWeight: 400, fontFamily: mono }}> {p.id}</span>}</span> },
                { label: "Version", key: "version", mono: true },
                { label: "Source", render: (p) => <Badge color={p.source === "world" ? COLORS.accent : COLORS.info}>{p.source === "world" ? "world plugin" : "shared"}</Badge> },
                { label: "Needs", render: (p) => <span style={{ fontFamily: mono, fontSize: 12 }}>{p.depends.length ? p.depends.join(", ") : "—"}</span> },
                { label: "Registered", render: (p) => <span style={{ fontSize: 12, color: COLORS.textMuted }}>{registrationSummary(p.registered) || "—"}</span> },
                { label: "Admin page", render: (p) => (p.admin_tool ? <a href={`#/${p.admin_tool}`} onClick={(e) => e.stopPropagation()} style={{ color: COLORS.accent, fontSize: 12 }}>Open</a> : <span style={{ color: COLORS.textDim }}>—</span>) },
              ]}
              rows={plugins}
            />
          </div>
        )}
        {selected && (
          <div style={{ borderTop: `1px solid ${COLORS.border}`, paddingTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 13, color: COLORS.text, fontFamily: sans }}>
              <strong>{selected.name}</strong> <span style={{ fontFamily: mono, color: COLORS.textDim }}>{selected.path}</span>
              <span style={{ color: COLORS.textMuted }}> · engine {selected.engine} · declared in plugin.toml [touches]; anything registered outside it fails at boot.</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "4px 16px", fontSize: 12 }}>
              {Object.entries(selected.declared || {}).map(([kind, value]) => (
                <div key={kind} style={{ display: "contents" }}>
                  <span style={{ color: COLORS.textMuted, fontFamily: mono }}>{kind}</span>
                  <span style={{ fontFamily: mono, color: COLORS.text, overflowWrap: "anywhere" }}>{Array.isArray(value) ? value.join(", ") : String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {plugins.length > 0 && !selected && <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: sans }}>Select a plugin to see what its manifest declares.</div>}
      </Card>

      <Card title="AI slots" icon={<Icons.Sparkles />}>
        <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: sans }}>
          A slot is on when the world ships <code>ai/prompts/&lt;slot&gt;.j2</code>. Off slots fall back to plain text, and Forge types that need them are disabled.
        </div>
        <div style={{ overflowX: "auto" }}>
          <DataTable
            columns={[
              { label: "Slot", key: "slot", mono: true },
              { label: "Declared by", render: (s) => <span style={{ fontFamily: mono, fontSize: 12 }}>{s.owner === "sage" ? "engine" : s.owner}</span> },
              { label: "State", render: (s) => <Badge color={s.enabled ? COLORS.success : COLORS.textDim}>{s.enabled ? "on" : "off"}</Badge> },
            ]}
            rows={slots}
          />
        </div>
      </Card>
    </div>
  );
}
