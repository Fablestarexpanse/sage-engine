/**
 * Nexus HTTP origin, or "" in dev to use the Vite proxy (same-origin /play, /media).
 * Set VITE_NEXUS_URL to talk to Nexus directly (remote API or no proxy).
 */
function base() {
  const explicit = (import.meta.env.VITE_NEXUS_URL || "").trim().replace(/\/$/, "");
  if (explicit) return explicit;
  if (import.meta.env.DEV) return "";
  return `http://127.0.0.1:${import.meta.env.VITE_NEXUS_PORT || "8001"}`.replace(/\/$/, "");
}

/** Resolved Nexus HTTP origin (for UI hints). Empty string means same-origin / Vite proxy in dev. */
export function playApiBaseUrl() {
  const b = base();
  return b || "(this origin — dev proxy to Nexus)";
}

/**
 * Play session token (JWT) issued by /play/auth/login and /play/auth/register.
 * Held in memory only; sent on subsequent /play/* calls so the password is not
 * re-transmitted on every action. Server falls back to username/password when absent.
 */
let playToken = "";

export function getPlayToken() {
  return playToken;
}

export function clearPlayToken() {
  playToken = "";
}

function captureToken(data) {
  if (data && typeof data.play_token === "string" && data.play_token) {
    playToken = data.play_token;
  }
  return data;
}

/** Auth fields for authenticated /play/* payloads: token when we have one, else credentials. */
function authFields(username, password) {
  if (playToken) return { token: playToken };
  return { username, password };
}

async function handlePlayResponse(r) {
  if (r.status === 502 || r.status === 503) {
    throw new Error(
      `HTTP ${r.status}: Nexus is not running or not reachable. On Windows: start Docker Desktop and wait until it is ready, then in the repo root run: docker compose up -d redis postgres — then: python -m fablestar (Nexus on port 8001).`
    );
  }
  if (r.status === 404) {
    let detail = "";
    try {
      const j = await r.clone().json();
      if (typeof j?.detail === "string") detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(
      detail === "Not Found"
        ? "This Nexus process does not know that route (HTTP 404). Stop any old python -m fablestar on this port and start it again from the current project (python -m fablestar) so /play routes match your client."
        : "Player route not found (HTTP 404). Restart Nexus from the project root: python -m fablestar — an old process on the port will be missing newer /play routes."
    );
  }
  let data;
  try {
    data = await r.json();
  } catch {
    data = null;
  }
  if (!r.ok) {
    const msg = data?.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : `HTTP ${r.status}`;
    throw new Error(msg);
  }
  return data;
}

export async function playLogin(username, password) {
  const r = await fetch(`${base()}/play/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return captureToken(await handlePlayResponse(r));
}

/** Dev-only: is passwordless test login available to this browser? */
export async function playDevStatus() {
  try {
    const r = await fetch(`${base()}/play/dev/status`);
    if (!r.ok) return false;
    const j = await r.json();
    return Boolean(j?.enabled);
  } catch {
    return false;
  }
}

/** Dev-only: log in as (creating if needed) a test character on the dev account. */
export async function playDevLogin(character) {
  const r = await fetch(`${base()}/play/dev/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ character }),
  });
  return captureToken(await handlePlayResponse(r));
}

export async function playRegister(username, password) {
  const r = await fetch(`${base()}/play/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return captureToken(await handlePlayResponse(r));
}

export function playWebSocketUrl() {
  const b = base();
  if (!b && typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws/play`;
  }
  const u = new URL(b || `http://127.0.0.1:${import.meta.env.VITE_NEXUS_PORT || "8001"}`);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = "/ws/play";
  u.search = "";
  u.hash = "";
  return u.toString();
}

/** Absolute URL for a Nexus path (e.g. character portrait). Optional cacheBust avoids stale browser cache on regenerate. */
export function playMediaUrl(relativePath, cacheBust) {
  if (!relativePath) return null;
  const p = relativePath.startsWith("/") ? relativePath : `/${relativePath}`;
  let u = `${base()}${p}`;
  if (cacheBust != null && cacheBust !== "") {
    u += `${u.includes("?") ? "&" : "?"}v=${encodeURIComponent(String(cacheBust))}`;
  }
  return u;
}

export async function playComfyuiStatus() {
  const r = await fetch(`${base()}/play/comfyui/status`);
  return handlePlayResponse(r);
}

/**
 * Public leaf catalog for chargen (budget, caps, domain list). No auth.
 * Checks /play/health first so older Nexus builds (no GET /play/proficiencies/catalog)
 * fail with a short message instead of HTTP 404 from the catalog route.
 */
