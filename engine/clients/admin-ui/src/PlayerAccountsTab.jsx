import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";

/** Matches server comfyui.toml default: 100 pixels ≈ US $1 at list. */
const PIXELS_PER_USD_REF = 100;
const ADMIN_PIXEL_PURCHASE_BUNDLES = [
  { id: "starter", label: "$4.99", pixels: 500, blurb: "~100 px/$" },
  { id: "standard", label: "$9.99", pixels: 1000, blurb: "100 px/$" },
  { id: "plus", label: "$19.99", pixels: 2200, blurb: "+10% vs straight rate" },
  { id: "best", label: "$49.99", pixels: 5750, blurb: "+15% vs straight rate" },
];

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
export default function PlayerAccountsTab({ focusTarget = null }) {
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
  const [err, setErr] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailErr, setDetailErr] = useState("");
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(async () => {
    setErr("");
    const url = `${API_BASE}/admin/player-accounts`;
    try {
      const { data } = await axios.get(url);
      setRows(Array.isArray(data) ? data : []);
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
    }
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

  const grantBundlePixels = async (pixels) => {
    if (selectedId == null || pixels <= 0) return;
    setBusy(true);
    try {
      await axios.patch(`${API_BASE}/admin/player-accounts/${selectedId}`, { echo_credits_add: pixels });
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
        <div style={{ padding: "10px 12px", borderBottom: `1px solid ${COLORS.border}`, fontSize: 12, color: COLORS.textMuted }}>
          Play accounts — pick one; editor is <strong style={{ color: COLORS.text }}>below</strong> (full width so nothing is clipped).
        </div>
        {err && <div style={{ padding: 12, color: COLORS.danger, fontSize: 12 }}>{String(err)}</div>}
        <div style={{ maxHeight: 260, overflowY: "auto" }}>
          {rows.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setSelectedId(r.id)}
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
                {r.is_gm ? (
                  <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "rgba(244,114,182,0.2)", color: "#f9a8d4", border: "1px solid rgba(244,114,182,0.45)" }}>👑 GM</span>
                ) : null}
              </div>
              <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4, fontFamily: "'JetBrains Mono', monospace" }}>
                id {r.id} · {r.character_count} chars · pixels {r.echo_credits}
              </div>
            </button>
          ))}
          {rows.length === 0 && !err && <div style={{ padding: 16, color: COLORS.textMuted, fontSize: 13 }}>No accounts</div>}
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
            Select an account above for <strong style={{ color: COLORS.text }}>pixels</strong>, <strong style={{ color: COLORS.text }}>bundles</strong>, <strong style={{ color: COLORS.text }}>GM crown</strong>, Nexus console access, and characters.
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

            <ConsoleAccessSection detail={detail} accountId={selectedId} disabled={busy} onChanged={reloadAccount} />

            <AccountEditForm
              detail={detail}
              disabled={busy}
              onSave={saveAccount}
              onGrantBundlePixels={grantBundlePixels}
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

function AccountEditForm({ detail, disabled, onSave, onGrantBundlePixels }) {
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
  const [echo, setEcho] = useState(String(detail.echo_credits ?? 0));
  const [isGm, setIsGm] = useState(Boolean(detail.is_gm));
  const [email, setEmail] = useState(detail.email || "");

  useEffect(() => {
    setEcho(String(detail.echo_credits ?? 0));
    setIsGm(Boolean(detail.is_gm));
    setEmail(detail.email || "");
  }, [detail.id, detail.echo_credits, detail.is_gm, detail.email]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Play account (in-game)</div>
      <label style={{ fontSize: 11, color: COLORS.textMuted }}>Email (optional)</label>
      <input value={email} onChange={(e) => setEmail(e.target.value)} style={inp} disabled={disabled} />
      <label style={{ fontSize: 11, color: COLORS.textMuted }}>Pixel balance (echo_credits)</label>
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
          Grant purchase bundle <span style={{ fontFamily: "'JetBrains Mono', monospace", color: COLORS.textDim }}>({PIXELS_PER_USD_REF} px ≈ $1 list)</span>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {ADMIN_PIXEL_PURCHASE_BUNDLES.map((b) => (
            <button
              key={b.id}
              type="button"
              disabled={disabled}
              title={`${b.pixels} pixels — ${b.blurb}`}
              onClick={() => {
                if (window.confirm(`Grant ${b.pixels} pixels (${b.label}) to ${detail.username}?`)) {
                  onGrantBundlePixels?.(b.pixels);
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
                +{b.pixels} px · {b.blurb}
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
          echo_credits: parseInt(echo, 10) || 0,
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
  const [digi, setDigi] = useState(String(c.digi_balance ?? 0));
  const [rep, setRep] = useState(String(c.reputation ?? 0));
  const [room, setRoom] = useState(c.room_id || "");
  const [pvp, setPvp] = useState(Boolean(c.pvp_enabled));
  const [portraitUrl, setPortraitUrl] = useState(c.portrait_url || "");
  const [portraitPrompt, setPortraitPrompt] = useState(c.portrait_prompt || "");

  useEffect(() => {
    setDigi(String(c.digi_balance ?? 0));
    setRep(String(c.reputation ?? 0));
    setRoom(c.room_id || "");
    setPvp(Boolean(c.pvp_enabled));
    setPortraitUrl(c.portrait_url || "");
    setPortraitPrompt(c.portrait_prompt || "");
    setStatsJson(JSON.stringify(c.stats ?? {}, null, 2));
  }, [c.id, c.digi_balance, c.reputation, c.room_id, c.pvp_enabled, c.portrait_url, c.portrait_prompt, c.stats]);

  return (
    <div style={{ marginBottom: 14, padding: 12, background: COLORS.bgInput, borderRadius: 8, border: `1px solid ${COLORS.border}` }}>
      <div style={{ fontWeight: 600, color: COLORS.forge, marginBottom: 8 }}>{c.name}</div>
      <div style={{ display: "grid", gap: 8, gridTemplateColumns: "1fr 1fr" }}>
        <div>
          <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Digi</div>
          <input value={digi} onChange={(e) => setDigi(e.target.value)} style={{ ...inp, padding: "6px 8px", fontSize: 12 }} disabled={disabled} />
        </div>
        <div>
          <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 4 }}>Reputation</div>
          <input value={rep} onChange={(e) => setRep(e.target.value)} style={{ ...inp, padding: "6px 8px", fontSize: 12 }} disabled={disabled} />
        </div>
      </div>
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
          Character stats JSON (legacy + <code style={{ color: COLORS.text }}>conduit</code> proficiency block)
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
          digi_balance: parseInt(digi, 10) || 0,
          reputation: parseInt(rep, 10) || 0,
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
