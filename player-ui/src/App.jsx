import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { usePlayTheme } from "./PlayThemeContext.jsx";
import {
  playLogin,
  playDevLogin,
  playDevStatus,
  playRegister,
  playWebSocketUrl,
  playMediaUrl,
  playComfyuiStatus,
  playGeneratePortrait,
  playSuggestPortraitPrompt,
  playCreateCharacter,
  playDeleteCharacter,
  playRefreshSession,
  playGenerateSceneImage,
  playFetchProficiencyCatalog,
  playApiBaseUrl,
  getPlayToken,
} from "./playApi.js";
import { ChargenProficienciesStep } from "./ChargenProficienciesStep.jsx";
import FablestarClient from "./mud/FablestarClient.jsx";
import { GmBadge } from "./GmBadge.jsx";
import { DEFAULT_NARRATIVE } from "./mud/03-narrative.jsx";
import { PORTRAIT_ASPECT_RATIO_CSS } from "./portraitProfile.js";
import { ReputationThermometer } from "./ReputationThermometer.jsx";
import { FloatingThemeToggle, ThemeToggleButton } from "./ThemeToggleButton.jsx";

/** Account-wide art balance (pixels / echo_credits): one place, not per character. */
function AccountArtCreditsBar({ echoEconomy, gameCurrencyLabel, onTopUp }) {
  const { T } = usePlayTheme();
  if (echoEconomy?.credits == null) return null;
  const lab = echoEconomy.label || "pixels";
  const gameLab = gameCurrencyLabel || "Digi";
  const n = echoEconomy.credits;
  const low = n < (echoEconomy.warnBelow ?? 12);
  return (
    <div
      style={{
        marginBottom: 16,
        padding: "14px 16px",
        borderRadius: T.radius.lg,
        border: `1px solid ${T.currency.pixel.border}`,
        background: `linear-gradient(135deg, ${T.currency.pixel.bg}, ${T.bg.panel})`,
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: 14,
        justifyContent: "space-between",
      }}
    >
      <div style={{ flex: "1 1 200px", minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: T.currency.pixel.fg, fontFamily: T.font.body }}>
          Pixels <span style={{ color: T.text.muted, fontWeight: 400 }}>(your account)</span>
        </div>
        <p style={{ margin: "6px 0 0", fontSize: 12, color: T.text.muted, lineHeight: 1.5, fontFamily: T.font.body }}>
          Same balance for every character. Spent when you use AI portrait or scene generation (separate from in-world{" "}
          <span style={{ color: T.currency.digi.fg, fontWeight: 600 }}>{gameLab}</span>).
        </p>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: T.currency.pixel.label, fontFamily: T.font.body }}>{lab}</div>
          <div
            style={{
              fontSize: 26,
              fontFamily: T.font.mono,
              fontWeight: 700,
              color: low ? T.currency.pixel.warn : T.currency.pixel.fg,
              lineHeight: 1.1,
            }}
          >
            {n}
          </div>
        </div>
        <button
          type="button"
          onClick={onTopUp}
          style={{
            padding: "8px 14px",
            borderRadius: T.radius.md,
            border: `1px solid ${T.currency.pixel.border}`,
            background: T.bg.deep,
            color: T.currency.pixel.fg,
            fontSize: 11,
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: T.font.body,
            whiteSpace: "nowrap",
          }}
        >
          How to add more
        </button>
      </div>
    </div>
  );
}