export async function playFetchProficiencyCatalog() {
  const hr = await fetch(`${base()}/play/health`);
  const health = await handlePlayResponse(hr);
  if (!health || health.proficiency_catalog !== true) {
    throw new Error(
      "The skill picker is not available on this Nexus build. Stop the server and start it again from this project: python -m fablestar."
    );
  }
  const r = await fetch(`${base()}/play/proficiencies/catalog`);
  return handlePlayResponse(r);
}

export async function playGeneratePortrait(username, password, appearance_prompt) {
  const r = await fetch(`${base()}/play/characters/portrait`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...authFields(username, password), appearance_prompt }),
  });
  return handlePlayResponse(r);
}

/** draftPortraitPrompt: rough text from the portrait field; sent as appearance_notes for the LLM template. */
export async function playSuggestPortraitPrompt(username, password, character_name, draftPortraitPrompt) {
  const r = await fetch(`${base()}/play/characters/suggest-portrait-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...authFields(username, password),
      character_name: character_name || "",
      appearance_notes: draftPortraitPrompt || "",
    }),
  });
  return handlePlayResponse(r);
}

export async function playCreateCharacter(username, password, name, portrait_prompt, portrait_url, starter_proficiencies) {
  const payload = {
    ...authFields(username, password),
    name,
    portrait_prompt: portrait_prompt || "",
    portrait_url: portrait_url || "",
  };
  if (starter_proficiencies && typeof starter_proficiencies === "object") {
    const cleaned = {};
    for (const [k, v] of Object.entries(starter_proficiencies)) {
      const n = Number(v);
      if (Number.isFinite(n) && n > 0) cleaned[String(k)] = Math.floor(n);
    }
    if (Object.keys(cleaned).length) payload.starter_proficiencies = cleaned;
  }
  const r = await fetch(`${base()}/play/characters/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handlePlayResponse(r);
}

/** Re-fetch characters + account fields (is_gm, echo_credits) from Nexus. */
export async function playRefreshSession(username, password) {
  const r = await fetch(`${base()}/play/auth/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(authFields(username, password)),
  });
  return handlePlayResponse(r);
}

async function parsePlayJson(r) {
  try {
    return await r.json();
  } catch {
    return null;
  }
}

function playHttpError(r, data) {
  if (r.status === 404) {
    const detail = typeof data?.detail === "string" ? data.detail : "";
    throw new Error(
      detail === "Not Found"
        ? "This Nexus process does not know that route (HTTP 404). Stop any old python -m fablestar on this port and start it again from the current project (python -m fablestar) so /play routes match your client."
        : "Player route not found (HTTP 404). Restart Nexus from the project root: python -m fablestar — an old process on the port will be missing newer /play routes."
    );
  }
  const msg = data?.detail
    ? typeof data.detail === "string"
      ? data.detail
      : JSON.stringify(data.detail)
    : `HTTP ${r.status}`;
  throw new Error(msg);
}


export async function playSuggestScenePrompt(username, password, narrative_context, room_hint) {
  const r = await fetch(`${base()}/play/scene/suggest-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...authFields(username, password),
      narrative_context: narrative_context || "",
      room_hint: room_hint || "",
    }),
  });
  if (!r.ok) {
    const data = await parsePlayJson(r);
    playHttpError(r, data);
  }
  return parsePlayJson(r);
}

export async function playGenerateSceneImage(username, password, scene_prompt, character_id) {
  const r = await fetch(`${base()}/play/scene/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...authFields(username, password),
      scene_prompt: scene_prompt || "",
      ...(character_id != null && character_id >= 1 ? { character_id } : {}),
    }),
  });
  if (!r.ok) {
    const data = await parsePlayJson(r);
    playHttpError(r, data);
  }
  return parsePlayJson(r);
}

export async function playListSceneGallery(username, password) {
  const r = await fetch(`${base()}/play/scene/gallery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(authFields(username, password)),
  });
  return handlePlayResponse(r);
}

export async function playApplySceneFromGallery(username, password, gallery_id, character_id) {
  const r = await fetch(`${base()}/play/scene/apply-gallery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...authFields(username, password),
      gallery_id,
      character_id,
    }),
  });
  return handlePlayResponse(r);
}

export async function playDeleteCharacter(username, password, character_id) {
  const r = await fetch(`${base()}/play/characters/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...authFields(username, password), character_id }),
  });
  return handlePlayResponse(r);
}
