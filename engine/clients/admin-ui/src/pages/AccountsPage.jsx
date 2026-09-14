import { useEffect, useState } from "react";
import { useAdminTheme } from "../AdminThemeContext.jsx";
import PlayerAccountsTab from "../PlayerAccountsTab.jsx";

// Players › Accounts: game accounts (suspension, AI art credits, console access, characters).
// #/accounts/<id> opens that account, so other pages can link to it.

const accountFromHash = () => {
  const id = Number(window.location.hash.replace(/^#\/?/, "").split("/")[1]);
  return Number.isInteger(id) && id > 0 ? id : null;
};

export default function AccountsPage() {
  const { colors: COLORS } = useAdminTheme();
  const [focus, setFocus] = useState(() => {
    const id = accountFromHash();
    return id ? { accountId: id, nonce: Date.now() } : null;
  });
  useEffect(() => {
    const onHash = () => {
      const id = accountFromHash();
      if (id) setFocus({ accountId: id, nonce: Date.now() });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'Space Grotesk', sans-serif" }}>Accounts</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: COLORS.textMuted, fontFamily: "'DM Sans', sans-serif", maxWidth: 820 }}>Game accounts: suspension, AI art credits, Nexus console access for this login, and characters. Staff logins are under Team &amp; access.</p>
      </div>
      <PlayerAccountsTab focusTarget={focus} onSelect={(id) => { if (accountFromHash() !== id) window.location.hash = `/accounts/${id}`; }} />
    </div>
  );
}