/** Per-character row: saved position + level (readable). Pixel balance lives in AccountArtCreditsBar. */
function ChooseCharacterGlassStats({ character, selected, onSelectRow }) {
  const { T } = usePlayTheme();
  const full = String(character.room_id || "").trim() || "—";
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${character.name}: last position; click to select`}
      onClick={() => onSelectRow(character.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelectRow(character.id);
        }
      }}
      style={{
        flex: 1,
        minWidth: 0,
        padding: "12px 14px",
        cursor: "pointer",
        borderLeft: `1px solid ${T.border.subtle}`,
        background: selected ? `${T.glyph.violet}12` : T.bg.surface,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 9,
              color: T.text.muted,
              fontWeight: 600,
              letterSpacing: "0.08em",
              marginBottom: 6,
              fontFamily: T.font.body,
            }}
          >
            Last saved position
          </div>
          <div
            title={full}
            style={{
              fontSize: 12,
              fontFamily: T.font.mono,
              color: T.text.secondary,
              lineHeight: 1.45,
              wordBreak: "break-word",
            }}
          >
            {full}
          </div>
        </div>
        <div
          style={{
            flexShrink: 0,
            textAlign: "center",
            padding: "8px 12px",
            borderRadius: T.radius.md,
            border: `1px solid ${T.border.dim}`,
            background: selected ? T.bg.panel : T.bg.void,
            minWidth: 56,
          }}
        >
          <div
            style={{
              fontSize: 8,
              color: T.text.muted,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              fontFamily: T.font.body,
              marginBottom: 2,
            }}
          >
            Level
          </div>
          <div style={{ fontSize: 17, fontWeight: 700, fontFamily: T.font.display, color: T.glyph.violet }}>—</div>
        </div>
      </div>
    </div>
  );
}

function parseHashAuthRoute() {
  const raw = (window.location.hash || "#").replace(/^#/, "").replace(/^\//, "");
  if (raw === "register") return "register";
  if (raw === "login") return "login";
  return "home";
}

function useHashAuthRoute() {
  const [route, setRoute] = useState(parseHashAuthRoute);
  useEffect(() => {
    const sync = () => setRoute(parseHashAuthRoute());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  return route;
}

function useAuthChrome() {
  const { T } = usePlayTheme();
  return useMemo(
    () => ({
      T,
      fullScreenShell: {
        flex: 1,
        minHeight: 0,
        width: "100%",
        height: "100%",
        background: T.bg.void,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: T.font.body,
        padding: 24,
        boxSizing: "border-box",
      },
      card: {
        width: "100%",
        maxWidth: 400,
        background: T.bg.panel,
        border: `1px solid ${T.border.dim}`,
        borderRadius: T.radius.xl,
        boxShadow: T.shadow.panel,
        padding: "28px 28px 24px",
      },
      input: {
        width: "100%",
        padding: "10px 12px",
        borderRadius: T.radius.md,
        border: `1px solid ${T.border.medium}`,
        background: T.bg.surface,
        color: T.text.primary,
        fontFamily: T.font.mono,
        fontSize: 13,
        outline: "none",
      },
    }),
    [T]
  );
}

function AuthBrandHeader({ subtitle }) {
  const { T } = usePlayTheme();
  return (
    <div style={{ textAlign: "center", marginBottom: 22 }}>
      <div style={{ fontSize: 28, color: T.glyph.violet, marginBottom: 6 }}>◈</div>
      <h1 style={{ fontFamily: T.font.display, fontSize: 22, color: T.text.primary, letterSpacing: "0.12em", fontWeight: 700 }}>FABLESTAR</h1>
      {subtitle != null && subtitle !== "" && (
        <p style={{ fontSize: 11, color: T.text.muted, marginTop: 6 }}>{subtitle}</p>
      )}
    </div>
  );
}

function AuthNavLinks({ children }) {
  return (
    <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8, alignItems: "center" }}>
      {children}
    </div>
  );
}

function AuthTextLink({ href, children }) {
  const { T } = usePlayTheme();
  return (
    <a
      href={href}
      style={{ fontSize: 11, color: T.text.muted, fontFamily: T.font.body, textDecoration: "none", borderBottom: `1px solid ${T.border.dim}` }}
    >
      {children}
    </a>
  );
}

function AuthLanding() {
  const { T, fullScreenShell, card } = useAuthChrome();
  return (
    <div style={fullScreenShell}>
      <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&family=Exo+2:wght@600;700&family=Oxanium:wght@500;600;700&display=swap" rel="stylesheet" />
      <div style={card}>
        <AuthBrandHeader subtitle="Expanse — enter your conduit" />
        <p style={{ fontSize: 12, color: T.text.secondary, lineHeight: 1.55, margin: "0 0 20px", textAlign: "center" }}>
          Sign in or register. After authentication you will choose or create a character before entering the world.
        </p>
        {import.meta.env.DEV && (
          <p
            style={{
              fontSize: 11,
              color: T.text.muted,
              lineHeight: 1.55,
              margin: "0 0 18px",
              padding: "10px 12px",
              borderRadius: T.radius.md,
              border: `1px dashed ${T.border.dim}`,
              background: T.bg.surface,
            }}
          >
            <strong style={{ color: T.text.secondary }}>Nexus dev_mode</strong> (auto on first start):{" "}
            <strong style={{ color: T.text.primary }}>staff</strong> / <code style={{ fontSize: 10 }}>test</code> (GM),{" "}
            <strong style={{ color: T.text.primary }}>player</strong> / <code style={{ fontSize: 10 }}>test</code>.
            <br />
            Optional:{" "}
            <code style={{ fontSize: 10, color: T.text.secondary }}>python scripts/ensure_test_user.py</code> →{" "}
            <strong style={{ color: T.text.primary }}>test</strong> / test, <strong style={{ color: T.text.primary }}>demo</strong> / demo.
          </p>
        )}
        <a
          href="#/login"
          style={{
            display: "block",
            width: "100%",
            boxSizing: "border-box",
            textAlign: "center",
            padding: "11px",
            borderRadius: T.radius.md,
            border: "none",
            cursor: "pointer",
            marginBottom: 10,
            background: `linear-gradient(135deg,${T.glyph.violet},${T.glyph.cyan})`,
            color: "#0a0a0f",
            fontWeight: 700,
            fontFamily: T.font.body,
            fontSize: 12,
            letterSpacing: "0.06em",
            textDecoration: "none",
          }}
        >
          Sign in
        </a>
        <a
          href="#/register"
          style={{
            display: "block",
            width: "100%",
            boxSizing: "border-box",
            textAlign: "center",
            padding: "11px",
            borderRadius: T.radius.md,
            border: `1px solid ${T.border.medium}`,
            cursor: "pointer",
            background: T.bg.surface,
            color: T.text.primary,
            fontWeight: 600,
            fontFamily: T.font.body,
            fontSize: 12,
            letterSpacing: "0.04em",
            textDecoration: "none",
          }}
        >
          Create account
        </a>
      </div>
    </div>
  );
}

function mapPlayAuthPayload(res) {
  return {
    username: res.username,
    accountId: res.account_id,
    characters: res.characters || [],
    echoCredits: res.echo_credits,
    currencyDisplayName: res.currency_display_name,
    gameCurrencyDisplayName: res.game_currency_display_name,
    pixelsPerUsd: typeof res.pixels_per_usd === "number" ? res.pixels_per_usd : 100,
    isGm: Boolean(res.is_gm),
  };
}

function AuthSignInForm({ onLoggedIn }) {
  const { T, fullScreenShell, card, input: authInputStyle } = useAuthChrome();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [devEnabled, setDevEnabled] = useState(false);
  const [devName, setDevName] = useState("Dev Tester");

  useEffect(() => {
    let alive = true;
    playDevStatus().then((ok) => alive && setDevEnabled(ok));
    return () => {
      alive = false;
    };
  }, []);

  const devLogin = async () => {
    setError("");
    setBusy(true);
    try {
      const res = await playDevLogin(devName.trim());
      if (!res.ok) {
        setError(res.error || "Dev login failed");
        setBusy(false);
        return;
      }
      onLoggedIn(mapPlayAuthPayload(res), "", res.character_id);
    } catch (err) {
      setError(err.message || "Network error — is the Nexus running?");
    }
    setBusy(false);
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const u = username.trim();
      const p = password.trim();
      const res = await playLogin(u, p);
      if (!res.ok) {
        setError(res.error === "invalid_credentials" ? "Unknown user or wrong password." : res.error || "Login failed");
        setBusy(false);
        return;
      }
      onLoggedIn(mapPlayAuthPayload(res), p);
    } catch (err) {
      setError(err.message || "Network error — is the Nexus running?");
    }
    setBusy(false);
  };

  return (
    <div style={fullScreenShell}>
      <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&family=Exo+2:wght@600;700&family=Oxanium:wght@500;600;700&display=swap" rel="stylesheet" />
      <div style={card}>
        <AuthBrandHeader subtitle="Sign in to continue" />
        <p style={{ margin: "0 0 16px", fontSize: 12, color: T.text.muted, lineHeight: 1.45 }}>
          Username and password are case-sensitive. Leading/trailing spaces are ignored.
        </p>
        <p style={{ margin: "0 0 14px", fontSize: 10, color: T.text.muted, lineHeight: 1.45, fontFamily: T.font.mono }}>
          Login API: {playApiBaseUrl()}
        </p>
        {import.meta.env.DEV && (
          <p
            style={{
              fontSize: 10,
              color: T.text.secondary,
              lineHeight: 1.5,
              margin: "0 0 14px",
              padding: "8px 10px",
              borderRadius: T.radius.md,
              border: `1px dashed ${T.border.dim}`,
              background: T.bg.surface,
            }}
          >
            Try <strong>staff</strong> / <code style={{ fontSize: 9 }}>test</code> or <strong>player</strong> /{" "}
            <code style={{ fontSize: 9 }}>test</code> (created by Nexus dev_mode). If those fail, run{" "}
            <code style={{ fontSize: 9 }}>python scripts/ensure_test_user.py</code> then use <strong>test</strong> / test or{" "}
            <strong>demo</strong> / demo.
          </p>
        )}
        <form onSubmit={submit}>
          <label style={{ display: "block", fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Username</label>
          <input
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ ...authInputStyle, marginBottom: 14 }}
          />
          <label style={{ display: "block", fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Password</label>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ ...authInputStyle, marginBottom: 18 }}
          />
          {error && <div role="alert" style={{ fontSize: 12, color: T.text.danger, marginBottom: 12 }}>{error}</div>}
          <button
            type="submit"
            disabled={busy}
            style={{
              width: "100%",
              padding: "11px",
              borderRadius: T.radius.md,
              border: "none",
              cursor: busy ? "wait" : "pointer",
              background: `linear-gradient(135deg,${T.glyph.violet},${T.glyph.cyan})`,
              color: "#0a0a0f",
              fontWeight: 700,
              fontFamily: T.font.body,
              fontSize: 12,
              letterSpacing: "0.06em",
            }}
          >
            {busy ? "…" : "Sign in"}
          </button>
        </form>
        {devEnabled && (
          <div
            data-testid="dev-login"
            style={{
              marginTop: 16,
              padding: "10px",
              borderRadius: T.radius.md,
              border: `1px dashed ${T.glyph.amber}`,
              background: T.bg.surface,
            }}
          >
            <label style={{ display: "block", fontSize: 10, color: T.glyph.amber, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
              Dev login (no password, localhost only)
            </label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                aria-label="Dev character name"
                value={devName}
                onChange={(e) => setDevName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    devLogin();
                  }
                }}
                style={{ ...authInputStyle, marginBottom: 0, flex: 1 }}
              />
              <button
                type="button"
                disabled={busy || devName.trim().length < 2}
                onClick={devLogin}
                style={{
                  padding: "0 14px",
                  borderRadius: T.radius.md,
                  border: `1px solid ${T.glyph.amber}`,
                  background: "transparent",
                  color: T.glyph.amber,
                  fontWeight: 700,
                  fontFamily: T.font.body,
                  fontSize: 12,
                  cursor: busy ? "wait" : "pointer",
                }}
              >
                Play
              </button>
            </div>
          </div>
        )}
        <AuthNavLinks>
          <AuthTextLink href="#/register">New conduit? Create account</AuthTextLink>
          <AuthTextLink href="#/">Back to welcome</AuthTextLink>
        </AuthNavLinks>
      </div>
    </div>
  );
}

function AuthRegisterForm({ onLoggedIn }) {
  const { T, fullScreenShell, card, input: authInputStyle } = useAuthChrome();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    const u = username.trim();
    const p = password.trim();
    const p2 = password2.trim();
    if (p !== p2) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const res = await playRegister(u, p);
      if (!res.ok) {
        setError(res.error === "username_taken" ? "That name is already taken." : res.error || "Register failed");
        setBusy(false);
        return;
      }
      onLoggedIn(mapPlayAuthPayload(res), p);
    } catch (err) {
      setError(err.message || "Network error — is the Nexus running?");
    }
    setBusy(false);
  };

  return (
    <div style={fullScreenShell}>
      <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&family=Exo+2:wght@600;700&family=Oxanium:wght@500;600;700&display=swap" rel="stylesheet" />
      <div style={card}>
        <AuthBrandHeader subtitle="Create your play account" />
        <p style={{ fontSize: 12, color: T.text.muted, lineHeight: 1.5, margin: "0 0 16px", textAlign: "center" }}>
          Choose a username and password. You will create or pick a character on the next screen.
        </p>
        <form onSubmit={submit}>
          <label style={{ display: "block", fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Username</label>
          <input
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ ...authInputStyle, marginBottom: 14 }}
          />
          <label style={{ display: "block", fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Password</label>
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ ...authInputStyle, marginBottom: 12 }}
          />
          <label style={{ display: "block", fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Confirm password</label>
          <input
            type="password"
            autoComplete="new-password"
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
            style={{ ...authInputStyle, marginBottom: 18 }}
          />
          {error && <div role="alert" style={{ fontSize: 12, color: T.text.danger, marginBottom: 12 }}>{error}</div>}
          <button
            type="submit"
            disabled={busy}
            style={{
              width: "100%",
              padding: "11px",
              borderRadius: T.radius.md,
              border: "none",
              cursor: busy ? "wait" : "pointer",
              background: `linear-gradient(135deg,${T.glyph.violet},${T.glyph.cyan})`,
              color: "#0a0a0f",
              fontWeight: 700,
              fontFamily: T.font.body,
              fontSize: 12,
              letterSpacing: "0.06em",
            }}
          >
            {busy ? "…" : "Create account"}
          </button>
        </form>
        <AuthNavLinks>
          <AuthTextLink href="#/login">Already registered? Sign in</AuthTextLink>
          <AuthTextLink href="#/">Back to welcome</AuthTextLink>
        </AuthNavLinks>
      </div>
    </div>
  );
}

function PlayAuthFlow({ onLoggedIn }) {
  const route = useHashAuthRoute();
  const finish = useCallback(
    (payload, pw, autoCharacterId) => {
      window.location.hash = "#/";
      onLoggedIn(payload, pw, autoCharacterId);
    },
    [onLoggedIn]
  );

  return (
    <>
      <FloatingThemeToggle />
      {route === "home" ? <AuthLanding /> : route === "login" ? <AuthSignInForm onLoggedIn={finish} /> : <AuthRegisterForm onLoggedIn={finish} />}
    </>
  );
}

function CharacterChooser({ auth, password, onCancel, onChosen, onUpdateCharacters, echoEconomy, mergeEchoFromPlayRes }) {
  const { T } = usePlayTheme();
  const { username, characters, gameCurrencyDisplayName, isGm } = auth;
  const gameCurrencyLabel = gameCurrencyDisplayName || "Digi";
  const [selectedId, setSelectedId] = useState(characters[0]?.id ?? null);
  const [view, setView] = useState(() => (characters.length ? "pick" : "create"));
  const [newName, setNewName] = useState("");
  const [portraitPrompt, setPortraitPrompt] = useState("");
  const [pendingPortraitUrl, setPendingPortraitUrl] = useState("");
  const [comfy, setComfy] = useState({ ready: false, reachable: false, pingError: "" });
  const [suggestBusy, setSuggestBusy] = useState(false);
  const [portraitGenerating, setPortraitGenerating] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [formErr, setFormErr] = useState("");
  const formLocked = suggestBusy || portraitGenerating || createBusy;
  const [postCreatePortraitWarn, setPostCreatePortraitWarn] = useState("");
  const [portraitPreviewBust, setPortraitPreviewBust] = useState(0);
  const [portraitLightboxOpen, setPortraitLightboxOpen] = useState(false);
  const [deleteBusyId, setDeleteBusyId] = useState(null);
  const [deleteErr, setDeleteErr] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleteNameConfirm, setDeleteNameConfirm] = useState("");
  const [profCatalog, setProfCatalog] = useState(null);
  const [profCatalogErr, setProfCatalogErr] = useState("");
  const [profCatalogLoading, setProfCatalogLoading] = useState(false);
  const [starterProf, setStarterProf] = useState({});
  /** create flow: identity + portrait first, then starter proficiencies, then submit */
  const [createPhase, setCreatePhase] = useState("identity");
  const prevViewRef = useRef(view);

  const onPixelsHelp = useCallback(() => {
    const lab = echoEconomy?.label || "pixels";
    const game = gameCurrencyLabel;
    window.alert(
      `${lab} (art currency) is spent when you generate character portraits or scene art with the AI (ComfyUI). ` +
        `It is not the same as in-world ${game}.\n\n` +
        "Your server host can grant more, or future progression may award it. There is no in-client purchase yet."
    );
  }, [echoEconomy?.label, gameCurrencyLabel]);

  useEffect(() => {
    let cancelled = false;
    playRefreshSession(username, password)
      .then((res) => {
        if (cancelled || !res?.ok) return;
        if (Array.isArray(res.characters)) onUpdateCharacters(res.characters);
        mergeEchoFromPlayRes?.(res);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [username, password, onUpdateCharacters, mergeEchoFromPlayRes]);

  const refreshComfy = useCallback(() => {
    playComfyuiStatus()
      .then((s) =>
        setComfy({
          ready: Boolean(s.ready),
          reachable: Boolean(s.comfy_reachable),
          pingError: typeof s.comfy_ping_error === "string" ? s.comfy_ping_error : "",
        })
      )
      .catch(() => setComfy({ ready: false, reachable: false, pingError: "" }));
  }, []);

  useEffect(() => {
    refreshComfy();
  }, [refreshComfy]);

  useEffect(() => {
    if (view === "create") refreshComfy();
  }, [view, refreshComfy]);

  useEffect(() => {
    if (view === "create" && prevViewRef.current !== "create") {
      setStarterProf({});
      setCreatePhase("identity");
    }
    prevViewRef.current = view;
  }, [view]);

  useEffect(() => {
    if (view !== "create") return;
    let cancelled = false;
    setProfCatalogErr("");
    setProfCatalogLoading(true);
    playFetchProficiencyCatalog()
      .then((data) => {
        if (cancelled) return;
        if (data && typeof data.budget === "number" && Array.isArray(data.leaves)) setProfCatalog(data);
        else setProfCatalogErr("Proficiency catalog response was unexpected.");
      })
      .catch((e) => {
        if (cancelled) return;
        setProfCatalogErr(e.message || "Could not load proficiency catalog");
        setProfCatalog(null);
      })
      .finally(() => {
        if (!cancelled) setProfCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [view]);

  useEffect(() => {
    if (characters.length && selectedId == null) setSelectedId(characters[0].id);
  }, [characters, selectedId]);

  useEffect(() => {
    if (selectedId != null && !characters.some((c) => c.id === selectedId)) {
      setSelectedId(characters[0]?.id ?? null);
    }
  }, [characters, selectedId]);

  useEffect(() => {
    if (!pendingPortraitUrl) setPortraitLightboxOpen(false);
  }, [pendingPortraitUrl]);

  useEffect(() => {
    if (!portraitLightboxOpen) return;
    const onKey = (e) => {
      if (e.key === "Escape") setPortraitLightboxOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [portraitLightboxOpen]);

  const thumb = (c) =>
    c.portrait_url ? (
      <div
        className="fablestar-portrait-stage"
        style={{
          width: 44,
          aspectRatio: PORTRAIT_ASPECT_RATIO_CSS,
          borderRadius: T.radius.md,
          border: `1px solid ${T.border.subtle}`,
          overflow: "hidden",
          flexShrink: 0,
        }}
      >
        <div className="fablestar-portrait-aurora fablestar-portrait-aurora--thumb" aria-hidden />
        <img
          src={playMediaUrl(c.portrait_url)}
          alt=""
          className="fablestar-portrait-cutout fablestar-portrait-cutout--thumb"
          style={{
            position: "relative",
            width: "100%",
            height: "100%",
            objectFit: "contain",
            objectPosition: "center",
            display: "block",
          }}
        />
      </div>
    ) : (
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: T.radius.md,
          background: T.bg.surface,
          border: `1px solid ${T.border.subtle}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 20,
          color: T.glyph.violet,
        }}
      >
        ◈
      </div>
    );

  const closeDeleteModal = () => {
    setPendingDelete(null);
    setDeleteNameConfirm("");
    setDeleteErr("");
  };

  useEffect(() => {
    if (!pendingDelete) return;
    const onKey = (e) => {
      if (e.key === "Escape") {
        setPendingDelete(null);
        setDeleteNameConfirm("");
        setDeleteErr("");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pendingDelete]);

  const runDeleteConfirmed = async () => {
    if (!pendingDelete) return;
    if (deleteNameConfirm !== pendingDelete.name) return;
    const c = pendingDelete;
    setDeleteErr("");
    setDeleteBusyId(c.id);
    try {
      const res = await playDeleteCharacter(username, password, c.id);
      if (!res.ok) {
        const map = {
          character_not_found: "That character is not on your account.",
          invalid_credentials: "Sign in again, then retry.",
        };
        setDeleteErr(map[res.error] || res.error || "Could not delete character");
        return;
      }
      const next = res.characters || [];
      if (next.some((x) => x.id === c.id)) {
        setDeleteErr(
          "The server did not remove this character. Restart Nexus from the current project (python -m fablestar) so character delete is supported."
        );
        return;
      }
      closeDeleteModal();
      mergeEchoFromPlayRes?.(res);
      onUpdateCharacters(next);
      if (next.length === 0) setView("create");
    } catch (e) {
      setDeleteErr(e.message || "Delete failed");
    } finally {
      setDeleteBusyId(null);
    }
  };

  const runGeneratePortrait = async () => {
    setFormErr("");
    setPortraitGenerating(true);
    try {
      const prompt =
        portraitPrompt.trim() ||
        `portrait headshot, science fiction character ${newName.trim() || "traveler"}, detailed face, cinematic light`;
      const res = await playGeneratePortrait(username, password, prompt);
      if (!res.ok) {
        mergeEchoFromPlayRes?.(res);
        const map = {
          insufficient_credits: `Not enough ${res.currency_display_name || "pixels"} (need ${res.required ?? "?"}, have ${res.balance ?? "?"}).`,
          comfyui_failed: res.detail || "ComfyUI portrait run failed.",
          invalid_credentials: "Session expired — sign in again.",
        };
        setFormErr(map[res.error] || res.detail || res.error || "Portrait generation failed");
        return;
      }
      mergeEchoFromPlayRes?.(res);
      if (res.portrait_url) {
        setPendingPortraitUrl(res.portrait_url);
        setPortraitPreviewBust((n) => n + 1);
      }
      else
        setFormErr(
          "ComfyUI is not configured on the server. You can still create your character; if ComfyUI is enabled later, the server will generate a portrait on create."
        );
    } catch (e) {
      setFormErr(e.message || "Request failed");
    } finally {
      setPortraitGenerating(false);
    }
  };

  const runSuggestPortraitPrompt = async () => {
    setFormErr("");
    setSuggestBusy(true);
    try {
      const res = await playSuggestPortraitPrompt(username, password, newName.trim(), portraitPrompt.trim());
      if (!res.ok) {
        const map = {
          llm_prompt_too_short: "The model returned an empty prompt — add a few words to the portrait prompt (or only a name) and try again.",
          llm_failed: "LLM request failed — start LM Studio / Ollama or check config/llm.toml on Nexus.",
          invalid_credentials: "Session expired — sign in again.",
        };
        setFormErr(map[res.error] || res.detail || res.error || "Could not suggest a prompt (is the LLM configured on Nexus?)");
        return;
      }
      if (res.prompt) setPortraitPrompt(res.prompt);
    } catch (e) {
      setFormErr(e.message || "Request failed");
    } finally {
      setSuggestBusy(false);
    }
  };

  const goToProficienciesStep = () => {
    setFormErr("");
    if (!newName.trim()) {
      setFormErr("Enter a character name to continue.");
      return;
    }
    setCreatePhase("skills");
  };

  const runCreateCharacter = async (e) => {
    e.preventDefault();
    setFormErr("");
    setCreateBusy(true);
    try {
      const res = await playCreateCharacter(
        username,
        password,
        newName.trim(),
        portraitPrompt.trim(),
        pendingPortraitUrl,
        starterProf
      );
      if (!res.ok) {
        mergeEchoFromPlayRes?.(res);
        const err = res.error || "";
        let starterMsg = "";
        if (typeof err === "string") {
          if (err === "starter_budget_exceeded") starterMsg = "Starter proficiency points exceed the allowed total (15).";
          else if (err === "invalid_proficiency_id") starterMsg = "Invalid proficiency id in your picks.";
          else if (err === "invalid_starter_proficiencies") starterMsg = "Invalid proficiency levels — use whole numbers.";
          else if (err.startsWith("unknown_proficiency:"))
            starterMsg = `Unknown skill id: ${err.slice("unknown_proficiency:".length)}`;
          else if (err.startsWith("invalid_level:"))
            starterMsg = `Invalid level for ${err.slice("invalid_level:".length)}.`;
          else if (err.startsWith("level_out_of_range:"))
            starterMsg = `Each skill can be at most 5 at creation (${err.slice("level_out_of_range:".length)}).`;
        }
        const map = {
          invalid_character_name: "Use 2–50 characters: letters, numbers, single spaces, _ - (start and end with a letter or number)",
          character_name_reserved: "That name is reserved. Pick another.",
          character_name_taken: "That character name is already taken.",
          character_limit: "Maximum characters per account reached.",
          invalid_credentials: "Session expired — sign in again.",
          insufficient_credits: `Not enough ${res.currency_display_name || "pixels"} (need ${res.required ?? "?"}, have ${res.balance ?? "?"}).`,
        };
        setFormErr(starterMsg || map[res.error] || res.error || "Could not create character");
        return;
      }
      mergeEchoFromPlayRes?.(res);
      onUpdateCharacters(res.characters || []);
      setSelectedId(res.character?.id ?? null);
      setNewName("");
      setPortraitPrompt("");
      setPendingPortraitUrl("");
      setStarterProf({});
      setCreatePhase("identity");
      setPostCreatePortraitWarn(
        res.portrait_generation_failed
          ? "Character created, but ComfyUI could not finish the portrait. You can continue playing; ask an admin to check ComfyUI logs."
          : ""
      );
      setView("pick");
    } catch (err) {
      setFormErr(err.message || "Request failed");
    } finally {
      setCreateBusy(false);
    }
  };

  const canEnter = characters.length > 0 && selectedId != null;
  const selectedCharacter = selectedId != null ? characters.find((c) => c.id === selectedId) ?? null : null;
  const comfyReady = comfy.ready;
  const comfyLabel = !comfy.ready
    ? "Portrait workflow not ready"
    : comfy.reachable
      ? "ComfyUI reachable"
      : "ComfyUI host not responding";

  const deleteNameMatches = pendingDelete != null && deleteNameConfirm === pendingDelete.name;

  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        width: "100%",
        background: T.bg.void,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: T.font.body,
        padding: 24,
        boxSizing: "border-box",
        position: "relative",
      }}
    >
      <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&family=Exo+2:wght@600;700&family=Oxanium:wght@500;600;700&display=swap" rel="stylesheet" />
      {pendingDelete ? (
        <div
          role="presentation"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 2000,
            background: "rgba(6,6,10,0.82)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 20,
            boxSizing: "border-box",
          }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) closeDeleteModal();
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-char-title"
            style={{
              width: "100%",
              maxWidth: 400,
              borderRadius: T.radius.xl,
              border: `1px solid ${T.border.medium}`,
              background: T.bg.panel,
              boxShadow: T.shadow.panel,
              padding: "22px 22px 18px",
            }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 id="delete-char-title" style={{ fontFamily: T.font.display, fontSize: 16, color: T.text.primary, margin: "0 0 8px" }}>
              Delete character?
            </h3>
            <p style={{ fontSize: 12, color: T.text.secondary, lineHeight: 1.5, margin: "0 0 14px" }}>
              Permanently removes <strong style={{ color: T.text.accent }}>{pendingDelete.name}</strong> from your account. This cannot be undone.
            </p>
            <label style={{ display: "block", fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
              Type the character name to confirm
            </label>
            <input
              autoComplete="off"
              value={deleteNameConfirm}
              onChange={(e) => setDeleteNameConfirm(e.target.value)}
              placeholder={pendingDelete.name}
              style={{
                width: "100%",
                marginBottom: 12,
                padding: "10px 12px",
                borderRadius: T.radius.md,
                border: `1px solid ${T.border.medium}`,
                background: T.bg.surface,
                color: T.text.primary,
                fontFamily: T.font.mono,
                fontSize: 13,
                outline: "none",
                boxSizing: "border-box",
              }}
            />
            {deleteErr ? (
              <div role="alert" style={{ marginBottom: 14, fontSize: 12, color: T.text.danger, lineHeight: 1.45 }}>
                {deleteErr}
              </div>
            ) : null}
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", flexWrap: "wrap" }}>
              <button
                type="button"
                disabled={deleteBusyId != null}
                onClick={closeDeleteModal}
                style={{
                  padding: "8px 14px",
                  borderRadius: T.radius.md,
                  border: `1px solid ${T.border.medium}`,
                  background: T.bg.surface,
                  color: T.text.muted,
                  fontSize: 11,
                  cursor: deleteBusyId != null ? "wait" : "pointer",
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!deleteNameMatches || deleteBusyId != null}
                onClick={runDeleteConfirmed}
                style={{
                  padding: "8px 14px",
                  borderRadius: T.radius.md,
                  border: `1px solid ${T.text.danger}`,
                  background: deleteNameMatches ? T.text.danger : T.bg.void,
                  color: deleteNameMatches ? "#0a0a0f" : T.text.muted,
                  fontSize: 11,
                  fontWeight: 700,
                  cursor: !deleteNameMatches || deleteBusyId != null ? "not-allowed" : "pointer",
                  opacity: deleteNameMatches ? 1 : 0.55,
                }}
              >
                {deleteBusyId != null ? "Deleting…" : "Delete forever"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {portraitLightboxOpen && pendingPortraitUrl ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Portrait full size"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1990,
            background: "rgba(6,6,10,0.94)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "48px 20px 20px",
            boxSizing: "border-box",
          }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setPortraitLightboxOpen(false);
          }}
        >
          <button
            type="button"
            onClick={() => setPortraitLightboxOpen(false)}
            style={{
              position: "fixed",
              top: 16,
              right: 16,
              zIndex: 1991,
              padding: "8px 14px",
              borderRadius: T.radius.md,
              border: `1px solid ${T.border.medium}`,
              background: T.bg.panel,
              color: T.text.secondary,
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Close
          </button>
          <div
            className="fablestar-portrait-stage"
            onMouseDown={(e) => e.stopPropagation()}
            style={{
              position: "relative",
              maxWidth: "min(96vw, 1200px)",
              maxHeight: "calc(100vh - 56px)",
              borderRadius: T.radius.lg,
              overflow: "hidden",
              border: `1px solid ${T.border.glyph}`,
              boxShadow: `0 0 0 1px rgba(0,0,0,0.4), ${T.shadow.glow}`,
            }}
          >
            <div className="fablestar-portrait-aurora fablestar-portrait-aurora--lightbox" aria-hidden />
            <img
              src={playMediaUrl(pendingPortraitUrl, portraitPreviewBust)}
              alt="Portrait full size"
              className="fablestar-portrait-cutout fablestar-portrait-cutout--lightbox"
              style={{
                position: "relative",
                display: "block",
                maxWidth: "min(calc(96vw - 16px), 1184px)",
                maxHeight: "calc(100vh - 72px)",
                width: "auto",
                height: "auto",
                margin: "0 auto",
                objectFit: "contain",
              }}
            />
          </div>
          <div
            style={{
              position: "fixed",
              bottom: 16,
              left: "50%",
              transform: "translateX(-50%)",
              fontSize: 10,
              color: T.text.muted,
              textAlign: "center",
              pointerEvents: "none",
            }}
          >
            Escape or click outside the image to close
          </div>
        </div>
      ) : null}
      <div
        style={{
          width: "100%",
          maxWidth: 1320,
          display: "flex",
          flexWrap: "wrap",
          alignItems: "flex-start",
          justifyContent: "center",
          gap: 32,
          boxSizing: "border-box",
        }}
      >
        <div style={{ flex: "1 1 320px", maxWidth: view === "create" && createPhase === "skills" ? 1080 : 640, minWidth: 0 }}>
        <div style={{ marginBottom: 20, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div>
            <h2 style={{ fontFamily: T.font.display, fontSize: 18, color: T.text.primary }}>
              {view === "create"
                ? createPhase === "identity"
                  ? "New character"
                  : "Starting proficiencies"
                : "Choose a character"}
            </h2>
            {view === "create" ? (
              <p style={{ fontSize: 11, color: T.text.muted, marginTop: 4, lineHeight: 1.45 }}>
                Step {createPhase === "identity" ? "1" : "2"} of 2 ·{" "}
                {createPhase === "identity" ? "Identity & portrait" : "Optional conduit ranks"}
              </p>
            ) : null}
            <p style={{ fontSize: 12, color: T.text.muted, marginTop: view === "create" ? 2 : 4, lineHeight: 1.45, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 4 }}>
              Signed in as <span style={{ color: T.text.accent }}>{username}</span>
              {isGm ? <GmBadge style={{ marginLeft: 2 }} /> : null}
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <ThemeToggleButton />
            {view === "create" && (
              <button
                type="button"
                onClick={() => refreshComfy()}
                style={{
                  padding: "6px 10px",
                  borderRadius: T.radius.md,
                  border: `1px solid ${T.border.dim}`,
                  background: T.bg.surface,
                  color: T.text.muted,
                  fontSize: 10,
                  cursor: "pointer",
                }}
              >
                Refresh ComfyUI status
              </button>
            )}
            <button
              type="button"
              onClick={onCancel}
              style={{
                padding: "6px 12px",
                borderRadius: T.radius.md,
                border: `1px solid ${T.border.medium}`,
                background: T.bg.surface,
                color: T.text.muted,
                fontSize: 10,
                cursor: "pointer",
              }}
            >
              Back
            </button>
          </div>
        </div>

        {echoEconomy?.credits != null ? (
          <AccountArtCreditsBar echoEconomy={echoEconomy} gameCurrencyLabel={gameCurrencyLabel} onTopUp={onPixelsHelp} />
        ) : null}

        {view === "create" && createPhase === "identity" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 10,
                padding: "10px 12px",
                borderRadius: T.radius.lg,
                border: `1px solid ${comfy.ready && comfy.reachable ? T.border.success : T.border.dim}`,
                background: T.bg.panel,
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 99,
                  background: comfy.ready && comfy.reachable ? T.text.success : T.text.muted,
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1, minWidth: 200 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: T.text.primary }}>{comfyLabel}</div>
                <div style={{ fontSize: 10, color: T.text.muted, marginTop: 2 }}>
                  {comfy.ready
                    ? comfy.reachable
                      ? "When you finish creation, Nexus can generate a portrait via ComfyUI unless you already previewed one below."
                      : comfy.pingError || "Start ComfyUI on the server or check base_url in comfyui.toml."
                    : "Add config/comfyui_area_workflow.json (or set workflow_path in comfyui.toml) and enable comfyui.toml."}
                </div>
              </div>
            </div>
            <p style={{ fontSize: 12, color: T.text.secondary, lineHeight: 1.45 }}>
              Name your character and set up a portrait prompt (optional). Use{" "}
              <strong style={{ color: T.text.muted }}>Suggest prompt</strong> for an LLM-polished Comfy line. On the next step you will
              optionally place starter proficiency ranks — then you submit once to create them in the world.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 20, alignItems: "flex-start" }}>
              <div style={{ flex: "1 1 280px", display: "flex", flexDirection: "column", gap: 14 }}>
                <label style={{ fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em" }}>Character name</label>
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Mara Voss"
                  style={{
                    width: "100%",
                    padding: "10px 12px",
                    borderRadius: T.radius.md,
                    border: `1px solid ${T.border.medium}`,
                    background: T.bg.surface,
                    color: T.text.primary,
                    fontFamily: T.font.mono,
                    fontSize: 13,
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
                <label style={{ fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  Portrait prompt (ComfyUI)
                </label>
                <textarea
                  value={portraitPrompt}
                  onChange={(e) => setPortraitPrompt(e.target.value)}
                  placeholder="Rough idea: tired pilot, cybernetic eye, warm rim light… — then “Suggest prompt” to polish, or leave blank for a default from your name."
                  rows={4}
                  style={{
                    width: "100%",
                    padding: "10px 12px",
                    borderRadius: T.radius.md,
                    border: `1px solid ${T.border.medium}`,
                    background: T.bg.surface,
                    color: T.text.primary,
                    fontFamily: T.font.body,
                    fontSize: 12,
                    outline: "none",
                    resize: "vertical",
                    boxSizing: "border-box",
                  }}
                />
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  <button
                    type="button"
                    disabled={formLocked || !newName.trim()}
                    onClick={runSuggestPortraitPrompt}
                    title="Rewrites and expands whatever you typed in the portrait prompt (plus character name) into a stronger ComfyUI-style line"
                    style={{
                      padding: "8px 14px",
                      borderRadius: T.radius.md,
                      border: `1px solid ${T.border.medium}`,
                      background: T.bg.surface,
                      color: newName.trim() ? T.text.accent : T.text.muted,
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: formLocked || !newName.trim() ? "not-allowed" : "pointer",
                    }}
                  >
                    {suggestBusy ? "…" : "Suggest prompt (LLM)"}
                  </button>
                  <button
                    type="button"
                    disabled={formLocked || !comfyReady}
                    onClick={runGeneratePortrait}
                    title="Runs ComfyUI once and shows the result here"
                    style={{
                      padding: "8px 14px",
                      borderRadius: T.radius.md,
                      border: `1px solid ${T.border.glyph}`,
                      background: comfyReady ? T.glyph.violetDim : T.bg.surface,
                      color: comfyReady ? T.text.primary : T.text.muted,
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: formLocked || !comfyReady ? "not-allowed" : "pointer",
                    }}
                  >
                    {portraitGenerating ? "Generating…" : comfyReady ? "Generate portrait" : "Generate portrait (ComfyUI off)"}
                  </button>
                  <button
                    type="button"
                    disabled={formLocked || !comfyReady || !pendingPortraitUrl}
                    onClick={runGeneratePortrait}
                    title="Queue another ComfyUI run with the same prompt (you can edit the prompt first)"
                    style={{
                      padding: "8px 14px",
                      borderRadius: T.radius.md,
                      border: `1px solid ${pendingPortraitUrl && comfyReady ? T.border.medium : T.border.dim}`,
                      background: T.bg.surface,
                      color: pendingPortraitUrl && comfyReady ? T.text.secondary : T.text.muted,
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: formLocked || !comfyReady || !pendingPortraitUrl ? "not-allowed" : "pointer",
                    }}
                  >
                    {portraitGenerating ? "Generating…" : "Regenerate portrait"}
                  </button>
                </div>
              </div>
              <div
                className={
                  !portraitGenerating && pendingPortraitUrl ? "fablestar-portrait-stage" : undefined
                }
                style={{
                  flex: "0 0 auto",
                  width: 168,
                  alignSelf: "flex-start",
                  aspectRatio: PORTRAIT_ASPECT_RATIO_CSS,
                  borderRadius: T.radius.lg,
                  border: portraitGenerating
                    ? `1px solid ${T.border.glyphHot}`
                    : pendingPortraitUrl
                      ? `1px solid ${T.border.glyph}`
                      : `1px dashed ${T.border.glyph}`,
                  background: portraitGenerating ? T.bg.deep : !pendingPortraitUrl ? T.glyph.violetDim : undefined,
                  boxShadow: portraitGenerating ? T.shadow.glow : "none",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  overflow: "hidden",
                  position: "relative",
                }}
              >
                {portraitGenerating ? (
                  <div
                    role="status"
                    aria-live="polite"
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 10,
                      padding: 14,
                      textAlign: "center",
                    }}
                  >
                    <div
                      className="fablestar-portrait-spin"
                      style={{
                        width: 44,
                        height: 44,
                        borderRadius: "50%",
                        border: `2px solid ${T.border.dim}`,
                        borderTopColor: T.glyph.violet,
                        borderRightColor: T.glyph.cyan,
                      }}
                    />
                    <div
                      style={{
                        fontFamily: T.font.display,
                        fontSize: 11,
                        letterSpacing: "0.16em",
                        textTransform: "uppercase",
                        color: T.text.accent,
                        fontWeight: 700,
                      }}
                    >
                      Generating
                    </div>
                    <div style={{ fontSize: 10, color: T.text.muted, lineHeight: 1.35, maxWidth: 138 }}>
                      ComfyUI is rendering your portrait…
                    </div>
                  </div>
                ) : pendingPortraitUrl ? (
                  <>
                    <div className="fablestar-portrait-aurora fablestar-portrait-aurora--thumb" aria-hidden />
                    <button
                      type="button"
                      key={portraitPreviewBust}
                      title="View full size"
                      aria-label="View portrait full screen"
                      onClick={() => setPortraitLightboxOpen(true)}
                      style={{
                        position: "absolute",
                        inset: 0,
                        zIndex: 2,
                        padding: 0,
                        margin: 0,
                        border: "none",
                        cursor: "zoom-in",
                        background: "transparent",
                        display: "block",
                      }}
                    >
                      <img
                        src={playMediaUrl(pendingPortraitUrl, portraitPreviewBust)}
                        alt="Portrait preview"
                        className="fablestar-portrait-cutout fablestar-portrait-cutout--thumb"
                        style={{
                          width: "100%",
                          height: "100%",
                          objectFit: "contain",
                          objectPosition: "center",
                          display: "block",
                          pointerEvents: "none",
                        }}
                      />
                    </button>
                  </>
                ) : (
                  <span style={{ fontSize: 11, color: T.text.muted, textAlign: "center", padding: 12 }}>
                    Portrait preview appears after “Generate portrait”, or when you create the character (server runs ComfyUI if you skip this step).
                  </span>
                )}
              </div>
            </div>
            {pendingPortraitUrl && !portraitGenerating ? (
              <p style={{ fontSize: 10, color: T.text.muted, margin: "-4px 0 0", textAlign: "right" }}>
                Click the preview to view it full screen
              </p>
            ) : null}
            {formErr ? (
              <div role="alert" style={{ fontSize: 12, color: T.text.danger }}>
                {formErr}
              </div>
            ) : null}
            <button
              type="button"
              disabled={formLocked || !newName.trim()}
              onClick={goToProficienciesStep}
              style={{
                width: "100%",
                padding: "12px",
                borderRadius: T.radius.md,
                border: "none",
                cursor: formLocked ? "wait" : "pointer",
                background: `linear-gradient(135deg,${T.glyph.violet},${T.glyph.cyan})`,
                color: "#0a0a0f",
                fontWeight: 700,
                fontSize: 12,
              }}
            >
              Continue — starting proficiencies →
            </button>
            <p style={{ fontSize: 10, color: T.text.muted, margin: 0, textAlign: "center", lineHeight: 1.45 }}>
              The skill catalog loads in the background while you work here, so the next screen is ready when you continue.
            </p>
            {characters.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setView("pick");
                  setFormErr("");
                  setCreatePhase("identity");
                }}
                style={{ background: "none", border: "none", color: T.text.muted, fontSize: 11, cursor: "pointer" }}
              >
                Cancel — back to list
              </button>
            )}
          </div>
        )}

        {view === "create" && createPhase === "skills" && (
          <form onSubmit={runCreateCharacter} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <ChargenProficienciesStep
              characterName={newName.trim()}
              portraitUrl={pendingPortraitUrl}
              portraitBust={portraitPreviewBust}
              budget={profCatalog?.budget ?? 15}
              maxPerLeaf={profCatalog?.max_per_leaf ?? 5}
              leaves={profCatalog?.leaves ?? []}
              catalogLoading={profCatalogLoading}
              catalogErr={profCatalogErr}
              value={starterProf}
              onChange={setStarterProf}
              disabled={formLocked}
              onBack={() => {
                setFormErr("");
                setCreatePhase("identity");
              }}
            />
            {formErr ? (
              <div role="alert" style={{ fontSize: 12, color: T.text.danger, lineHeight: 1.45, maxWidth: 720, alignSelf: "center" }}>
                {formErr}
              </div>
            ) : null}
            {comfy.ready && comfy.reachable && (
              <p style={{ fontSize: 10, color: T.text.muted, margin: 0, textAlign: "center", lineHeight: 1.45 }}>
                Final submit may run ComfyUI for your portrait if you did not preview one — can take about a minute.
              </p>
            )}
            <button
              type="submit"
              disabled={formLocked || !newName.trim() || createBusy}
              style={{
                width: "100%",
                maxWidth: 480,
                alignSelf: "center",
                padding: "12px",
                borderRadius: T.radius.md,
                border: "none",
                cursor: createBusy ? "wait" : "pointer",
                background: `linear-gradient(135deg,${T.glyph.violet},${T.glyph.cyan})`,
                color: "#0a0a0f",
                fontWeight: 700,
                fontSize: 12,
              }}
            >
              {createBusy ? "Creating character…" : "Create character"}
            </button>
            {characters.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setView("pick");
                  setFormErr("");
                  setCreatePhase("identity");
                }}
                style={{ background: "none", border: "none", color: T.text.muted, fontSize: 11, cursor: "pointer", alignSelf: "center" }}
              >
                Cancel — back to list
              </button>
            )}
          </form>
        )}

        {view === "pick" && (
          <>
            {postCreatePortraitWarn ? (
              <div
                role="status"
                style={{
                  marginBottom: 14,
                  padding: "12px 14px",
                  borderRadius: T.radius.lg,
                  border: `1px solid ${T.border.glyph}`,
                  background: T.glyph.amberDim,
                  color: T.text.secondary,
                  fontSize: 12,
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-start",
                }}
              >
                <span style={{ flex: 1 }}>{postCreatePortraitWarn}</span>
                <button
                  type="button"
                  onClick={() => setPostCreatePortraitWarn("")}
                  style={{
                    flexShrink: 0,
                    padding: "4px 8px",
                    borderRadius: T.radius.sm,
                    border: `1px solid ${T.border.medium}`,
                    background: T.bg.surface,
                    color: T.text.muted,
                    fontSize: 10,
                    cursor: "pointer",
                  }}
                >
                  Dismiss
                </button>
              </div>
            ) : null}
            {deleteErr && !pendingDelete ? (
              <div role="alert" style={{ marginBottom: 10, fontSize: 12, color: T.text.danger }}>
                {deleteErr}
              </div>
            ) : null}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {characters.length === 0 && (
                <div
                  style={{
                    padding: 16,
                    borderRadius: T.radius.lg,
                    border: `1px dashed ${T.border.glyph}`,
                    background: T.glyph.violetDim,
                    color: T.text.secondary,
                    fontSize: 12,
                  }}
                >
                  No characters yet. Create one to enter the game.
                </div>
              )}
              {characters.map((c) => (
                <div
                  key={c.id}
                  style={{
                    display: "flex",
                    alignItems: "stretch",
                    gap: 0,
                    borderRadius: T.radius.lg,
                    border: `1px solid ${selectedId === c.id ? T.border.glyph : T.border.dim}`,
                    background: selectedId === c.id ? T.glyph.violetDim : T.bg.panel,
                    overflow: "hidden",
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedId(c.id)}
                    style={{
                      flex: "0 1 40%",
                      maxWidth: 280,
                      display: "flex",
                      alignItems: "center",
                      gap: 14,
                      padding: 14,
                      textAlign: "left",
                      cursor: "pointer",
                      border: "none",
                      background: "transparent",
                      color: T.text.primary,
                      fontFamily: "inherit",
                      minWidth: 0,
                    }}
                  >
                    {thumb(c)}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        {selectedId === c.id ? (
                          <span style={{ fontSize: 10, color: T.text.success, flexShrink: 0 }} aria-hidden>
                            ●
                          </span>
                        ) : null}
                        <div style={{ fontFamily: T.font.display, fontSize: 15, color: T.text.accent }}>{c.name}</div>
                        {isGm ? (
                          <GmBadge
                            style={{
                              marginLeft: 2,
                              fontSize: 8,
                              padding: "2px 6px",
                            }}
                          />
                        ) : null}
                      </div>
                      <div
                        style={{
                          fontSize: 11,
                          fontFamily: T.font.mono,
                          color: T.currency.digi.fg,
                          marginTop: 5,
                          letterSpacing: "0.02em",
                        }}
                        title={`In-world wallet for this character (${gameCurrencyLabel})`}
                      >
                        {gameCurrencyLabel}{" "}
                        <span style={{ fontWeight: 600 }}>{typeof c.digi_balance === "number" ? c.digi_balance : 0}</span>
                      </div>
                      <div
                        style={{
                          marginTop: 6,
                          display: "flex",
                          flexWrap: "wrap",
                          alignItems: "center",
                          gap: 8,
                          fontSize: 9,
                          fontFamily: T.font.body,
                        }}
                      >
                        <span
                          style={{
                            padding: "2px 6px",
                            borderRadius: T.radius.sm,
                            fontWeight: 600,
                            color: c.pvp_enabled ? T.glyph.crimson : T.text.success,
                            background: c.pvp_enabled ? T.glyph.crimsonDim : "rgba(52,211,153,0.1)",
                            border: `1px solid ${c.pvp_enabled ? `${T.glyph.crimson}40` : `${T.text.success}35`}`,
                          }}
                        >
                          {c.pvp_enabled ? "PVP on" : "No PVP"}
                        </span>
                      </div>
                      <div style={{ marginTop: 8, maxWidth: 280 }}>
                        <ReputationThermometer reputation={typeof c.reputation === "number" ? c.reputation : 0} compact />
                      </div>
                    </div>
                  </button>
                  <ChooseCharacterGlassStats character={c} selected={selectedId === c.id} onSelectRow={setSelectedId} />
                  <button
                    type="button"
                    title="Delete character"
                    disabled={deleteBusyId != null || pendingDelete != null}
                    onClick={() => {
                      setDeleteErr("");
                      setPendingDelete({ id: c.id, name: c.name });
                      setDeleteNameConfirm("");
                    }}
                    style={{
                      flexShrink: 0,
                      width: 44,
                      border: "none",
                      borderLeft: `1px solid ${T.border.dim}`,
                      background: T.bg.surface,
                      color: T.text.muted,
                      fontSize: 18,
                      lineHeight: 1,
                      cursor: deleteBusyId != null ? "wait" : "pointer",
                      opacity: deleteBusyId === c.id ? 0.5 : 1,
                    }}
                  >
                    {deleteBusyId === c.id ? "…" : "×"}
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => {
                setView("create");
                setFormErr("");
                setPostCreatePortraitWarn("");
              }}
              style={{
                width: "100%",
                marginTop: 12,
                padding: "10px",
                borderRadius: T.radius.md,
                border: `1px solid ${T.border.medium}`,
                background: T.bg.surface,
                color: T.text.muted,
                fontSize: 11,
                cursor: "pointer",
              }}
            >
              + Create another character
            </button>
            <button
              type="button"
              disabled={!canEnter}
              onClick={() => {
                const ch = characters.find((c) => c.id === selectedId);
                onChosen({
                  characterId: selectedId,
                  characterName: ch?.name ?? username,
                  password,
                  portraitUrl: ch?.portrait_url ?? null,
                  digiBalance: typeof ch?.digi_balance === "number" ? ch.digi_balance : 0,
                  pvpEnabled: Boolean(ch?.pvp_enabled),
                  reputation: typeof ch?.reputation === "number" ? ch.reputation : 0,
                  lastSceneImageUrl: ch?.last_scene_image_url ?? null,
                  characterStats: ch?.stats ?? null,
                  resonanceLevelsTotal: typeof ch?.resonance_levels_total === "number" ? ch.resonance_levels_total : null,
                });
              }}
              style={{
                width: "100%",
                marginTop: 16,
                padding: "12px",
                borderRadius: T.radius.md,
                border: "none",
                cursor: canEnter ? "pointer" : "not-allowed",
                opacity: canEnter ? 1 : 0.45,
                background: `linear-gradient(135deg,${T.glyph.violet},${T.glyph.cyan})`,
                color: "#0a0a0f",
                fontWeight: 700,
                fontSize: 12,
              }}
            >
              Enter the Expanse
            </button>
          </>
        )}
        </div>
        {view === "pick" && characters.length > 0 ? (
          <aside
            aria-label="Selected character portrait"
            style={{
              flex: "0 1 460px",
              width: "100%",
              maxWidth: "min(520px, 92vw)",
              minWidth: 280,
              position: "sticky",
              top: 24,
              alignSelf: "flex-start",
              padding: "20px 22px",
              borderRadius: T.radius.xl,
              border: `1px solid ${T.border.medium}`,
              background: T.bg.panel,
              boxShadow: T.shadow.panel,
              boxSizing: "border-box",
            }}
          >
            <div style={{ fontFamily: T.font.display, fontSize: 13, color: T.text.primary, marginBottom: 4 }}>
              {selectedCharacter?.name ?? "—"}
            </div>
            <div style={{ fontSize: 10, color: T.text.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 14 }}>
              Portrait preview
            </div>
            {selectedCharacter?.portrait_url ? (
              <div
                className="fablestar-portrait-stage"
                style={{
                  width: "100%",
                  aspectRatio: PORTRAIT_ASPECT_RATIO_CSS,
                  borderRadius: T.radius.lg,
                  border: `1px solid ${T.border.glyph}`,
                  overflow: "hidden",
                }}
              >
                <div className="fablestar-portrait-aurora fablestar-portrait-aurora--thumb" aria-hidden />
                <img
                  src={playMediaUrl(selectedCharacter.portrait_url)}
                  alt={selectedCharacter.name ? `Portrait: ${selectedCharacter.name}` : "Character portrait"}
                  className="fablestar-portrait-cutout fablestar-portrait-cutout--hero"
                  style={{
                    position: "relative",
                    width: "100%",
                    height: "100%",
                    objectFit: "contain",
                    objectPosition: "center",
                    display: "block",
                  }}
                />
              </div>
            ) : (
              <div
                style={{
                  width: "100%",
                  aspectRatio: PORTRAIT_ASPECT_RATIO_CSS,
                  borderRadius: T.radius.lg,
                  border: `1px dashed ${T.border.dim}`,
                  background: T.bg.surface,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: T.text.muted,
                  fontSize: 12,
                  textAlign: "center",
                  padding: 16,
                  boxSizing: "border-box",
                }}
              >
                No portrait yet for this character.
              </div>
            )}
          </aside>
        ) : null}
      </div>
    </div>
  );
}

const MAX_NARRATIVE_LINES = 1500;

export default function App() {
  const [step, setStep] = useState("login");
  const [auth, setAuth] = useState(null);
  const passwordRef = useRef("");
  const [playSession, setPlaySession] = useState(null);
  const [narrativeLines, setNarrativeLinesRaw] = useState(() => [...DEFAULT_NARRATIVE]);
  // The log is append-only for hours of play; keep the DOM bounded.
  const setNarrativeLines = useCallback((update) => {
    setNarrativeLinesRaw((prev) => {
      const next = typeof update === "function" ? update(prev) : update;
      return next.length > MAX_NARRATIVE_LINES ? next.slice(-MAX_NARRATIVE_LINES) : next;
    });
  }, []);
  const [wsConnected, setWsConnected] = useState(false);
  // Set when the server ended the session on purpose (quit, signed in elsewhere,
  // login refused): show why and wait for the player instead of auto-reconnecting.
  const [wsStopped, setWsStopped] = useState(null);
  const [wsRetry, setWsRetry] = useState(0); // bumped by onclose to trigger auto-reconnect
  const wsRef = useRef(null);
  const [playerScenePath, setPlayerScenePath] = useState(null);
  const [playerSceneBust, setPlayerSceneBust] = useState(0);
  const [playComfyScene, setPlayComfyScene] = useState({
    areaReady: false,
    areaCost: 3,
    economyEnabled: true,
    currencyDisplayName: "pixels",
    pixelsPerUsd: 100,
  });
  const [echoEconomy, setEchoEconomy] = useState({ credits: null, label: "pixels", warnBelow: 12, pixelsPerUsd: 100 });
  const [sceneGenerating, setSceneGenerating] = useState(false);
  const sceneGenerateInFlightRef = useRef(false);

  const mergeEchoFromPlayRes = useCallback((res) => {
    if (!res || typeof res !== "object") return;
    setEchoEconomy((prev) => ({
      ...prev,
      credits: typeof res.echo_credits === "number" ? res.echo_credits : prev.credits,
      label: typeof res.currency_display_name === "string" ? res.currency_display_name : prev.label,
      pixelsPerUsd: typeof res.pixels_per_usd === "number" ? res.pixels_per_usd : prev.pixelsPerUsd,
    }));
    if (typeof res.is_gm === "boolean") {
      setAuth((a) => (a ? { ...a, isGm: res.is_gm } : a));
    }
  }, []);

  const updateAuthCharacters = useCallback((chars) => {
    setAuth((a) => (a ? { ...a, characters: chars } : a));
  }, []);

  // Dev login names its character up front; skip the chooser for it.
  const devAutoCharacterRef = useRef(null);
  const onLoggedIn = useCallback((a, pw, autoCharacterId) => {
    devAutoCharacterRef.current = autoCharacterId ?? null;
    passwordRef.current = pw;
    setAuth(a);
    setEchoEconomy({
      credits: typeof a.echoCredits === "number" ? a.echoCredits : 0,
      label: a.currencyDisplayName || "pixels",
      warnBelow: 12,
      pixelsPerUsd: typeof a.pixelsPerUsd === "number" ? a.pixelsPerUsd : 100,
    });
    setStep("choose");
  }, []);

  const disconnectWs = useCallback(() => {
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* ignore */ }
      wsRef.current = null;
    }
    setWsConnected(false);
  }, []);

  const onSignOut = useCallback(() => {
    disconnectWs();
    setPlaySession(null);
    setAuth(null);
    passwordRef.current = "";
    window.location.hash = "#/";
    setStep("login");
    setNarrativeLines([...DEFAULT_NARRATIVE]);
    setPlayerScenePath(null);
    setPlayerSceneBust(0);
    setPlayComfyScene({ areaReady: false, areaCost: 3, economyEnabled: true, currencyDisplayName: "pixels", pixelsPerUsd: 100 });
    setEchoEconomy({ credits: null, label: "pixels", warnBelow: 12, pixelsPerUsd: 100 });
    setSceneGenerating(false);
    sceneGenerateInFlightRef.current = false;
  }, [disconnectWs]);

  const explainPlayPixels = useCallback(() => {
    const lab = echoEconomy?.label || "pixels";
    const game = auth?.gameCurrencyDisplayName ?? "Digi";
    const ppu = echoEconomy?.pixelsPerUsd ?? playComfyScene?.pixelsPerUsd ?? 100;
    const sceneCost = typeof playComfyScene?.areaCost === "number" ? playComfyScene.areaCost : 3;
    window.alert(
      `${lab} (art currency) is spent on AI portraits and scene art (ComfyUI). ` +
        `On this server, one scene generation is about ${sceneCost} ${lab} (portrait pricing may differ).\n\n` +
        `Reference rate: ${ppu} ${lab} ≈ US $1 at list price — your host may sell packs or grant balance. ` +
        `Not the same as in-world ${game}.`
    );
  }, [
    echoEconomy?.label,
    echoEconomy?.pixelsPerUsd,
    auth?.gameCurrencyDisplayName,
    playComfyScene?.areaCost,
    playComfyScene?.pixelsPerUsd,
  ]);

  useEffect(() => {
    if (step !== "play") {
      setPlayerScenePath(null);
      setPlayerSceneBust(0);
      setPlayComfyScene({ areaReady: false, areaCost: 3, economyEnabled: true, currencyDisplayName: "pixels", pixelsPerUsd: 100 });
      setSceneGenerating(false);
      sceneGenerateInFlightRef.current = false;
    }
  }, [step]);

  useEffect(() => {
    if (step !== "play" || !playSession) {
      setPlayComfyScene({ areaReady: false, areaCost: 3, economyEnabled: true, currencyDisplayName: "pixels", pixelsPerUsd: 100 });
      return;
    }
    let cancelled = false;
    playComfyuiStatus()
      .then((s) => {
        if (!cancelled) {
          const areaCost = typeof s.area_generation_cost === "number" ? s.area_generation_cost : 3;
          const ppu = typeof s.pixels_per_usd === "number" ? s.pixels_per_usd : 100;
          setPlayComfyScene({
            areaReady: Boolean(s.area_ready),
            areaCost,
            economyEnabled: s.economy_enabled !== false,
            currencyDisplayName:
              typeof s.currency_display_name === "string" && s.currency_display_name.trim()
                ? s.currency_display_name.trim()
                : "pixels",
            pixelsPerUsd: ppu,
          });
          setEchoEconomy((prev) => ({
            ...prev,
            warnBelow: Math.max(9, areaCost * 3),
            pixelsPerUsd: ppu,
          }));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPlayComfyScene({ areaReady: false, areaCost: 3, economyEnabled: true, currencyDisplayName: "pixels", pixelsPerUsd: 100 });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [step, playSession?.username, playSession?.characterId]);

  const onChosen = useCallback(
    ({ characterId, characterName, password, portraitUrl, digiBalance, pvpEnabled, reputation, lastSceneImageUrl, characterStats, resonanceLevelsTotal }) => {
      passwordRef.current = password;
      setPlaySession({
        username: auth.username,
        accountId: auth.accountId,
        characterId,
        characterName,
        portraitUrl: portraitUrl || null,
        digiBalance: typeof digiBalance === "number" ? digiBalance : 0,
        pvpEnabled: typeof pvpEnabled === "boolean" ? pvpEnabled : false,
        reputation: typeof reputation === "number" ? reputation : 0,
        isGm: Boolean(auth.isGm),
        characterStats: characterStats && typeof characterStats === "object" ? characterStats : null,
        resonanceLevelsTotal: typeof resonanceLevelsTotal === "number" ? resonanceLevelsTotal : null,
      });
      setPlayerScenePath(lastSceneImageUrl && String(lastSceneImageUrl).trim() ? String(lastSceneImageUrl).trim() : null);
      setPlayerSceneBust((n) => n + 1);
      setStep("play");
    },
    [auth]
  );

  useEffect(() => {
    if (step !== "choose" || !auth || devAutoCharacterRef.current == null) return;
    const ch = (auth.characters || []).find((c) => c.id === devAutoCharacterRef.current);
    devAutoCharacterRef.current = null;
    if (!ch) return;
    onChosen({
      characterId: ch.id,
      characterName: ch.name,
      password: "",
      portraitUrl: ch.portrait_url ?? null,
      digiBalance: typeof ch.digi_balance === "number" ? ch.digi_balance : 0,
      pvpEnabled: Boolean(ch.pvp_enabled),
      reputation: typeof ch.reputation === "number" ? ch.reputation : 0,
      lastSceneImageUrl: ch.last_scene_image_url ?? null,
      characterStats: ch.stats ?? null,
      resonanceLevelsTotal: typeof ch.resonance_levels_total === "number" ? ch.resonance_levels_total : null,
    });
  }, [step, auth, onChosen]);

  useEffect(() => {
    if (step !== "play" || !playSession) return undefined;
    const url = playWebSocketUrl();
    const ws = new WebSocket(url);
    wsRef.current = ws;
    let endReason = null;

    ws.onopen = () => {
      setWsConnected(true);
      setWsStopped(null);
      const token = getPlayToken();
      const payload = token
        ? { token }
        : { username: playSession.username, password: passwordRef.current };
      if (playSession.characterId != null) payload.character_id = playSession.characterId;
      ws.send(JSON.stringify(payload));
      // Keep password in memory for this session: /play/* HTTP routes (scene LLM, Comfy, portraits)
      // reuse the same credentials on older Nexus builds without token support.
    };

    ws.onmessage = (ev) => {
      const t = typeof ev.data === "string" ? ev.data : "";
      const trimmed = t.trim();
      try {
        const j = JSON.parse(trimmed);
        if (j && j.ok === false) {
          setNarrativeLines((prev) => [...prev, { type: "alert", text: `Connection refused: ${j.error}`, level: "danger" }]);
          endReason = "refused";
          ws.close();
          return;
        }
        if (j && j.client_notice === "session_end") {
          endReason = typeof j.reason === "string" ? j.reason : null;
          return;
        }
        if (j && j.client_notice === "echo_credits_granted") {
          const lab = typeof j.currency_display_name === "string" && j.currency_display_name.trim() ? j.currency_display_name.trim() : "pixels";
          const added = typeof j.echo_credits_added === "number" ? j.echo_credits_added : 0;
          const bal = typeof j.echo_credits === "number" ? j.echo_credits : null;
          mergeEchoFromPlayRes(j);
          if (bal != null) {
            setAuth((a) => (a ? { ...a, echoCredits: bal } : a));
          }
          const msg =
            added > 0 && bal != null
              ? `A GM added ${added} ${lab} to your account. Your balance is now ${bal} ${lab}.`
              : bal != null
                ? `Your ${lab} balance was updated to ${bal}.`
                : `Your ${lab} balance was updated.`;
          setNarrativeLines((prev) => [...prev, { type: "pixel_grant", text: msg }]);
          return;
        }
        if (j && j.client_notice === "chat_message") {
          setPlaySession((prev) =>
            prev
              ? {
                  ...prev,
                  chatMessages: [
                    ...(prev.chatMessages || []).slice(-99),
                    {
                      channel: j.channel === "tell" ? "tell" : "local",
                      from: String(j.from || "?"),
                      text: String(j.text || ""),
                      self: Boolean(j.self),
                      at: typeof j.at === "number" ? j.at : Date.now() / 1000,
                    },
                  ],
                }
              : prev
          );
          return;
        }
        if (j && j.client_notice === "character_snapshot") {
          setPlaySession((prev) =>
            prev
              ? {
                  ...prev,
                  characterStats: j.stats && typeof j.stats === "object" ? j.stats : prev.characterStats,
                  resonanceLevelsTotal:
                    typeof j.resonance_levels_total === "number" ? j.resonance_levels_total : prev.resonanceLevelsTotal,
                  liveLocation: j.location && typeof j.location === "object" ? j.location : prev.liveLocation,
                  liveEffects: Array.isArray(j.effects) ? j.effects : prev.liveEffects,
                  liveInventory: Array.isArray(j.inventory) ? j.inventory : prev.liveInventory,
                  liveMap: j.map && typeof j.map === "object" ? j.map : prev.liveMap,
                }
              : prev
          );
          return;
        }
        if (j && j.client_notice === "staff_account_update") {
          if (typeof j.echo_credits === "number") {
            mergeEchoFromPlayRes(j);
            setAuth((a) => (a ? { ...a, echoCredits: j.echo_credits } : a));
          }
          if (typeof j.play_account_is_gm === "boolean") {
            setAuth((a) => (a ? { ...a, isGm: j.play_account_is_gm } : a));
          }
          const roleLabel = typeof j.staff_role_label === "string" && j.staff_role_label.trim() ? j.staff_role_label.trim() : "Staff";
          const dname = typeof j.staff_display_name === "string" && j.staff_display_name.trim() ? j.staff_display_name.trim() : "Someone";
          const charPart = typeof j.character_name === "string" && j.character_name.trim() ? ` — character ${j.character_name.trim()}` : "";
          const auditRaw = Array.isArray(j.audit_lines) ? j.audit_lines : [];
          const bullets = auditRaw.filter((x) => typeof x === "string" && x.trim()).map((x) => `• ${x.trim()}`);
          const body = bullets.length ? bullets.join("\n") : "Your account was updated.";
          const msg = `${roleLabel} (${dname})${charPart}:\n${body}`;
          setNarrativeLines((prev) => [...prev, { type: "staff_notice", text: msg }]);
          return;
        }
      } catch {
        /* narrative text */
      }
      const parts = t.split(/\r?\n/).filter((line) => line.length > 0);
      if (parts.length === 0) return;
      setNarrativeLines((prev) => [
        ...prev,
        ...parts.map((text) =>
          /^\[Server\]/i.test(String(text).trim())
            ? { type: "server_message", text }
            : { type: "raw", text }
        ),
      ]);
    };

    let retryTimer = null;
    ws.onclose = () => {
      setWsConnected(false);
      wsRef.current = null;
      const stopped = {
        quit: "You left the station.",
        replaced: "This character signed in from another window or device.",
        refused: "The station refused this login.",
      }[endReason];
      if (stopped) {
        setWsStopped(stopped);
        return;
      }
      // Auto-reconnect after a drop or a death (the server respawns you on
      // login). Without it a server restart left a dead socket eating commands.
      retryTimer = setTimeout(() => setWsRetry((n) => n + 1), 2500);
    };

    ws.onerror = () => {
      setWsConnected(false);
    };

    return () => {
      if (retryTimer) clearTimeout(retryTimer);
      disconnectWs();
    };
    // Important: do not depend on the full `playSession` object. `character_snapshot` and other
    // updates merge into playSession often; a new object reference would reconnect the socket and
    // the server would emit initial `look` again — duplicate room blocks / "narrative spam".
  }, [step, playSession?.username, playSession?.characterId, disconnectWs, mergeEchoFromPlayRes, wsRetry]);

  const onSendCommand = useCallback((cmd) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      setNarrativeLines((prev) => [...prev, { type: "action", text: `> ${cmd}`, ts: new Date().toLocaleTimeString([], { hour12: false }) }]);
      ws.send(cmd);
    }
  }, []);

  const handleSceneImageSaved = useCallback((relativePath) => {
    if (!relativePath) return;
    setPlayerScenePath(relativePath);
    setPlayerSceneBust((n) => n + 1);
    setAuth((a) => {
      if (!a?.characters || playSession?.characterId == null) return a;
      const id = playSession.characterId;
      return {
        ...a,
        characters: a.characters.map((c) =>
          c.id === id ? { ...c, last_scene_image_url: relativePath } : c
        ),
      };
    });
  }, [playSession?.characterId]);

  const beginBackgroundSceneGenerate = useCallback(
    (scene_prompt) => {
      if (!playSession) return;
      const p = (scene_prompt || "").trim();
      if (p.length < 3) return;
      if (sceneGenerateInFlightRef.current) {
        setNarrativeLines((prev) => [
          ...prev,
          {
            type: "alert",
            level: "warning",
            text: "Scene art is already generating — watch the Scene panel.",
          },
        ]);
        return;
      }
      sceneGenerateInFlightRef.current = true;
      setSceneGenerating(true);
      playGenerateSceneImage(playSession.username, passwordRef.current, p, playSession.characterId)
        .then((res) => {
          mergeEchoFromPlayRes(res);
          if (!res.ok) {
            const map = {
              comfyui_not_configured: "ComfyUI or the area workflow is not configured on Nexus.",
              comfyui_failed: res.detail || "ComfyUI run failed.",
              invalid_credentials: "Session expired — sign in again.",
              prompt_too_short: "Prompt too short.",
              prompt_too_long: "Prompt too long (max 4000 characters).",
              insufficient_credits: `Not enough ${res.currency_display_name || "pixels"} (need ${res.required ?? "?"}, have ${res.balance ?? "?"}).`,
            };
            const msg = map[res.error] || res.detail || res.error || "Scene generation failed";
            setNarrativeLines((prev) => [...prev, { type: "alert", level: "danger", text: msg }]);
            return;
          }
          if (res.scene_image_url) handleSceneImageSaved(res.scene_image_url);
        })
        .catch((e) => {
          setNarrativeLines((prev) => [
            ...prev,
            { type: "alert", level: "danger", text: e.message || "Scene generation failed" },
          ]);
        })
        .finally(() => {
          sceneGenerateInFlightRef.current = false;
          setSceneGenerating(false);
        });
    },
    [playSession, mergeEchoFromPlayRes, handleSceneImageSaved]
  );

  const appShell = { flex: 1, minHeight: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column" };

  if (step === "login") {
    return <div style={appShell}><PlayAuthFlow onLoggedIn={onLoggedIn} /></div>;
  }
  if (step === "choose" && auth) {
    return (
      <div style={appShell}>
        <CharacterChooser
          auth={auth}
          password={passwordRef.current}
          onCancel={onSignOut}
          onChosen={onChosen}
          onUpdateCharacters={updateAuthCharacters}
          echoEconomy={echoEconomy}
          mergeEchoFromPlayRes={mergeEchoFromPlayRes}
        />
      </div>
    );
  }
  if (step === "play" && playSession) {
    const staticSceneImageUrl =
      import.meta.env.VITE_SCENE_IMAGE_URL
        ? String(import.meta.env.VITE_SCENE_IMAGE_URL).startsWith("http")
          ? import.meta.env.VITE_SCENE_IMAGE_URL
          : playMediaUrl(import.meta.env.VITE_SCENE_IMAGE_URL)
        : undefined;
    const resolvedSceneImageUrl =
      playerScenePath != null ? playMediaUrl(playerScenePath, playerSceneBust) : staticSceneImageUrl;

    return (
      <div style={appShell}>
        <FablestarClient
          sceneGenerating={sceneGenerating}
          session={{
            username: playSession.username,
            characterName: playSession.characterName,
            characterId: playSession.characterId,
            portraitImageUrl: playSession.portraitUrl ? playMediaUrl(playSession.portraitUrl) : null,
            digiBalance: playSession.digiBalance ?? 0,
            pvpEnabled: playSession.pvpEnabled,
            reputation: playSession.reputation ?? 0,
            isGm: playSession.isGm,
            characterStats: playSession.characterStats ?? null,
            resonanceLevelsTotal: playSession.resonanceLevelsTotal ?? null,
            liveLocation: playSession.liveLocation ?? null,
            liveEffects: playSession.liveEffects ?? null,
            liveInventory: playSession.liveInventory ?? null,
            liveMap: playSession.liveMap ?? null,
            chatMessages: playSession.chatMessages ?? null,
          }}
          onSignOut={onSignOut}
          narrativeLines={narrativeLines}
          onSendCommand={onSendCommand}
          wsConnected={wsConnected}
          wsStopped={wsStopped}
          onReconnect={() => {
            setWsStopped(null);
            setWsRetry((n) => n + 1);
          }}
          sceneImageUrl={resolvedSceneImageUrl}
          sceneRoomLabel={import.meta.env.VITE_SCENE_ROOM_LABEL || undefined}
          sceneDownloadBaseName={`fablestar-scene-${String(playSession.characterName || "character").replace(/[^a-zA-Z0-9_-]+/g, "_")}`}
          gameCurrencyDisplayName={auth?.gameCurrencyDisplayName ?? "Digi"}
          echoEconomy={echoEconomy}
          sceneGen={{
            username: playSession.username,
            characterId: playSession.characterId,
            getPassword: () => passwordRef.current,
            areaReady: playComfyScene.areaReady,
            areaGenerationCost: playComfyScene.areaCost,
            economyEnabled: playComfyScene.economyEnabled,
            echoCredits: echoEconomy.credits,
            currencyLabel: echoEconomy.label || playComfyScene.currencyDisplayName,
            onPixelsHelp: explainPlayPixels,
            onSceneGenerated: handleSceneImageSaved,
            beginBackgroundSceneGenerate,
            mergeEchoFromPlayRes,
          }}
        />
      </div>
    );
  }
  return <div style={appShell} />;
}
