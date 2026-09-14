import { useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import { API_BASE } from "../apiConfig.js";
import { ActionButton, FetchErrorBanner, StatCard, Icons } from "../adminCommon.jsx";

// Economy › Money: each of the world's currencies summed across saved characters, with the
// biggest holders. Saved characters trail live play by up to about a minute.

const mono = "'JetBrains Mono', monospace";

export default function MoneyPage() {
  const { colors: COLORS } = useAdminTheme();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let alive = true;
    axios.get(`${API_BASE}/admin/economy/money`)
      .then(({ data: d }) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => alive && setError(e?.response?.data?.detail || e.message));
    return () => { alive = false; };
  }, [version]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 1100 }}>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Money</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", maxWidth: 780 }}>
            How much of each currency exists across {data ? data.characters.toLocaleString() : "…"} saved characters, and who holds the most. Saved characters are updated about once a minute. Shop takings are under Shops.
          </p>
        </div>
        <span style={{ marginLeft: "auto" }}><ActionButton small variant="ghost" icon={<Icons.Refresh />} onClick={() => setVersion((v) => v + 1)}>Refresh</ActionButton></span>
      </div>
      <FetchErrorBanner error={error} label="money" />
      {data && data.currencies.length === 0 && <div style={{ fontSize: 13, color: COLORS.textMuted }}>This world has no currencies.</div>}
      {(data?.currencies || []).map((c) => (
        <section key={c.key} style={{ background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: COLORS.text }}>{c.name} <span style={{ fontFamily: mono, fontSize: 11, color: COLORS.textDim }}>{c.key}</span></h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
            <StatCard label="In circulation" value={c.total.toLocaleString()} color={COLORS.accent} icon={<Icons.Items />} />
            <StatCard label="Characters holding any" value={c.holders.toLocaleString()} color={COLORS.info} icon={<Icons.Players />} />
            <StatCard label="Average per character" value={c.average.toLocaleString()} color={COLORS.success} icon={<Icons.Players />} />
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, fontFamily: mono, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Biggest holders</div>
            {c.top.length === 0 ? <div style={{ fontSize: 12, color: COLORS.textDim }}>Nobody holds any.</div> : (
              <ol style={{ margin: 0, paddingLeft: 22, display: "flex", flexDirection: "column", gap: 3 }}>
                {c.top.map((t) => (
                  <li key={t.id} style={{ fontSize: 13, color: COLORS.text }}>
                    <a href={t.href} style={{ color: COLORS.accent }}>{t.name}</a>
                    <span style={{ fontFamily: mono, marginLeft: 10 }}>{t.amount.toLocaleString()}</span>
                    <span style={{ fontSize: 11, color: COLORS.textDim, marginLeft: 8 }}>{c.total ? `${Math.round((t.amount / c.total) * 100)}%` : ""}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>
      ))}
    </div>
  );
}
