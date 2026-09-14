import { useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { Icons, ActionButton, DataTable, FetchErrorBanner } from "../adminCommon.jsx";

// Economy › AI art credits: what players pay for generated portraits and scenes, and the bundles
// staff grant. Separate from the world's in-game money. Stored in config/comfyui.toml.

const FIELDS = [
  ["currency_display_name", "Credit name shown to players", "text"],
  ["starting_ai_credits", "Starting credits (new accounts)", "number"],
  ["portrait_generation_cost", "Portrait cost", "number"],
  ["area_generation_cost", "Scene cost", "number"],
  ["character_create_portrait_cost", "Character creation portrait cost", "number"],
  ["credits_per_usd", "Credits per USD (reference only)", "number"],
];

export default function CreditsPage() {
  const { colors: COLORS } = useAdminTheme();
  const [form, setForm] = useState(null);
  const [bundles, setBundles] = useState([]);
  const [error, setError] = useState(null);
  const [persist, setPersist] = useState(true);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/comfyui/status`)
      .then(({ data }) => alive && setForm(Object.fromEntries([["economy_enabled", !!data.economy_enabled], ...FIELDS.map(([k]) => [k, data[k] ?? ""])])))
      .catch((e) => alive && setError(e?.response?.data?.detail || e.message));
    axios.get(`${API_BASE}/admin/economy`)
      .then(({ data }) => alive && setBundles(data.credit_bundles || []))
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const save = async () => {
    setBusy(true);
    setNote("");
    try {
      const body = { economy_enabled: form.economy_enabled };
      for (const [k, , type] of FIELDS) body[k] = type === "number" ? Number(form[k]) : form[k];
      await axios.patch(`${API_BASE}/comfyui/settings?persist=${persist}`, body);
      setNote(persist ? "Saved to config/comfyui.toml." : "Applied until the server restarts.");
    } catch (e) {
      setNote(e.response?.data?.detail || e.message || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const inp = { width: "100%", padding: "8px 10px", background: COLORS.bgInput, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13, fontFamily: "'DM Sans', sans-serif" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 900 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>AI art credits</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>What players spend on generated portraits and scene images. This is not the world&apos;s in-game money. Grant credits to a player from Players › Accounts.</p>
      </div>
      <FetchErrorBanner error={error} label="credit settings" />
      {form && (
        <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: COLORS.text, cursor: "pointer" }}>
            <input id="credits-enabled" type="checkbox" checked={form.economy_enabled} onChange={(e) => setForm((f) => ({ ...f, economy_enabled: e.target.checked }))} />
            Charge credits for generation
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
            {FIELDS.map(([k, label, type]) => (
              <div key={k}>
                <label htmlFor={`credits-${k}`} style={{ fontSize: 11, color: COLORS.textMuted, display: "block", marginBottom: 4 }}>{label}</label>
                <input id={`credits-${k}`} type={type} min={type === "number" ? 0 : undefined} value={form[k]} onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} style={inp} />
              </div>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: COLORS.textMuted, cursor: "pointer" }}>
              <input id="credits-persist" type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
              Save to config/comfyui.toml
            </label>
            <ActionButton variant="primary" icon={<Icons.Save />} onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</ActionButton>
            {note && <span style={{ fontSize: 12, color: COLORS.textMuted }}>{note}</span>}
          </div>
        </div>
      )}
      <div style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <div style={{ padding: "12px 16px", fontSize: 14, fontWeight: 600, color: COLORS.text }}>Credit bundles</div>
        {bundles.length === 0
          ? <div style={{ padding: "0 16px 16px", fontSize: 12, color: COLORS.textMuted }}>No bundles. Add <code>[[credit_bundles]]</code> entries to config/comfyui.toml.</div>
          : <DataTable columns={Object.keys(bundles[0]).map((k) => ({ label: k.replace(/_/g, " "), render: (r) => String(r[k] ?? "—") }))} rows={bundles.map((b, i) => ({ id: i, ...b }))} />}
      </div>
    </div>
  );
}
