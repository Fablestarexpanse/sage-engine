import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useAdminTheme } from "./AdminThemeContext.jsx";
import { API_BASE } from "./apiConfig.js";

/** Shops admin — every shop room: keeper, wallet, stock, and the sales ledger. */

const fmtTime = (at) => {
  try {
    const d = new Date(at * 1000);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  } catch {
    return "";
  }
};

export default function ShopsTab() {
  const { colors: COLORS } = useAdminTheme();
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${API_BASE}/plugins/shop/admin/shops`);
      setRows(Array.isArray(r.data) ? r.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || e.message || "shops API failed");
    }
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  const shop = rows.find((r) => r.room_id === selected) ?? rows[0] ?? null;
  const card = { background: COLORS.bgCard, border: `1px solid ${COLORS.border}`, borderRadius: 10 };
  const cell = { padding: "6px 10px", fontSize: 12, color: COLORS.text, borderBottom: `1px solid ${COLORS.border}` };
  const th = { ...cell, color: COLORS.textMuted, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left" };
  const label = { fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(420px, 1fr) minmax(380px, 1fr)", gap: 16, alignItems: "start" }}>
      <div style={{ ...card, overflow: "hidden" }}>
        <div style={{ padding: "10px 12px", fontWeight: 700, fontSize: 13, color: COLORS.text, borderBottom: `1px solid ${COLORS.border}` }}>
          Shops {error && <span style={{ color: COLORS.danger, fontWeight: 400, marginLeft: 8 }}>{error}</span>}
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>
            <th style={th}>Shop</th><th style={th}>Keeper</th>
            <th style={th} title="Keeper wallet">Keeper wallet</th>
            <th style={th} title="Items sold to customers / revenue">Sold</th>
            <th style={th} title="Items bought from customers / spend">Bought</th>
            <th style={th}>Policy</th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.room_id} onClick={() => setSelected(r.room_id)}
                style={{ cursor: "pointer", background: (shop?.room_id === r.room_id) ? COLORS.bgInput : "transparent" }}>
                <td style={cell} title={r.room_id}>{r.shop_name}</td>
                <td style={cell}>{r.owner ? r.owner.name : <span style={{ color: COLORS.textMuted }}>house NPC</span>}</td>
                <td style={cell}>{r.owner?.money ?? "—"}</td>
                <td style={cell}>{r.sold_count} <span style={{ color: COLORS.success }}>+{r.revenue}</span></td>
                <td style={cell}>{r.bought_count} <span style={{ color: COLORS.danger }}>−{r.spend}</span></td>
                <td style={cell}>{r.buys ? `buys @ ${Math.round(r.buy_rate * 100)}%` : "sells only"}</td>
              </tr>
            ))}
            {!rows.length && <tr><td style={cell} colSpan={6}>No shop rooms found (add a shop block to a room YAML).</td></tr>}
          </tbody>
        </table>
      </div>

      {shop && (
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ ...card, padding: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: COLORS.text, marginBottom: 8 }}>
              {shop.shop_name} <span style={{ color: COLORS.textMuted, fontWeight: 400 }}>· {shop.room_id}</span>
            </div>
            {shop.owner && (
              <div style={{ fontSize: 11, color: COLORS.text, marginBottom: 10 }}>
                <div style={label}>Keeper</div>
                {shop.owner.name} — <b>{shop.owner.money ?? "?"} {shop.currency}</b>
                {shop.owner.room_id && <span style={{ color: COLORS.textMuted }}> · now in {shop.owner.room_id.split(":")[1]}</span>}
                {shop.owner.home_room && <span style={{ color: COLORS.textMuted }}> · lives at {shop.owner.home_room.split(":")[1]}</span>}
                {Array.isArray(shop.owner.inventory) && (
                  <div style={{ color: COLORS.textMuted, marginTop: 3 }}>
                    carrying: {shop.owner.inventory.join(", ") || "nothing"}
                  </div>
                )}
              </div>
            )}
            <div style={label}>Stock &amp; prices</div>
            <div style={{ fontSize: 11, color: COLORS.text }}>
              {shop.stock.map((s) => <div key={s.template}>{s.name} — {s.price} {shop.currency}</div>)}
              {!shop.stock.length && <span style={{ color: COLORS.textMuted }}>sells nothing (buyer only)</span>}
              {shop.buys && <div style={{ color: COLORS.textMuted, marginTop: 3 }}>buys most goods at {Math.round(shop.buy_rate * 100)}% of value</div>}
            </div>
            {shop.buys && (
              <>
                <div style={{ ...label, marginTop: 10 }}>Secondhand shelf <span style={{ textTransform: "none" }}>(cap {shop.stock_cap} per item)</span></div>
                <div style={{ fontSize: 11, color: COLORS.text }}>
                  {(shop.secondhand ?? []).map((s) => (
                    <div key={s.template}>
                      {s.name} <b>x{s.count}</b> — {s.price} {shop.currency} each
                      {s.count >= shop.stock_cap && <span style={{ color: COLORS.warning }}> · full</span>}
                    </div>
                  ))}
                  {!(shop.secondhand ?? []).length && <span style={{ color: COLORS.textMuted }}>empty — nothing bought in yet</span>}
                </div>
              </>
            )}
          </div>

          <div style={{ ...card, padding: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 12, color: COLORS.text, marginBottom: 6 }}>
              Ledger <span style={{ color: COLORS.textMuted, fontWeight: 400 }}>
                — sold {shop.sold_count} (+{shop.revenue} {shop.currency}) · bought {shop.bought_count} (−{shop.spend} {shop.currency})
              </span>
            </div>
            <div style={{ maxHeight: 240, overflow: "auto", fontSize: 11, fontFamily: "monospace" }}>
              {shop.ledger.map((e, i) => (
                <div key={i} style={{ display: "flex", gap: 8, padding: "2px 0", borderBottom: `1px solid ${COLORS.border}22` }}>
                  <span style={{ color: COLORS.textMuted }}>{fmtTime(e.at)}</span>
                  <span style={{ color: e.kind === "sale" ? COLORS.success : COLORS.danger, width: 62 }}>
                    {e.kind === "sale" ? "sold" : "bought"}
                  </span>
                  <span style={{ color: COLORS.text, flex: 1 }}>{e.item}</span>
                  <span style={{ color: COLORS.textMuted }}>{e.kind === "sale" ? "to" : "from"} {e.actor}</span>
                  <span style={{ color: COLORS.text }}>{e.price} {shop.currency}</span>
                </div>
              ))}
              {!shop.ledger.length && <span style={{ color: COLORS.textMuted }}>No transactions yet.</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
