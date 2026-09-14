import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";
import { SearchBar } from "./adminCommon.jsx";
import Pager from "./pager.jsx";
import { useDebounced } from "./listHooks.js";

/** Matches server comfyui.toml default: 100 credits ≈ US $1 at list. */

function ConsoleAccessSection({ detail, accountId, disabled, onChanged }) {
  const { colors: COLORS } = useAdminTheme();
  const [pw, setPw] = useState("");
  const [role, setRole] = useState("gm");
  const ca = detail?.console_access;

  useEffect(() => {
    if (ca?.role) setRole(ca.role);
  }, [ca?.role, accountId]);

  const grant = async () => {
    if (pw.length < 4) {
      window.alert("Console password must be at least 4 characters.");
      return;
    }
    try {
      await axios.put(`${API_BASE}/admin/player-accounts/${accountId}/console-access`, {
        password: pw,
        role,
      });
      setPw("");
      await onChanged();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message || "Failed");
    }
  };

  const revoke = async () => {
    if (!window.confirm("Deactivate Nexus console login for this play username?")) return;
    try {
      await axios.delete(`${API_BASE}/admin/player-accounts/${accountId}/console-access`);
      await onChanged();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message || "Failed");
    }
  };

  return (
    <div
      style={{
        padding: 12,
        borderRadius: 8,
        border: `1px solid ${COLORS.border}`,
        background: COLORS.bgInput,
        marginBottom: 4,
      }}
    >
      <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
        Nexus console (admin panel)
      </div>
      <p style={{ margin: "0 0 10px", fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5 }}>
        Grant a <strong style={{ color: COLORS.text }}>separate</strong> admin login that uses this play username (lowercased). In-game <strong style={{ color: COLORS.text }}>GM crown</strong> is still the checkbox below.
      </p>
      {ca?.is_active ? (
        <div style={{ fontSize: 12, color: COLORS.text, marginBottom: 10, fontFamily: "'JetBrains Mono', monospace" }}>
          Active · role <strong>{ca.role}</strong> · staff #{ca.staff_id}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 10 }}>No active console user tied to this play name.</div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 8 }}>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          disabled={disabled}
          style={{ padding: "6px 8px", background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }}
        >
          <option value="gm">GM (console)</option>
          <option value="admin">Admin</option>
          <option value="head_admin">Head admin</option>
        </select>
        <input
          type="password"
          placeholder={ca?.is_active ? "New password (min 4)" : "Password (min 4)"}
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          disabled={disabled}
          style={{ padding: "6px 10px", minWidth: 160, background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text }}
          autoComplete="new-password"
        />
        <button
          type="button"
          disabled={disabled}
          onClick={grant}
          style={{ padding: "6px 12px", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: disabled ? "wait" : "pointer" }}
        >
          {ca?.is_active ? "Update" : "Grant"}
        </button>
        {ca?.is_active ? (
          <button
            type="button"
            disabled={disabled}
            onClick={revoke}
            style={{ padding: "6px 12px", background: COLORS.bgCard, color: COLORS.danger, border: `1px solid ${COLORS.border}`, borderRadius: 6, fontWeight: 600, cursor: disabled ? "wait" : "pointer" }}
          >
            Revoke
          </button>
        ) : null}
      </div>
      <div style={{ fontSize: 10, color: COLORS.textDim }}>Head admins can assign any role; Admin role can only assign GM.</div>
    </div>
  );
}

/** focusTarget: jump to an account (e.g. from Live sessions). */
const ACCOUNTS_PAGE = 50;

export default function PlayerAccountsTab({ focusTarget = null, onSelect }) {
  const { colors: COLORS } = useAdminTheme();
  const inp = {
    padding: "8px 10px",
    background: COLORS.bgInput,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 6,
    color: COLORS.text,
    fontSize: 13,
    width: "100%",
    boxSizing: "border-box",
  };
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("username");
  const [offset, setOffset] = useState(0);
  const [err, setErr] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailErr, setDetailErr] = useState("");
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(async () => {
    setErr("");
    const url = `${API_BASE}/admin/player-accounts`;
    const desc = sort === "created" || sort === "last_login" || sort === "characters";
    try {
      const { data } = await axios.get(url, { params: { q, filter, sort, desc, limit: ACCOUNTS_PAGE, offset } });
      setRows(data.rows || []);
      setTotal(data.total || 0);
    } catch (e) {
      const detail = e.response?.data?.detail;
      const detailStr =
        typeof detail === "string" ? detail : detail != null ? JSON.stringify(detail) : "";
      const status = e.response?.status;
      const parts = [
        detailStr || null,
        status ? `HTTP ${status}` : null,
        e.message === "Network Error" || !e.response
          ? `Cannot reach Nexus at ${API_BASE} (is the server running on the same port as config/server.toml?)`
          : null,
      ].filter(Boolean);
      setErr(parts.join(" — ") || "Failed to load accounts");
      setRows([]);
      setTotal(0);
    }
  }, [q, filter, sort, offset]);

  const [economy, setEconomy] = useState(null);
  useEffect(() => {
    let alive = true;
    axios
      .get(`${API_BASE}/admin/economy`)
      .then(({ data }) => alive && setEconomy(data))
      .catch(() => alive && setEconomy(null));
    return () => {
      alive = false;
    };
  }, []);

  const loadDetail = useCallback(async (id) => {
    if (id == null) return;
    setBusy(true);
    setDetailErr("");
    try {
      const { data } = await axios.get(`${API_BASE}/admin/player-accounts/${id}`);
      setDetail(data);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || "Load failed";
      setDetailErr(typeof msg === "string" ? msg : JSON.stringify(msg));
      setDetail(null);
    } finally {
      setBusy(false);
    }
  }, []);

  const reloadAccount = useCallback(async () => {
    if (selectedId == null) return;
    await loadList();
    await loadDetail(selectedId);
  }, [selectedId, loadList, loadDetail]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (focusTarget?.accountId != null) {
      setSelectedId(focusTarget.accountId);
    }
  }, [focusTarget?.accountId, focusTarget?.nonce]);

  useEffect(() => {
    if (selectedId != null) loadDetail(selectedId);
    else {
      setDetail(null);
      setDetailErr("");
    }
  }, [selectedId, loadDetail]);

  const saveAccount = async (patch) => {
    if (selectedId == null) return;
    setBusy(true);
    try {
      await axios.patch(`${API_BASE}/admin/player-accounts/${selectedId}`, patch);
      await reloadAccount();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  // Saved-character editor (raw fields). For live changes to a playing character, use Characters above.
  const saveCharacter = async (charId, patch) => {
    if (selectedId == null) return;
    setBusy(true);
    try {
      await axios.patch(`${API_BASE}/admin/player-accounts/${selectedId}/characters/${charId}`, patch);
      await reloadAccount();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const grantBundleCredits = async (credits) => {
    if (selectedId == null || credits <= 0) return;
    setBusy(true);
    try {
      await axios.patch(`${API_BASE}/admin/player-accounts/${selectedId}`, { ai_credits_add: credits });
      await reloadAccount();
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 16,
        width: "100%",
        minWidth: 0,
      }}
    >
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden", width: "100%" }}>
        <div style={{ padding: "10px 12px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <SearchBar placeholder="Search login or email…" value={search} onChange={(v) => { setSearch(v); setOffset(0); }} />
          <select id="accounts-filter" aria-label="Show" value={filter} onChange={(e) => { setFilter(e.target.value); setOffset(0); }} style={{ ...inp, width: "auto" }}>
            <option value="all">All accounts</option>
            <option value="suspended">Suspended</option>
            <option value="gm">GM crown</option>
            <option value="no_characters">No characters</option>
          </select>
          <select id="accounts-sort" aria-label="Sort by" value={sort} onChange={(e) => { setSort(e.target.value); setOffset(0); }} style={{ ...inp, width: "auto" }}>
            <option value="username">Login A–Z</option>
            <option value="last_login">Last signed in</option>
            <option value="created">Newest</option>
            <option value="characters">Most characters</option>
          </select>
          <span style={{ marginLeft: "auto" }}><Pager offset={offset} limit={ACCOUNTS_PAGE} total={total} onOffset={setOffset} /></span>
        </div>
        {err && <div style={{ padding: 12, color: COLORS.danger, fontSize: 12 }}>{String(err)}</div>}
        <div style={{ maxHeight: 260, overflowY: "auto" }}>
          {rows.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => { setSelectedId(r.id); onSelect?.(r.id); }}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "10px 12px",
                border: "none",
                borderBottom: `1px solid ${COLORS.border}`,
                background: selectedId === r.id ? "rgba(124,106,239,0.12)" : "transparent",
                color: COLORS.text,
                cursor: "pointer",
                fontFamily: "'DM Sans', sans-serif",
              }}
            >
              <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {r.username}
                {r.muted_until && new Date(r.muted_until) > new Date() ? (
                  <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: COLORS.warningBg, color: COLORS.warning, border: `1px solid ${COLORS.warning}` }}>muted</span>
                ) : null}
                {r.suspended_at ? (
                  <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: COLORS.dangerBg, color: COLORS.danger, border: `1px solid ${COLORS.danger}` }}>suspended</span>
                ) : null}
                {r.is_gm ? (
                  <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "rgba(244,114,182,0.2)", color: "#f9a8d4", border: "1px solid rgba(244,114,182,0.45)" }}>👑 GM</span>
                ) : null}
              </div>
              <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4, fontFamily: "'JetBrains Mono', monospace" }}>
                id {r.id} · {r.character_count} chars · credits {r.ai_credits}{r.last_login ? ` · last in ${new Date(r.last_login).toLocaleDateString()}` : ""}
              </div>
            </button>
          ))}
          {rows.length === 0 && !err && <div style={{ padding: 16, color: COLORS.textMuted, fontSize: 13 }}>{q || filter !== "all" ? "No accounts match." : "No accounts yet."}</div>}
        </div>
      </div>

      <div
        style={{
          background: COLORS.bgCard,
          border: `1px solid ${selectedId ? COLORS.accent : COLORS.border}`,
          borderRadius: 10,
          padding: 18,
          width: "100%",
          minWidth: 0,
          boxShadow: selectedId ? `0 0 0 1px ${COLORS.accent}33` : "none",
        }}
      >
        <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>Account editor</div>
        {!selectedId && (
          <div style={{ color: COLORS.textMuted, fontSize: 13, lineHeight: 1.5 }}>
            Select an account above for <strong style={{ color: COLORS.text }}>credits</strong>, <strong style={{ color: COLORS.text }}>bundles</strong>, <strong style={{ color: COLORS.text }}>GM crown</strong>, Nexus console access, and characters.
          </div>
        )}
        {selectedId && busy && !detail && !detailErr && <div style={{ color: COLORS.textMuted }}>Loading…</div>}
        {selectedId && !busy && !detail && detailErr && (
          <div style={{ color: COLORS.danger, fontSize: 13 }} role="alert">
            {detailErr}
          </div>
        )}
        {detail && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <h3 style={{ margin: "0 0 8px", fontSize: 18, color: COLORS.text }}>{detail.username}</h3>
              <div style={{ fontSize: 12, color: COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>account #{detail.id}</div>
            </div>

            <SuspensionSection detail={detail} accountId={selectedId} disabled={busy} onChanged={reloadAccount} />

            <MuteSection detail={detail} accountId={selectedId} disabled={busy} onChanged={reloadAccount} />

            <SignInsSection key={selectedId} accountId={selectedId} />

            <ConsoleAccessSection detail={detail} accountId={selectedId} disabled={busy} onChanged={reloadAccount} />

            <AccountEditForm
              detail={detail}
              disabled={busy}
              onSave={saveAccount}
              onGrantBundleCredits={grantBundleCredits}
              economy={economy}
            />

            <div style={{ borderTop: `1px solid ${COLORS.border}`, paddingTop: 12 }}>
              <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>Characters</div>
              {(detail.characters || []).map((c) => (
                <CharacterEditCard key={c.id} c={c} disabled={busy} onSave={(patch) => saveCharacter(c.id, patch)} />
              ))}
              {(!detail.characters || detail.characters.length === 0) && (
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>No characters</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const MUTE_LENGTHS = [
  [15, "15 minutes"],
  [60, "1 hour"],
  [60 * 24, "1 day"],
  [60 * 24 * 7, "1 week"],
];

// A muted account's characters cannot say, emote or tell; connected ones are told at once.
function MuteSection({ detail, accountId, disabled, onChanged }) {
  const { colors: COLORS } = useAdminTheme();
  const [minutes, setMinutes] = useState(60);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (fn) => {
    setBusy(true);
    try {
      await fn();
      setReason("");
      await onChanged?.();
    } catch (e) {
      const d = e.response?.data?.detail;
      window.alert(typeof d === "string" ? d : e.message);
    } finally {
      setBusy(false);
    }
  };
  const until = detail.muted_until ? new Date(detail.muted_until) : null;
  const muted = until && until > new Date();
  return (
    <div style={{ padding: "10px 12px", borderRadius: 8, border: `1px solid ${muted ? COLORS.warning : COLORS.border}`, background: muted ? COLORS.warningBg : COLORS.bgInput, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Mute</div>
      {muted ? (
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: COLORS.text }}>Muted until {until.toLocaleString()}{detail.mute_reason ? `: ${detail.mute_reason}` : ""}. Their characters cannot say, emote or tell.</span>
          <button type="button" disabled={disabled || busy} onClick={() => run(() => axios.delete(`${API_BASE}/admin/player-accounts/${accountId}/mute`))}
            style={{ padding: "6px 12px", borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bgCard, color: COLORS.text, cursor: "pointer", fontSize: 12 }}>Lift mute</button>
        </div>
      ) : (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <select id={`mute-length-${accountId}`} aria-label="Mute length" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
            style={{ padding: "7px 10px", background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13 }}>
            {MUTE_LENGTHS.map(([m, label]) => <option key={m} value={m}>{label}</option>)}
          </select>
          <input id={`mute-reason-${accountId}`} aria-label="Reason for mute" placeholder="Reason (shown to staff)" value={reason} onChange={(e) => setReason(e.target.value)}
            style={{ flex: 1, minWidth: 180, padding: "7px 10px", background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13 }} />
          <button type="button" disabled={disabled || busy} onClick={() => run(() => axios.post(`${API_BASE}/admin/player-accounts/${accountId}/mute`, { minutes, reason }))}
            style={{ padding: "6px 12px", borderRadius: 6, border: `1px solid ${COLORS.warning}`, background: "transparent", color: COLORS.warning, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>Mute</button>
        </div>
      )}
    </div>
  );
}

// This account's recent sign-ins; addresses appear only if the operator records them.
function SignInsSection({ accountId }) {
  const { colors: COLORS } = useAdminTheme();
  const [data, setData] = useState(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/admin/moderation/logins`, { params: { account_id: accountId, limit: 10 } })
      .then(({ data: d }) => alive && setData(d))
      .catch(() => alive && setData({ rows: [], total: 0 }));
    return () => { alive = false; };
  }, [accountId, version]);
  const erase = async () => {
    if (!window.confirm("Erase this account's stored sign-in addresses? Sign-in times stay.")) return;
    try {
      await axios.delete(`${API_BASE}/admin/player-accounts/${accountId}/logins`);
      setVersion((v) => v + 1);
    } catch (e) {
      window.alert(e.response?.data?.detail || e.message);
    }
  };
  if (!data) return null;
  const hasAddresses = data.rows.some((r) => r.address);
  return (
    <div style={{ padding: "10px 12px", borderRadius: 8, border: `1px solid ${COLORS.border}`, background: COLORS.bgInput, display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Recent sign-ins ({data.total})</span>
        {hasAddresses && <button type="button" onClick={erase} style={{ marginLeft: "auto", padding: "3px 10px", borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bgCard, color: COLORS.text, cursor: "pointer", fontSize: 11 }}>Erase addresses</button>}
      </div>
      {data.rows.length === 0 && <div style={{ fontSize: 12, color: COLORS.textDim }}>No sign-ins recorded.</div>}
      {data.rows.map((r) => (
        <div key={r.id} style={{ display: "flex", gap: 12, fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: COLORS.text }}>
          <span>{new Date(r.at).toLocaleString()}</span>
          <span style={{ color: COLORS.textMuted }}>{r.method}</span>
          <span style={{ color: r.address ? COLORS.text : COLORS.textDim }}>{r.address || "address not recorded"}</span>
        </div>
      ))}
    </div>
  );
}

function SuspensionSection({ detail, accountId, disabled, onChanged }) {
  const { colors: COLORS } = useAdminTheme();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (fn) => {
    setBusy(true);
    try {
      await fn();
      setReason("");
      await onChanged?.();
    } catch (e) {
      const d = e.response?.data?.detail;
      window.alert(typeof d === "string" ? d : e.message);
    } finally {
      setBusy(false);
    }
  };
  const suspended = Boolean(detail.suspended_at);
  return (
    <div style={{ padding: "10px 12px", borderRadius: 8, border: `1px solid ${suspended ? COLORS.danger : COLORS.border}`, background: suspended ? COLORS.dangerBg : COLORS.bgInput, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Suspension</div>
      {suspended ? (
        <>
          <div style={{ fontSize: 13, color: COLORS.text }}>
            Suspended since {new Date(detail.suspended_at).toLocaleString()}{detail.suspended_reason ? `: ${detail.suspended_reason}` : ""}. This account cannot sign in or play.
          </div>
          <button type="button" disabled={disabled || busy} onClick={() => run(() => axios.delete(`${API_BASE}/admin/player-accounts/${accountId}/suspend`))}
            style={{ alignSelf: "start", padding: "6px 12px", borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bgCard, color: COLORS.text, cursor: "pointer", fontSize: 12 }}>Lift suspension</button>
        </>
      ) : (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input id={`suspend-reason-${accountId}`} aria-label="Reason for suspension" placeholder="Reason (shown to staff)" value={reason} onChange={(e) => setReason(e.target.value)}
            style={{ flex: 1, minWidth: 180, padding: "7px 10px", background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13 }} />
          <button type="button" disabled={disabled || busy} onClick={() => {
            if (window.confirm(`Suspend ${detail.username}? Their characters are disconnected and they cannot sign in until the suspension is lifted.`)) {
              run(() => axios.post(`${API_BASE}/admin/player-accounts/${accountId}/suspend`, { reason }));
            }
          }} style={{ padding: "6px 12px", borderRadius: 6, border: `1px solid ${COLORS.danger}`, background: "transparent", color: COLORS.danger, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>Suspend account</button>
        </div>
      )}
    </div>
  );
}

function AccountEditForm({ detail, disabled, onSave, onGrantBundleCredits, economy }) {
  const bundles = economy?.credit_bundles || [];
  const { colors: COLORS } = useAdminTheme();
  const inp = {
    padding: "8px 10px",
    background: COLORS.bgInput,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 6,
    color: COLORS.text,
    fontSize: 13,
    width: "100%",
    boxSizing: "border-box",
  };
  const [echo, setEcho] = useState(String(detail.ai_credits ?? 0));
  const [isGm, setIsGm] = useState(Boolean(detail.is_gm));
  const [email, setEmail] = useState(detail.email || "");

  useEffect(() => {
    setEcho(String(detail.ai_credits ?? 0));
    setIsGm(Boolean(detail.is_gm));
    setEmail(detail.email || "");
  }, [detail.id, detail.ai_credits, detail.is_gm, detail.email]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Play account (in-game)</div>
      <label style={{ fontSize: 11, color: COLORS.textMuted }}>Email (optional)</label>
      <input value={email} onChange={(e) => setEmail(e.target.value)} style={inp} disabled={disabled} />
      <label style={{ fontSize: 11, color: COLORS.textMuted }}>AI art credits (ai_credits)</label>
      <input value={echo} onChange={(e) => setEcho(e.target.value)} style={inp} disabled={disabled} />
      <div
        style={{
          padding: "10px 12px",
          borderRadius: 8,
          border: `1px solid ${COLORS.border}`,
          background: COLORS.bgInput,
        }}
      >
        <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 6 }}>
          Grant purchase bundle{economy ? <span style={{ fontFamily: "'JetBrains Mono', monospace", color: COLORS.textDim }}> ({economy.credits_per_usd} {economy.currency_display_name} ≈ $1 list)</span> : null}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {bundles.length === 0 ? (
            <span style={{ fontSize: 11, color: COLORS.textDim }}>No bundles configured ([[credit_bundles]] in config/comfyui.toml).</span>
          ) : null}
          {bundles.map((b) => (
            <button
              key={b.id}
              type="button"
              disabled={disabled}
              title={`${b.credits} credits — ${b.blurb}`}
              onClick={() => {
                if (window.confirm(`Grant ${b.credits} credits (${b.label}) to ${detail.username}?`)) {
                  onGrantBundleCredits?.(b.credits);
                }
              }}
              style={{
                padding: "6px 10px",
                borderRadius: 6,
                border: `1px solid ${COLORS.accent}55`,
                background: "rgba(124,106,239,0.12)",
                color: COLORS.text,
                fontSize: 12,
                fontWeight: 600,
                cursor: disabled ? "wait" : "pointer",
                fontFamily: "'DM Sans', sans-serif",
              }}
            >
              {b.label}
              <span style={{ display: "block", fontSize: 9, fontWeight: 500, color: COLORS.textMuted, marginTop: 2 }}>
                +{b.credits} {economy?.currency_display_name || "credits"} · {b.blurb}
              </span>
            </button>
          ))}
        </div>
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: COLORS.text, cursor: "pointer" }}>
        <input type="checkbox" checked={isGm} onChange={(e) => setIsGm(e.target.checked)} disabled={disabled} />
        Game Master play account (pink crown in player client)
      </label>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSave({
          ai_credits: parseInt(echo, 10) || 0,
          is_gm: isGm,
          email: email.trim() || null,
        })}
        style={{
          alignSelf: "start",
          padding: "8px 16px",
          background: COLORS.accent,
          color: "#fff",
          border: "none",
          borderRadius: 6,
          fontWeight: 600,
          cursor: disabled ? "wait" : "pointer",
        }}
      >
        Save account
      </button>
    </div>
  );
}

function CharacterEditCard({ c, disabled, onSave }) {
  const { colors: COLORS } = useAdminTheme();
  const [statsJson, setStatsJson] = useState(() => JSON.stringify(c.stats ?? {}, null, 2));
  const inp = {
    padding: "8px 10px",
    background: COLORS.bgInput,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 6,
    color: COLORS.text,
    fontSize: 13,
    width: "100%",
    boxSizing: "border-box",
  };
  const [room, setRoom] = useState(c.room_id || "");
  const [pvp, setPvp] = useState(Boolean(c.pvp_enabled));
  const [portraitUrl, setPortraitUrl] = useState(c.portrait_url || "");
  const [portraitPrompt, setPortraitPrompt] = useState(c.portrait_prompt || "");

  useEffect(() => {
    setRoom(c.room_id || "");
    setPvp(Boolean(c.pvp_enabled));
    setPortraitUrl(c.portrait_url || "");
    setPortraitPrompt(c.portrait_prompt || "");
    setStatsJson(JSON.stringify(c.stats ?? {}, null, 2));
  }, [c.id, c.room_id, c.pvp_enabled, c.portrait_url, c.portrait_prompt, c.stats]);

  return (
    <div style={{ marginBottom: 14, padding: 12, background: COLORS.bgInput, borderRadius: 8, border: `1px solid ${COLORS.border}` }}>
      <div style={{ fontWeight: 600, color: COLORS.forge, marginBottom: 8 }}>{c.name}</div>
      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>room_id</div>
        <input value={room} onChange={(e) => setRoom(e.target.value)} style={{ ...inp, padding: "6px 8px", fontSize: 12 }} disabled={disabled} />
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, fontSize: 12, color: COLORS.text, cursor: "pointer" }}>
        <input type="checkbox" checked={pvp} onChange={(e) => setPvp(e.target.checked)} disabled={disabled} />
        PVP enabled
      </label>
      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Portrait URL</div>
        <input value={portraitUrl} onChange={(e) => setPortraitUrl(e.target.value)} style={{ ...inp, padding: "6px 8px", fontSize: 12 }} disabled={disabled} />
      </div>
      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Portrait prompt</div>
        <textarea value={portraitPrompt} onChange={(e) => setPortraitPrompt(e.target.value)} style={{ ...inp, minHeight: 56, resize: "vertical" }} disabled={disabled} />
      </div>
      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>
          Character stats JSON (vitals, wallet balances by currency key, world and plugin blocks)
        </div>
        <textarea
          value={statsJson}
          onChange={(e) => setStatsJson(e.target.value)}
          style={{ ...inp, minHeight: 120, resize: "vertical", fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}
          disabled={disabled}
          spellCheck={false}
        />
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => {
          let statsParsed = null;
          try {
            statsParsed = JSON.parse(statsJson);
          } catch {
            window.alert("Stats JSON is invalid — fix syntax before saving.");
            return;
          }
          if (statsParsed !== null && typeof statsParsed !== "object") {
            window.alert("Stats JSON must be an object.");
            return;
          }
          onSave({
          room_id: room.trim(),
          pvp_enabled: pvp,
          portrait_url: portraitUrl.trim() || null,
          portrait_prompt: portraitPrompt.trim() || null,
          stats: statsParsed,
        });
        }}
        style={{
          marginTop: 10,
          padding: "6px 12px",
          background: COLORS.success,
          color: "#0a0a0f",
          border: "none",
          borderRadius: 6,
          fontWeight: 600,
          fontSize: 12,
          cursor: disabled ? "wait" : "pointer",
        }}
      >
        Save character
      </button>
    </div>
  );
}
